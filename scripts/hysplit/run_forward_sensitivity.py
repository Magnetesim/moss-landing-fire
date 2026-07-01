#!/usr/bin/env python3

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORWARD_SCRIPT = PROJECT_ROOT / "scripts" / "hysplit" / "run_forward_dispersion.py"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "sweeps"
DEFAULT_START_UTC = "2025-01-18T02:00:00Z"
DEFAULT_END_UTC = "2025-01-18T06:00:00Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a parallel forward-dispersion sensitivity sweep."
    )
    parser.add_argument("--start-utc", default=DEFAULT_START_UTC)
    parser.add_argument("--end-utc", default=DEFAULT_END_UTC)
    parser.add_argument(
        "--release-start-utc",
        default=None,
        help="Emission start time in UTC for each run. Defaults to --start-utc.",
    )
    parser.add_argument(
        "--sample-start-utc",
        default=DEFAULT_START_UTC,
        help="Sampling window start time in UTC for each run.",
    )
    parser.add_argument(
        "--sample-stop-utc",
        default=DEFAULT_END_UTC,
        help="Sampling window stop time in UTC for each run.",
    )
    parser.add_argument(
        "--source-heights-m",
        default="10,50,100,200",
        help="Comma-separated release heights in meters AGL.",
    )
    parser.add_argument(
        "--emission-hours-list",
        default="2,4,8",
        help="Comma-separated release durations in hours.",
    )
    parser.add_argument(
        "--emission-rates",
        default="1",
        help="Comma-separated emission rates in model units per hour.",
    )
    parser.add_argument(
        "--sampling-interval-hours",
        type=float,
        default=1.0,
        help="Output averaging interval for each forward run.",
    )
    parser.add_argument("--source-lat", type=float, default=36.8044)
    parser.add_argument("--source-lon", type=float, default=-121.7883)
    parser.add_argument(
        "--source-geometry",
        choices=("point", "area_grid"),
        default="point",
        help="Source geometry to pass through to each forward run.",
    )
    parser.add_argument(
        "--source-footprint-m",
        default="300,120",
        help="East-west,north-south source footprint in meters for area-grid runs.",
    )
    parser.add_argument(
        "--source-grid-shape",
        default="5,3",
        help="Number of source points in east-west,north-south directions for area-grid runs.",
    )
    parser.add_argument(
        "--source-rotation-deg",
        type=float,
        default=0.0,
        help="Counterclockwise footprint rotation in degrees for area-grid runs.",
    )
    parser.add_argument("--concentration-level-m", type=float, default=10.0)
    parser.add_argument("--grid-center-lat", type=float, default=36.82)
    parser.add_argument("--grid-center-lon", type=float, default=-121.80)
    parser.add_argument("--grid-spacing-deg", default="0.01,0.01")
    parser.add_argument("--grid-span-deg", default="1.40,1.20")
    parser.add_argument("--plot-styles", default="county,dynamic_exp,dynamic_lin")
    parser.add_argument("--plot-frames", action="store_true")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--numpar", type=int, default=500, help="Initial number of particles/puffs for each HYSPLIT run.")
    parser.add_argument("--maxpar", type=int, default=50000, help="Maximum particle/puff count for each HYSPLIT run.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--forward-script", type=Path, default=DEFAULT_FORWARD_SCRIPT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--run-tag-prefix",
        default="sensitivity",
        help="Prefix used to name each forward run directory.",
    )
    return parser.parse_args()


def parse_float_list(raw: str) -> list[float]:
    values = [float(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not values:
        raise ValueError("Expected at least one numeric value")
    return values


def format_token(value: float) -> str:
    formatted = f"{value:g}"
    return formatted.replace(".", "p").replace("-", "m")


def build_run_tag(
    prefix: str,
    source_height_m: float,
    emission_hours: float,
    emission_rate: float,
    source_geometry: str,
    source_grid_shape: str,
) -> str:
    tag = (
        f"{prefix}_h{format_token(source_height_m)}"
        f"_eh{format_token(emission_hours)}"
        f"_er{format_token(emission_rate)}"
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
    if link_path.exists() or link_path.is_symlink():
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
    start_utc: str,
    end_utc: str,
    release_start_utc: str | None,
    sample_start_utc: str | None,
    sample_stop_utc: str | None,
    source_lat: float,
    source_lon: float,
    source_geometry: str,
    source_footprint_m: str,
    source_grid_shape: str,
    source_rotation_deg: float,
    source_height_m: float,
    emission_rate: float,
    emission_hours: float,
    concentration_level_m: float,
    grid_center_lat: float,
    grid_center_lon: float,
    grid_spacing_deg: str,
    grid_span_deg: str,
    sampling_interval_hours: float,
    numpar: int,
    maxpar: int,
    plot_styles: str,
    plot_frames: bool,
    plot: bool,
    dry_run: bool,
    run_tag_prefix: str,
) -> dict[str, object]:
    run_tag = build_run_tag(
        run_tag_prefix,
        source_height_m,
        emission_hours,
        emission_rate,
        source_geometry,
        source_grid_shape,
    )
    cmd = [
        python_exe,
        str(forward_script),
        "--start-utc",
        start_utc,
        "--end-utc",
        end_utc,
        "--source-lat",
        str(source_lat),
        "--source-lon",
        str(source_lon),
        "--source-geometry",
        source_geometry,
        "--source-footprint-m",
        source_footprint_m,
        "--source-grid-shape",
        source_grid_shape,
        "--source-rotation-deg",
        str(source_rotation_deg),
        "--source-height-m",
        str(source_height_m),
        "--emission-rate",
        str(emission_rate),
        "--emission-hours",
        str(emission_hours),
        "--concentration-level-m",
        str(concentration_level_m),
        "--grid-center-lat",
        str(grid_center_lat),
        "--grid-center-lon",
        str(grid_center_lon),
        "--grid-spacing-deg",
        grid_spacing_deg,
        "--grid-span-deg",
        grid_span_deg,
        "--sampling-interval-hours",
        str(sampling_interval_hours),
        "--numpar",
        str(numpar),
        "--maxpar",
        str(maxpar),
        "--plot-styles",
        plot_styles,
        "--output-root",
        str(output_root),
        "--run-tag",
        run_tag,
    ]

    if release_start_utc is not None:
        cmd.extend(["--release-start-utc", release_start_utc])
    if sample_start_utc is not None:
        cmd.extend(["--sample-start-utc", sample_start_utc])
    if sample_stop_utc is not None:
        cmd.extend(["--sample-stop-utc", sample_stop_utc])

    if plot_frames:
        cmd.append("--plot-frames")
    if plot:
        cmd.append("--plot")
    if dry_run:
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
        f"{run_tag}_t{pd.Timestamp(start_utc):%Y%m%d%H}_to_{pd.Timestamp(end_utc):%Y%m%d%H}_"
        f"h{int(round(source_height_m)):04d}"
        f"{build_geometry_suffix(source_geometry, source_grid_shape)}"
    )

    return {
        "run_tag": run_tag,
        "start_utc": start_utc,
        "end_utc": end_utc,
        "source_height_m": source_height_m,
        "source_geometry": source_geometry,
        "source_footprint_m": source_footprint_m,
        "source_grid_shape": source_grid_shape,
        "source_rotation_deg": source_rotation_deg,
        "emission_rate": emission_rate,
        "emission_hours": emission_hours,
        "sampling_interval_hours": sampling_interval_hours,
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

    source_heights = parse_float_list(args.source_heights_m)
    emission_hours_list = parse_float_list(args.emission_hours_list)
    emission_rates = parse_float_list(args.emission_rates)

    combos = list(itertools.product(source_heights, emission_hours_list, emission_rates))
    args.output_root.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    if args.jobs == 1:
        for source_height_m, emission_hours, emission_rate in combos:
            results.append(
                run_case(
                    python_exe=sys.executable,
                    forward_script=args.forward_script,
                    output_root=args.output_root,
                    start_utc=args.start_utc,
                    end_utc=args.end_utc,
                    release_start_utc=args.release_start_utc,
                    sample_start_utc=args.sample_start_utc,
                    sample_stop_utc=args.sample_stop_utc,
                    source_lat=args.source_lat,
                    source_lon=args.source_lon,
                    source_geometry=args.source_geometry,
                    source_footprint_m=args.source_footprint_m,
                    source_grid_shape=args.source_grid_shape,
                    source_rotation_deg=args.source_rotation_deg,
                    source_height_m=source_height_m,
                    emission_rate=emission_rate,
                    emission_hours=emission_hours,
                    concentration_level_m=args.concentration_level_m,
                    grid_center_lat=args.grid_center_lat,
                    grid_center_lon=args.grid_center_lon,
                    grid_spacing_deg=args.grid_spacing_deg,
                    grid_span_deg=args.grid_span_deg,
                    sampling_interval_hours=args.sampling_interval_hours,
                    numpar=args.numpar,
                    maxpar=args.maxpar,
                    plot_styles=args.plot_styles,
                    plot_frames=args.plot_frames,
                    plot=args.plot,
                    dry_run=args.dry_run,
                    run_tag_prefix=args.run_tag_prefix,
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
                    args.start_utc,
                    args.end_utc,
                    args.release_start_utc,
                    args.sample_start_utc,
                    args.sample_stop_utc,
                    args.source_lat,
                    args.source_lon,
                    args.source_geometry,
                    args.source_footprint_m,
                    args.source_grid_shape,
                    args.source_rotation_deg,
                    source_height_m,
                    emission_rate,
                    emission_hours,
                    args.concentration_level_m,
                    args.grid_center_lat,
                    args.grid_center_lon,
                    args.grid_spacing_deg,
                    args.grid_span_deg,
                    args.sampling_interval_hours,
                    args.numpar,
                    args.maxpar,
                    args.plot_styles,
                    args.plot_frames,
                    args.plot,
                    args.dry_run,
                    args.run_tag_prefix,
                )
                for source_height_m, emission_hours, emission_rate in combos
            ]
            for future in as_completed(futures):
                results.append(future.result())

    manifest = pd.DataFrame(results).sort_values(
        ["source_height_m", "emission_hours", "emission_rate"]
    ).reset_index(drop=True)
    manifest_path = args.output_root / f"{args.run_tag_prefix}_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    update_latest_pointers(args.output_root, manifest_path, args.run_tag_prefix)

    print(f"Forward sensitivity cases: {len(combos)}")
    print(f"Concurrent jobs: {args.jobs}")
    print(f"Saved manifest to {manifest_path}")
    print(manifest["status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
