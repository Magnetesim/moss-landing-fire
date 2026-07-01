#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HRRR_DIR = PROJECT_ROOT / "hrrr"
DEFAULT_HYSPLIT_ROOT = PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion"

DEFAULT_START_UTC = "2025-01-18T02:00:00Z"  # 2025-01-17 18:00 PST
DEFAULT_END_UTC = "2025-01-18T06:00:00Z"    # 2025-01-17 22:00 PST
DEFAULT_SOURCE_LAT = 36.8044
DEFAULT_SOURCE_LON = -121.7883


@dataclass(frozen=True)
class MetFile:
    start: pd.Timestamp
    filename: str


@dataclass(frozen=True)
class SourceSpec:
    lat: float
    lon: float
    height_m: float
    emission_rate: float | None = None
    emission_area_m2: float | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a forward HYSPLIT concentration simulation for the Moss Landing fire plume."
    )
    parser.add_argument("--start-utc", default=DEFAULT_START_UTC, help="Simulation start time in UTC.")
    parser.add_argument("--end-utc", default=DEFAULT_END_UTC, help="Simulation end time in UTC.")
    parser.add_argument(
        "--release-start-utc",
        default=None,
        help="Emission start time in UTC. Defaults to the simulation start time.",
    )
    parser.add_argument(
        "--sample-start-utc",
        default=None,
        help="Sampling window start time in UTC. Defaults to HYSPLIT's automatic behavior.",
    )
    parser.add_argument(
        "--sample-stop-utc",
        default=None,
        help="Sampling window stop time in UTC. Defaults to HYSPLIT's automatic behavior.",
    )
    parser.add_argument("--source-lat", type=float, default=DEFAULT_SOURCE_LAT)
    parser.add_argument("--source-lon", type=float, default=DEFAULT_SOURCE_LON)
    parser.add_argument("--source-height-m", type=float, default=10.0, help="Release height AGL in meters.")
    parser.add_argument(
        "--source-geometry",
        choices=("point", "area_grid"),
        default="point",
        help="Approximate the source as a single point or a small grid of release points.",
    )
    parser.add_argument(
        "--source-footprint-m",
        default="300,120",
        help="East-west,north-south source footprint in meters for --source-geometry area_grid.",
    )
    parser.add_argument(
        "--source-grid-shape",
        default="5,3",
        help="Number of source points in east-west,north-south directions for --source-geometry area_grid.",
    )
    parser.add_argument(
        "--source-rotation-deg",
        type=float,
        default=0.0,
        help="Counterclockwise rotation of the area-grid footprint in degrees.",
    )
    parser.add_argument("--emission-rate", type=float, default=1.0, help="Emission rate in model units per hour.")
    parser.add_argument("--emission-hours", type=float, default=None, help="Emission duration in hours. Defaults to full run length.")
    parser.add_argument("--pollutant-name", default="TEST", help="Four-character pollutant label used in HYSPLIT output.")
    parser.add_argument("--concentration-level-m", type=float, default=10.0, help="Output concentration height AGL in meters.")
    parser.add_argument("--grid-center-lat", type=float, default=36.82)
    parser.add_argument("--grid-center-lon", type=float, default=-121.80)
    parser.add_argument(
        "--grid-spacing-deg",
        default="0.01,0.01",
        help="Lat,lon spacing in degrees for the concentration grid.",
    )
    parser.add_argument(
        "--grid-span-deg",
        default="1.40,1.20",
        help="Lat,lon span in degrees for the concentration grid.",
    )
    parser.add_argument(
        "--sampling-interval-hours",
        type=float,
        default=1.0,
        help="Output averaging interval in hours. Defaults to 1 hour for time-resolved plume plots.",
    )
    parser.add_argument("--hrrr-dir", type=Path, default=DEFAULT_HRRR_DIR)
    parser.add_argument("--hysplit-root", type=Path, default=DEFAULT_HYSPLIT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-tag", default="pdf_window", help="Label used in the output directory name.")
    parser.add_argument("--dry-run", action="store_true", help="Write files but do not run hycs_std.")
    parser.add_argument("--plot", action="store_true", help="Run concplot.py after the concentration model succeeds.")
    parser.add_argument("--numpar", type=int, default=500, help="Initial number of particles/puffs released by HYSPLIT.")
    parser.add_argument("--maxpar", type=int, default=50000, help="Maximum particle/puff count allowed by HYSPLIT.")
    parser.add_argument(
        "--plot-styles",
        default="county,dynamic_exp,dynamic_lin",
        help="Comma-separated plot styles: county, dynamic_exp, dynamic_lin.",
    )
    parser.add_argument(
        "--plot-frames",
        action="store_true",
        help="Write one plot file per output time period instead of combining all periods into one file.",
    )
    return parser.parse_args()


def parse_pair(raw: str) -> tuple[float, float]:
    pieces = [piece.strip() for piece in raw.split(",") if piece.strip()]
    if len(pieces) != 2:
        raise ValueError(f"Expected two comma-separated values, got: {raw}")
    return float(pieces[0]), float(pieces[1])


def parse_int_pair(raw: str) -> tuple[int, int]:
    pieces = [piece.strip() for piece in raw.split(",") if piece.strip()]
    if len(pieces) != 2:
        raise ValueError(f"Expected two comma-separated integer values, got: {raw}")
    return int(pieces[0]), int(pieces[1])


def parse_plot_styles(raw: str) -> list[str]:
    valid = {"county", "dynamic_exp", "dynamic_lin"}
    styles = [piece.strip() for piece in raw.split(",") if piece.strip()]
    if not styles:
        raise ValueError("Expected at least one plot style")
    unknown = [style for style in styles if style not in valid]
    if unknown:
        raise ValueError(f"Unknown plot styles: {', '.join(unknown)}")
    return styles


def floor_to_hrrr_block(ts: pd.Timestamp) -> pd.Timestamp:
    hour = (ts.hour // 6) * 6
    return ts.floor("D") + pd.Timedelta(hours=hour)


def hrrr_filename(block_start: pd.Timestamp) -> str:
    return f"{block_start:%Y%m%d}_{block_start:%H}-{block_start.hour + 5:02d}_hrrr"


def required_met_files(start_time: pd.Timestamp, end_time: pd.Timestamp) -> list[MetFile]:
    block_start = floor_to_hrrr_block(start_time)
    block_end = floor_to_hrrr_block(end_time)

    files: list[MetFile] = []
    current = block_start
    while current <= block_end:
        files.append(MetFile(start=current, filename=hrrr_filename(current)))
        current += pd.Timedelta(hours=6)
    return files


def ensure_batch_support_files(output_root: Path, hysplit_root: Path) -> None:
    target = hysplit_root / "bdyfiles"
    link_path = output_root / "bdyfiles"
    if link_path.is_symlink():
        try:
            if link_path.resolve(strict=True) == target.resolve(strict=True):
                return
        except FileNotFoundError:
            pass
        link_path.unlink()
    elif os.path.lexists(link_path):
        return
    os.symlink(target, link_path, target_is_directory=True)


def refresh_symlink(link_path: Path, target: Path) -> None:
    if os.path.lexists(link_path):
        try:
            link_path.unlink()
        except FileNotFoundError:
            pass
    os.symlink(target, link_path, target_is_directory=target.is_dir())


def update_latest_pointers(output_root: Path, run_dir: Path) -> None:
    latest_dir = output_root / "latest"
    latest_dir.mkdir(exist_ok=True)
    refresh_symlink(latest_dir / "run", run_dir.resolve())
    (latest_dir / "latest_run.txt").write_text(str(run_dir.resolve()) + "\n", encoding="utf-8")


def format_duration(hours: float) -> str:
    total_minutes = int(round(hours * 60))
    hh, mm = divmod(total_minutes, 60)
    return f"{hh:02d} {mm:02d} 00"


def format_sampling_interval(hours: float) -> str:
    total_minutes = int(round(hours * 60))
    hh, mm = divmod(total_minutes, 60)
    return f"0 {hh:02d} {mm:02d}"


def format_hysplit_datetime(ts: pd.Timestamp | None) -> str:
    if ts is None:
        return "00 00 00 00 00"
    return ts.strftime("%y %m %d %H %M")


def meters_to_latlon_offsets(east_m: float, north_m: float, center_lat_deg: float) -> tuple[float, float]:
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = meters_per_deg_lat * max(math.cos(math.radians(center_lat_deg)), 1.0e-6)
    return north_m / meters_per_deg_lat, east_m / meters_per_deg_lon


def build_source_specs(
    source_geometry: str,
    source_lat: float,
    source_lon: float,
    source_height_m: float,
    emission_rate: float,
    source_footprint_m: tuple[float, float],
    source_grid_shape: tuple[int, int],
    source_rotation_deg: float,
) -> list[SourceSpec]:
    if source_geometry == "point":
        return [SourceSpec(lat=source_lat, lon=source_lon, height_m=source_height_m)]

    nx, ny = source_grid_shape
    if nx < 1 or ny < 1:
        raise ValueError("--source-grid-shape values must both be at least 1")
    footprint_x_m, footprint_y_m = source_footprint_m
    if footprint_x_m <= 0 or footprint_y_m <= 0:
        raise ValueError("--source-footprint-m values must both be positive")

    xs = [0.0] if nx == 1 else list(np.linspace(-footprint_x_m / 2.0, footprint_x_m / 2.0, nx))
    ys = [0.0] if ny == 1 else list(np.linspace(-footprint_y_m / 2.0, footprint_y_m / 2.0, ny))
    theta = math.radians(source_rotation_deg)
    cos_t = math.cos(theta)
    sin_t = math.sin(theta)

    per_source_rate = emission_rate / float(nx * ny)
    per_source_area = (footprint_x_m * footprint_y_m) / float(nx * ny)
    specs: list[SourceSpec] = []
    for y_m in ys:
        for x_m in xs:
            east_m = x_m * cos_t - y_m * sin_t
            north_m = x_m * sin_t + y_m * cos_t
            dlat, dlon = meters_to_latlon_offsets(east_m, north_m, source_lat)
            specs.append(
                SourceSpec(
                    lat=source_lat + dlat,
                    lon=source_lon + dlon,
                    height_m=source_height_m,
                    emission_rate=per_source_rate,
                    emission_area_m2=per_source_area,
                )
            )
    return specs


def build_geometry_suffix(source_geometry: str, source_grid_shape: tuple[int, int]) -> str:
    if source_geometry == "point":
        return ""
    return f"_srcarea{source_grid_shape[0]}x{source_grid_shape[1]}"


def write_control(
    control_path: Path,
    start_time: pd.Timestamp,
    run_hours: float,
    source_specs: list[SourceSpec],
    hrrr_dir: Path,
    met_files: list[MetFile],
    pollutant_name: str,
    emission_rate: float,
    emission_hours: float,
    release_start_time: pd.Timestamp | None,
    grid_center_lat: float,
    grid_center_lon: float,
    grid_spacing_deg: tuple[float, float],
    grid_span_deg: tuple[float, float],
    concentration_level_m: float,
    sampling_interval_hours: float,
    sample_start_time: pd.Timestamp | None,
    sample_stop_time: pd.Timestamp | None,
) -> None:
    lines = [
        start_time.strftime("%y %m %d %H"),
        f"{len(source_specs)}",
        f"{int(round(run_hours))}",
        "0",
        "10000.0",
        f"{len(met_files)}",
    ]

    source_lines: list[str] = []
    for spec in source_specs:
        parts = [f"{spec.lat:.6f}", f"{spec.lon:.6f}", f"{spec.height_m:.1f}"]
        if spec.emission_rate is not None:
            parts.append(f"{spec.emission_rate:.6g}")
        if spec.emission_area_m2 is not None:
            parts.append(f"{spec.emission_area_m2:.1f}")
        source_lines.append(" ".join(parts))
    lines[2:2] = source_lines

    met_dir = str(hrrr_dir.resolve()) + "/"
    for met_file in met_files:
        lines.extend([met_dir, met_file.filename])

    lines.extend(
        [
            "1",
            pollutant_name[:4].upper().ljust(4),
            f"{emission_rate:.6g}",
            f"{emission_hours:.3f}",
            format_hysplit_datetime(release_start_time),
            "1",
            f"{grid_center_lat:.4f} {grid_center_lon:.4f}",
            f"{grid_spacing_deg[0]:.4f} {grid_spacing_deg[1]:.4f}",
            f"{grid_span_deg[0]:.4f} {grid_span_deg[1]:.4f}",
            "./",
            "cdump",
            "1",
            f"{concentration_level_m:.1f}",
            format_hysplit_datetime(sample_start_time),
            format_hysplit_datetime(sample_stop_time),
            format_sampling_interval(sampling_interval_hours),
            "1",
            "0.0 0.0 0.0",
            "0.0 0.0 0.0 0.0 0.0",
            "0.0 0.0 0.0",
            "0.0",
            "0.0",
        ]
    )
    control_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_setup_cfg(setup_path: Path, numpar: int, maxpar: int) -> None:
    setup = "\n".join(
        [
            "&SETUP",
            "initd = 4,",
            "khmax = 9999,",
            f"numpar = {numpar},",
            f"maxpar = {maxpar},",
            "/",
        ]
    )
    setup_path.write_text(setup + "\n", encoding="ascii")


def build_concplot_command(hysplit_root: Path, style: str, frame_files: bool) -> str:
    concplot = hysplit_root / "exec" / "concplot"
    arlmap = hysplit_root / "graphics" / "arlmap"
    frame_opt = "-f1 " if frame_files else ""

    if style == "county":
        values = "1:USER-1:255255000+4:USER-2:255165000+40:USER-3:255000000"
        return (
            f'"{concplot}" '
            "-icdump "
            f'-j"{arlmap}" '
            "-c4 "
            f'-v{values} '
            "-k1 "
            "-81 "
            f"{frame_opt}"
            "-oplume_map.ps"
        )

    if style == "dynamic_exp":
        return (
            f'"{concplot}" '
            "-icdump "
            f'-j"{arlmap}" '
            "-c0:6 "
            "-3 1 "
            "-k1 "
            "-81 "
            f"{frame_opt}"
            "-oplume_dynamic_exp.ps"
        )

    if style == "dynamic_lin":
        return (
            f'"{concplot}" '
            "-icdump "
            f'-j"{arlmap}" '
            "-c2:6 "
            "-3 1 "
            "-k1 "
            "-81 "
            f"{frame_opt}"
            "-oplume_dynamic_lin.ps"
        )

    raise ValueError(f"Unsupported plot style: {style}")


def write_plot_script(plot_script_path: Path, hysplit_root: Path, style: str, frame_files: bool) -> None:
    command = build_concplot_command(hysplit_root, style=style, frame_files=frame_files)
    output_stem = {
        "county": "plume_map",
        "dynamic_exp": "plume_dynamic_exp",
        "dynamic_lin": "plume_dynamic_lin",
    }[style]
    script = "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            command,
            f'if command -v ps2pdf >/dev/null 2>&1 && [ -f {output_stem}.ps ]; then ps2pdf {output_stem}.ps {output_stem}.pdf; fi',
        ]
    )
    plot_script_path.write_text(script + "\n", encoding="ascii")
    plot_script_path.chmod(0o755)


def main() -> None:
    args = parse_args()

    start_time = pd.Timestamp(args.start_utc, tz="UTC")
    end_time = pd.Timestamp(args.end_utc, tz="UTC")
    if end_time <= start_time:
        raise ValueError("--end-utc must be later than --start-utc")
    release_start_time = pd.Timestamp(args.release_start_utc, tz="UTC") if args.release_start_utc else start_time
    sample_start_time = pd.Timestamp(args.sample_start_utc, tz="UTC") if args.sample_start_utc else None
    sample_stop_time = pd.Timestamp(args.sample_stop_utc, tz="UTC") if args.sample_stop_utc else None
    if release_start_time < start_time:
        raise ValueError("--release-start-utc cannot be earlier than --start-utc")
    if release_start_time > end_time:
        raise ValueError("--release-start-utc must be on or before --end-utc")
    if sample_start_time is not None and sample_start_time < start_time:
        raise ValueError("--sample-start-utc cannot be earlier than --start-utc")
    if sample_stop_time is not None and sample_stop_time > end_time:
        raise ValueError("--sample-stop-utc cannot be later than --end-utc")
    if sample_start_time is not None and sample_stop_time is not None and sample_stop_time <= sample_start_time:
        raise ValueError("--sample-stop-utc must be later than --sample-start-utc")

    run_hours = (end_time - start_time).total_seconds() / 3600.0
    emission_default_hours = (end_time - release_start_time).total_seconds() / 3600.0
    emission_hours = args.emission_hours if args.emission_hours is not None else emission_default_hours
    sampling_interval_hours = args.sampling_interval_hours
    if emission_hours <= 0 or sampling_interval_hours <= 0:
        raise ValueError("Emission and sampling intervals must be positive")
    if args.numpar < 1 or args.maxpar < args.numpar:
        raise ValueError("--numpar must be positive and --maxpar must be >= --numpar")

    grid_spacing_deg = parse_pair(args.grid_spacing_deg)
    grid_span_deg = parse_pair(args.grid_span_deg)
    source_footprint_m = parse_pair(args.source_footprint_m)
    source_grid_shape = parse_int_pair(args.source_grid_shape)
    plot_styles = parse_plot_styles(args.plot_styles)
    source_specs = build_source_specs(
        source_geometry=args.source_geometry,
        source_lat=args.source_lat,
        source_lon=args.source_lon,
        source_height_m=args.source_height_m,
        emission_rate=args.emission_rate,
        source_footprint_m=source_footprint_m,
        source_grid_shape=source_grid_shape,
        source_rotation_deg=args.source_rotation_deg,
    )

    hrrr_dir = args.hrrr_dir.resolve()
    hysplit_root = args.hysplit_root.resolve()
    hycs_std = hysplit_root / "exec" / "hycs_std"
    if not hycs_std.exists():
        raise FileNotFoundError(f"Could not find hycs_std at {hycs_std}")

    met_files = required_met_files(start_time=start_time, end_time=end_time)
    missing_met = [mf.filename for mf in met_files if not (hrrr_dir / mf.filename).exists()]

    args.output_root.mkdir(parents=True, exist_ok=True)
    ensure_batch_support_files(args.output_root, hysplit_root)

    run_dir = args.output_root / (
        f"{args.run_tag}_t{start_time:%Y%m%d%H}_to_{end_time:%Y%m%d%H}_"
        f"h{int(round(args.source_height_m)):04d}"
        f"{build_geometry_suffix(args.source_geometry, source_grid_shape)}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    control_path = run_dir / "CONTROL"
    setup_path = run_dir / "SETUP.CFG"
    log_path = run_dir / "run.log"
    cdump_path = run_dir / "cdump"

    write_control(
        control_path=control_path,
        start_time=start_time,
        run_hours=run_hours,
        source_specs=source_specs,
        hrrr_dir=hrrr_dir,
        met_files=met_files,
        pollutant_name=args.pollutant_name,
        emission_rate=args.emission_rate,
        emission_hours=emission_hours,
        release_start_time=release_start_time,
        grid_center_lat=args.grid_center_lat,
        grid_center_lon=args.grid_center_lon,
        grid_spacing_deg=grid_spacing_deg,
        grid_span_deg=grid_span_deg,
        concentration_level_m=args.concentration_level_m,
        sampling_interval_hours=sampling_interval_hours,
        sample_start_time=sample_start_time,
        sample_stop_time=sample_stop_time,
    )
    write_setup_cfg(setup_path, numpar=args.numpar, maxpar=args.maxpar)
    plot_script_map = {
        "county": run_dir / "plot_county_thresholds.sh",
        "dynamic_exp": run_dir / "plot_dynamic_exponential.sh",
        "dynamic_lin": run_dir / "plot_dynamic_linear.sh",
    }
    for style in plot_styles:
        write_plot_script(plot_script_map[style], hysplit_root, style=style, frame_files=args.plot_frames)

    # Keep the historical script name as an alias to the county-threshold plot for compatibility.
    legacy_plot_script_path = run_dir / "plot_concentration.sh"
    if "county" in plot_styles:
        legacy_plot_script_path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\nbash ./plot_county_thresholds.sh\n",
            encoding="ascii",
        )
        legacy_plot_script_path.chmod(0o755)

    if missing_met:
        log_path.write_text("Missing meteorology files:\n" + "\n".join(missing_met) + "\n", encoding="utf-8")
        raise FileNotFoundError(
            "Missing required HRRR files for this window: " + ", ".join(missing_met)
        )

    if args.dry_run:
        print(f"Wrote CONTROL and SETUP.CFG to {run_dir}")
        print(f"Run duration: {run_hours:.2f} hours")
        print(f"Release start: {release_start_time}")
        print(f"Source geometry: {args.source_geometry} ({len(source_specs)} release points)")
        if sample_start_time is not None or sample_stop_time is not None:
            print(f"Sampling window: {sample_start_time} to {sample_stop_time}")
        update_latest_pointers(args.output_root, run_dir)
        print("Plot commands:")
        for style in plot_styles:
            print(f"  {style}: {plot_script_map[style]}")
        return

    proc = subprocess.run(
        [str(hycs_std)],
        cwd=run_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log_path.write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0:
        raise RuntimeError(f"hycs_std failed with exit code {proc.returncode}. See {log_path}")
    if not cdump_path.exists() or cdump_path.stat().st_size == 0:
        raise RuntimeError(f"hycs_std completed without a usable cdump file. See {log_path}")

    if args.plot:
        for style in plot_styles:
            script_path = plot_script_map[style]
            plot_proc = subprocess.run(
                ["bash", str(script_path)],
                cwd=run_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
            plot_log_path = run_dir / f"plot_{style}.log"
            plot_log_path.write_text(plot_proc.stdout, encoding="utf-8")
            if plot_proc.returncode != 0:
                raise RuntimeError(f"concplot failed for style {style} with exit code {plot_proc.returncode}. See {plot_log_path}")

    update_latest_pointers(args.output_root, run_dir)
    print(f"Completed forward dispersion run in {run_dir}")
    print(f"Met files: {', '.join(mf.filename for mf in met_files)}")
    print(f"Release start: {release_start_time}")
    print(f"Source geometry: {args.source_geometry} ({len(source_specs)} release points)")
    if sample_start_time is not None or sample_stop_time is not None:
        print(f"Sampling window: {sample_start_time} to {sample_stop_time}")
    print("Plot commands:")
    for style in plot_styles:
        print(f"  {style}: {plot_script_map[style]}")


if __name__ == "__main__":
    main()
