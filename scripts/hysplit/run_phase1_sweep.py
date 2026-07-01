#!/usr/bin/env python3

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORWARD_SCRIPT = PROJECT_ROOT / "scripts" / "hysplit" / "run_forward_dispersion.py"
DEFAULT_SCORE_SCRIPT = PROJECT_ROOT / "scripts" / "hysplit" / "score_against_purpleair.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "sweeps"
DEFAULT_IGNITION_UTC = "2025-01-16T23:00:00Z"
DEFAULT_SOURCE_SETUPS = "point|300,120|1,1;area_grid|300,120|5,3;area_grid|600,240|7,3;area_grid|900,360|9,5"
DEFAULT_SOURCE_HEIGHTS_M = "10,25,50,100,150,250"
DEFAULT_RELEASE_DURATIONS_H = "4,8,12,24"
DEFAULT_WINDOW_INDICES = "1,4,7,10"
DEFAULT_RUN_TAG_PREFIX = "phase1_matrix"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the phase 1 Moss Landing HYSPLIT sweep and auto-rank against PurpleAir."
    )
    parser.add_argument("--ignition-utc", default=DEFAULT_IGNITION_UTC)
    parser.add_argument("--source-heights-m", default=DEFAULT_SOURCE_HEIGHTS_M)
    parser.add_argument("--release-durations-h", default=DEFAULT_RELEASE_DURATIONS_H)
    parser.add_argument(
        "--source-setups",
        default=DEFAULT_SOURCE_SETUPS,
        help=(
            "Semicolon-separated geometry specs as geometry|footprint|grid_shape. "
            "For point sources use any valid footprint/grid pair, e.g. point|300,120|1,1."
        ),
    )
    parser.add_argument("--window-indices", default=DEFAULT_WINDOW_INDICES)
    parser.add_argument("--window-hours", type=float, default=4.0)
    parser.add_argument("--window-step-hours", type=float, default=4.0)
    parser.add_argument("--source-lat", type=float, default=36.8044)
    parser.add_argument("--source-lon", type=float, default=-121.7883)
    parser.add_argument("--source-rotation-deg", type=float, default=0.0)
    parser.add_argument("--emission-rate", type=float, default=1.0)
    parser.add_argument("--concentration-level-m", type=float, default=10.0)
    parser.add_argument("--grid-center-lat", type=float, default=36.82)
    parser.add_argument("--grid-center-lon", type=float, default=-121.80)
    parser.add_argument("--grid-spacing-deg", default="0.01,0.01")
    parser.add_argument("--grid-span-deg", default="1.40,1.20")
    parser.add_argument("--numpar", type=int, default=500)
    parser.add_argument("--maxpar", type=int, default=50000)
    parser.add_argument("--plot-styles", default="county,dynamic_exp,dynamic_lin")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--forward-script", type=Path, default=DEFAULT_FORWARD_SCRIPT)
    parser.add_argument("--score-script", type=Path, default=DEFAULT_SCORE_SCRIPT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-tag-prefix", default=DEFAULT_RUN_TAG_PREFIX)
    parser.add_argument("--score", action="store_true", help="Run PurpleAir scoring after HYSPLIT completes.")
    parser.add_argument("--purpleair-rows", default=DEFAULT_WINDOW_INDICES)
    parser.add_argument("--purpleair-threshold", type=float, default=12.0)
    parser.add_argument("--hysplit-binary-class", type=int, default=3)
    parser.add_argument("--score-scenario-columns", default="scenario_tag")
    return parser.parse_args()


def parse_float_list(raw: str) -> list[float]:
    values = [float(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not values:
        raise ValueError("Expected at least one numeric value")
    return values


def parse_int_list(raw: str) -> list[int]:
    values = [int(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not values:
        raise ValueError("Expected at least one integer value")
    return values


def format_token(value: float) -> str:
    return f"{value:g}".replace(".", "p").replace("-", "m")


def parse_source_setups(raw: str) -> list[dict[str, str]]:
    setups: list[dict[str, str]] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [part.strip() for part in chunk.split("|")]
        if len(parts) != 3:
            raise ValueError(f"Bad source setup {chunk!r}; expected geometry|footprint|grid_shape")
        geometry, footprint, grid_shape = parts
        if geometry not in {"point", "area_grid"}:
            raise ValueError(f"Unsupported source geometry: {geometry}")
        setups.append(
            {
                "source_geometry": geometry,
                "source_footprint_m": footprint,
                "source_grid_shape": grid_shape,
            }
        )
    if not setups:
        raise ValueError("No source setups configured")
    return setups


def build_sample_windows(
    ignition_utc: pd.Timestamp,
    window_indices: list[int],
    window_hours: float,
    window_step_hours: float,
) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
    width = pd.to_timedelta(window_hours, unit="h")
    step = pd.to_timedelta(window_step_hours, unit="h")
    windows = []
    for idx in window_indices:
        start = ignition_utc + idx * step
        stop = start + width
        windows.append((idx, start, stop))
    return windows


def build_geometry_suffix(source_geometry: str, source_grid_shape: str) -> str:
    if source_geometry == "point":
        return "pt"
    return "area" + source_grid_shape.replace(",", "x")


def build_scenario_tag(
    source_height_m: float,
    release_duration_h: float,
    source_geometry: str,
    source_footprint_m: str,
    source_grid_shape: str,
) -> str:
    parts = [
        f"h{format_token(source_height_m)}",
        f"dur{format_token(release_duration_h)}",
        build_geometry_suffix(source_geometry, source_grid_shape),
    ]
    if source_geometry == "area_grid":
        parts.append("fp" + source_footprint_m.replace(",", "x"))
    return "_".join(parts)


def run_case(
    python_exe: str,
    forward_script: Path,
    output_root: Path,
    ignition_utc: pd.Timestamp,
    sample_start_utc: pd.Timestamp,
    sample_stop_utc: pd.Timestamp,
    release_end_utc: pd.Timestamp,
    source_height_m: float,
    scenario_tag: str,
    window_index: int,
    setup: dict[str, str],
    args: argparse.Namespace,
) -> dict[str, object]:
    run_tag = (
        f"{args.run_tag_prefix}_{scenario_tag}"
        f"_w{window_index:02d}"
        f"_{sample_start_utc:%Y%m%d%H}to{sample_stop_utc:%Y%m%d%H}"
    )
    emission_hours = (release_end_utc - ignition_utc).total_seconds() / 3600.0
    cmd = [
        python_exe,
        str(forward_script),
        "--start-utc",
        ignition_utc.isoformat().replace("+00:00", "Z"),
        "--end-utc",
        sample_stop_utc.isoformat().replace("+00:00", "Z"),
        "--release-start-utc",
        ignition_utc.isoformat().replace("+00:00", "Z"),
        "--sample-start-utc",
        sample_start_utc.isoformat().replace("+00:00", "Z"),
        "--sample-stop-utc",
        sample_stop_utc.isoformat().replace("+00:00", "Z"),
        "--source-lat",
        str(args.source_lat),
        "--source-lon",
        str(args.source_lon),
        "--source-geometry",
        setup["source_geometry"],
        "--source-footprint-m",
        setup["source_footprint_m"],
        "--source-grid-shape",
        setup["source_grid_shape"],
        "--source-rotation-deg",
        str(args.source_rotation_deg),
        "--source-height-m",
        str(source_height_m),
        "--emission-rate",
        str(args.emission_rate),
        "--emission-hours",
        str(emission_hours),
        "--concentration-level-m",
        str(args.concentration_level_m),
        "--grid-center-lat",
        str(args.grid_center_lat),
        "--grid-center-lon",
        str(args.grid_center_lon),
        "--grid-spacing-deg",
        args.grid_spacing_deg,
        "--grid-span-deg",
        args.grid_span_deg,
        "--sampling-interval-hours",
        str(args.window_hours),
        "--numpar",
        str(args.numpar),
        "--maxpar",
        str(args.maxpar),
        "--plot-styles",
        args.plot_styles,
        "--output-root",
        str(output_root),
        "--run-tag",
        run_tag,
    ]
    if args.dry_run:
        cmd.append("--dry-run")

    proc = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    geometry_suffix = ""
    if setup["source_geometry"] == "area_grid":
        nx, ny = [piece.strip() for piece in setup["source_grid_shape"].split(",", maxsplit=1)]
        geometry_suffix = f"_srcarea{nx}x{ny}"

    run_dir = output_root / (
        f"{run_tag}_t{ignition_utc:%Y%m%d%H}_to_{sample_stop_utc:%Y%m%d%H}_"
        f"h{int(round(source_height_m)):04d}"
        f"{geometry_suffix}"
    )

    return {
        "scenario_tag": scenario_tag,
        "window_index": window_index,
        "run_tag": run_tag,
        "ignition_utc": ignition_utc.isoformat(),
        "simulation_end_utc": sample_stop_utc.isoformat(),
        "sample_start_utc": sample_start_utc.isoformat(),
        "sample_stop_utc": sample_stop_utc.isoformat(),
        "release_end_utc": release_end_utc.isoformat(),
        "emission_hours": emission_hours,
        "source_height_m": source_height_m,
        "source_geometry": setup["source_geometry"],
        "source_footprint_m": setup["source_footprint_m"],
        "source_grid_shape": setup["source_grid_shape"],
        "source_rotation_deg": args.source_rotation_deg,
        "emission_rate": args.emission_rate,
        "window_hours": args.window_hours,
        "run_dir": str(run_dir.resolve()),
        "status": "completed" if proc.returncode == 0 else "failed",
        "return_code": proc.returncode,
        "stdout": proc.stdout,
    }


def main() -> None:
    args = parse_args()
    if args.jobs < 1:
        raise ValueError("--jobs must be at least 1")
    if not args.forward_script.exists():
        raise FileNotFoundError(args.forward_script)
    if args.score and not args.score_script.exists():
        raise FileNotFoundError(args.score_script)

    ignition_utc = pd.Timestamp(args.ignition_utc, tz="UTC")
    source_heights = parse_float_list(args.source_heights_m)
    release_durations_h = parse_float_list(args.release_durations_h)
    source_setups = parse_source_setups(args.source_setups)
    window_indices = parse_int_list(args.window_indices)
    windows = build_sample_windows(ignition_utc, window_indices, args.window_hours, args.window_step_hours)

    args.output_root.mkdir(parents=True, exist_ok=True)
    jobs = []
    for height in source_heights:
        for duration_h in release_durations_h:
            release_end_utc = ignition_utc + pd.to_timedelta(duration_h, unit="h")
            for setup in source_setups:
                scenario_tag = build_scenario_tag(
                    source_height_m=height,
                    release_duration_h=duration_h,
                    source_geometry=setup["source_geometry"],
                    source_footprint_m=setup["source_footprint_m"],
                    source_grid_shape=setup["source_grid_shape"],
                )
                for window_index, sample_start_utc, sample_stop_utc in windows:
                    jobs.append(
                        {
                            "height": height,
                            "duration_h": duration_h,
                            "release_end_utc": release_end_utc,
                            "setup": setup,
                            "scenario_tag": scenario_tag,
                            "window_index": window_index,
                            "sample_start_utc": sample_start_utc,
                            "sample_stop_utc": sample_stop_utc,
                        }
                    )

    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = [
            executor.submit(
                run_case,
                sys.executable,
                args.forward_script,
                args.output_root,
                ignition_utc,
                job["sample_start_utc"],
                job["sample_stop_utc"],
                job["release_end_utc"],
                job["height"],
                job["scenario_tag"],
                job["window_index"],
                job["setup"],
                args,
            )
            for job in jobs
        ]
        for future in as_completed(futures):
            results.append(future.result())

    manifest = pd.DataFrame(results).sort_values(
        ["scenario_tag", "window_index", "source_height_m"]
    ).reset_index(drop=True)
    manifest_path = args.output_root / f"{args.run_tag_prefix}_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    print(f"Phase 1 scenarios: {len(source_heights) * len(release_durations_h) * len(source_setups)}")
    print(f"Phase 1 runs: {len(jobs)}")
    print(f"Saved manifest: {manifest_path}")
    print(manifest['status'].value_counts(dropna=False).to_string())

    if args.score:
        score_cmd = [
            sys.executable,
            str(args.score_script),
            "--manifest",
            str(manifest_path),
            "--rows",
            args.purpleair_rows,
            "--purpleair-threshold",
            str(args.purpleair_threshold),
            "--hysplit-binary-class",
            str(args.hysplit_binary_class),
            "--scenario-columns",
            args.score_scenario_columns,
        ]
        score_proc = subprocess.run(
            score_cmd,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        print(score_proc.stdout)
        if score_proc.returncode != 0:
            raise SystemExit(score_proc.returncode)


if __name__ == "__main__":
    main()
