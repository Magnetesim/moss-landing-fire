#!/usr/bin/env python3

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORWARD_SCRIPT = PROJECT_ROOT / "scripts" / "hysplit" / "run_forward_dispersion.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "sweeps"
DEFAULT_IGNITION_UTC = "2025-01-16T23:00:00Z"
DEFAULT_STOP_UTC = "2025-01-18T23:00:00Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a forward HYSPLIT time-height ensemble with sequential 4-hour windows from ignition."
    )
    parser.add_argument("--ignition-utc", default=DEFAULT_IGNITION_UTC, help="Ignition/release start in UTC.")
    parser.add_argument("--stop-utc", default=DEFAULT_STOP_UTC, help="Last model/sample time in UTC.")
    parser.add_argument(
        "--window-hours",
        type=float,
        default=4.0,
        help="Integrated plume window width in hours.",
    )
    parser.add_argument(
        "--window-step-hours",
        type=float,
        default=4.0,
        help="Time between successive window starts in hours.",
    )
    parser.add_argument(
        "--source-heights-m",
        default="10,25,50,100,250",
        help="Comma-separated release heights in meters AGL.",
    )
    parser.add_argument("--source-lat", type=float, default=36.8044)
    parser.add_argument("--source-lon", type=float, default=-121.7883)
    parser.add_argument(
        "--source-geometry",
        choices=("point", "area_grid"),
        default="area_grid",
        help="Source geometry to pass through to each forward run.",
    )
    parser.add_argument("--source-footprint-m", default="300,120")
    parser.add_argument("--source-grid-shape", default="5,3")
    parser.add_argument("--source-rotation-deg", type=float, default=0.0)
    parser.add_argument("--emission-rate", type=float, default=1.0)
    parser.add_argument(
        "--release-end-utc",
        default=None,
        help="Optional common release end time in UTC. Defaults to each window stop time.",
    )
    parser.add_argument("--concentration-level-m", type=float, default=10.0)
    parser.add_argument("--grid-center-lat", type=float, default=36.82)
    parser.add_argument("--grid-center-lon", type=float, default=-121.80)
    parser.add_argument("--grid-spacing-deg", default="0.01,0.01")
    parser.add_argument("--grid-span-deg", default="1.40,1.20")
    parser.add_argument("--plot-styles", default="county,dynamic_exp,dynamic_lin")
    parser.add_argument("--plot-frames", action="store_true")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--numpar", type=int, default=500)
    parser.add_argument("--maxpar", type=int, default=50000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--forward-script", type=Path, default=DEFAULT_FORWARD_SCRIPT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--run-tag-prefix",
        default="time_height",
        help="Prefix used to name each forward run directory.",
    )
    return parser.parse_args()


def parse_float_list(raw: str) -> list[float]:
    values = [float(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not values:
        raise ValueError("Expected at least one numeric value")
    return values


def format_token(value: float) -> str:
    return f"{value:g}".replace(".", "p").replace("-", "m")


def build_windows(
    ignition_utc: pd.Timestamp,
    stop_utc: pd.Timestamp,
    window_hours: float,
    step_hours: float,
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    if window_hours <= 0 or step_hours <= 0:
        raise ValueError("--window-hours and --window-step-hours must be positive")
    windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    current = ignition_utc
    width = pd.to_timedelta(window_hours, unit="h")
    step = pd.to_timedelta(step_hours, unit="h")
    while current + width <= stop_utc:
        windows.append((current, current + width))
        current += step
    if not windows:
        raise ValueError("No valid sample windows fit between --ignition-utc and --stop-utc")
    return windows


def build_run_tag(
    prefix: str,
    source_height_m: float,
    sample_start_utc: pd.Timestamp,
    sample_stop_utc: pd.Timestamp,
    source_geometry: str,
    source_grid_shape: str,
) -> str:
    tag = (
        f"{prefix}_h{format_token(source_height_m)}"
        f"_w{sample_start_utc:%Y%m%d%H}"
        f"to{sample_stop_utc:%Y%m%d%H}"
    )
    if source_geometry == "area_grid":
        tag += "_src" + source_grid_shape.replace(",", "x")
    return tag


def build_geometry_suffix(source_geometry: str, source_grid_shape: str) -> str:
    if source_geometry == "point":
        return ""
    nx, ny = [piece.strip() for piece in source_grid_shape.split(",", maxsplit=1)]
    return f"_srcarea{nx}x{ny}"


def refresh_symlink(link_path: Path, target: Path) -> None:
    if os.path.lexists(link_path):
        try:
            link_path.unlink()
        except FileNotFoundError:
            pass
    os.symlink(target, link_path, target_is_directory=target.is_dir())


def update_latest_pointers(output_root: Path, manifest_path: Path, run_tag_prefix: str) -> None:
    latest_dir = output_root / "latest"
    latest_dir.mkdir(exist_ok=True)
    refresh_symlink(latest_dir / "manifest.csv", manifest_path.resolve())
    (latest_dir / "latest_sweep_prefix.txt").write_text(run_tag_prefix + "\n", encoding="utf-8")
    (latest_dir / "latest_manifest.txt").write_text(str(manifest_path.resolve()) + "\n", encoding="utf-8")


def run_case(
    python_exe: str,
    forward_script: Path,
    output_root: Path,
    ignition_utc: pd.Timestamp,
    stop_utc: pd.Timestamp,
    release_end_utc: pd.Timestamp | None,
    sample_start_utc: pd.Timestamp,
    sample_stop_utc: pd.Timestamp,
    source_height_m: float,
    args: argparse.Namespace,
) -> dict[str, object]:
    effective_release_end = release_end_utc if release_end_utc is not None else sample_stop_utc
    emission_hours = (effective_release_end - ignition_utc).total_seconds() / 3600.0
    if emission_hours <= 0:
        raise ValueError("Computed emission duration must be positive")

    run_tag = build_run_tag(
        args.run_tag_prefix,
        source_height_m,
        sample_start_utc,
        sample_stop_utc,
        args.source_geometry,
        args.source_grid_shape,
    )
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
        args.source_geometry,
        "--source-footprint-m",
        args.source_footprint_m,
        "--source-grid-shape",
        args.source_grid_shape,
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
    if args.plot_frames:
        cmd.append("--plot-frames")
    if args.plot:
        cmd.append("--plot")
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

    run_dir = output_root / (
        f"{run_tag}_t{ignition_utc:%Y%m%d%H}_to_{sample_stop_utc:%Y%m%d%H}_"
        f"h{int(round(source_height_m)):04d}"
        f"{build_geometry_suffix(args.source_geometry, args.source_grid_shape)}"
    )

    return {
        "run_tag": run_tag,
        "ignition_utc": ignition_utc.isoformat(),
        "simulation_end_utc": sample_stop_utc.isoformat(),
        "sample_start_utc": sample_start_utc.isoformat(),
        "sample_stop_utc": sample_stop_utc.isoformat(),
        "release_end_utc": effective_release_end.isoformat(),
        "emission_hours": emission_hours,
        "source_height_m": source_height_m,
        "source_geometry": args.source_geometry,
        "source_footprint_m": args.source_footprint_m,
        "source_grid_shape": args.source_grid_shape,
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
        raise FileNotFoundError(f"Could not find forward script at {args.forward_script}")

    ignition_utc = pd.Timestamp(args.ignition_utc, tz="UTC")
    stop_utc = pd.Timestamp(args.stop_utc, tz="UTC")
    release_end_utc = pd.Timestamp(args.release_end_utc, tz="UTC") if args.release_end_utc else None
    if stop_utc <= ignition_utc:
        raise ValueError("--stop-utc must be later than --ignition-utc")
    if release_end_utc is not None and release_end_utc < ignition_utc:
        raise ValueError("--release-end-utc cannot be earlier than --ignition-utc")

    source_heights = parse_float_list(args.source_heights_m)
    windows = build_windows(ignition_utc, stop_utc, args.window_hours, args.window_step_hours)
    combos = [(height, start, stop) for start, stop in windows for height in source_heights]
    args.output_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    if args.jobs == 1:
        for source_height_m, sample_start_utc, sample_stop_utc in combos:
            results.append(
                run_case(
                    sys.executable,
                    args.forward_script,
                    args.output_root,
                    ignition_utc,
                    stop_utc,
                    release_end_utc,
                    sample_start_utc,
                    sample_stop_utc,
                    source_height_m,
                    args,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = [
                executor.submit(
                    run_case,
                    sys.executable,
                    args.forward_script,
                    args.output_root,
                    ignition_utc,
                    stop_utc,
                    release_end_utc,
                    sample_start_utc,
                    sample_stop_utc,
                    source_height_m,
                    args,
                )
                for source_height_m, sample_start_utc, sample_stop_utc in combos
            ]
            for future in as_completed(futures):
                results.append(future.result())

    manifest = pd.DataFrame(results).sort_values(
        ["sample_start_utc", "source_height_m"]
    ).reset_index(drop=True)
    manifest_path = args.output_root / f"{args.run_tag_prefix}_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    update_latest_pointers(args.output_root, manifest_path, args.run_tag_prefix)

    print(f"Forward time-height cases: {len(combos)}")
    print(f"Sample windows: {len(windows)}")
    print(f"Heights: {source_heights}")
    print(f"Concurrent jobs: {args.jobs}")
    print(f"Saved manifest to {manifest_path}")
    print(manifest["status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
