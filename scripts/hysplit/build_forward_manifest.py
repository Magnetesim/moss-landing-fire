#!/usr/bin/env python3
"""Build a deterministic, cluster-ready forward HYSPLIT run manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from moss_landing.constants import DEFAULT_IGNITION_UTC, MOSS_LANDING_LAT, MOSS_LANDING_LON
from moss_landing.paths import DEFAULT_HYSPLIT_ROOT, HRRR_DIR as DEFAULT_HRRR_DIR, PROJECT_ROOT

DEFAULT_RUNS_ROOT = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "manifest_rows"
DEFAULT_MANIFEST = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "phase1_forward_manifest.csv"
DEFAULT_FORWARD_SCRIPT = PROJECT_ROOT / "scripts" / "hysplit" / "run_forward_dispersion.py"

DEFAULT_SOURCE_SETUPS = "point|300,120|1,1;area_grid|300,120|5,3;area_grid|600,240|7,3;area_grid|900,360|9,5"
DEFAULT_SOURCE_HEIGHTS_M = "10,25,50,100,150,250"
DEFAULT_RELEASE_DURATIONS_H = "4,8,12,24"
DEFAULT_WINDOW_INDICES = "1,4,7,10"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--runs-root", type=Path, default=DEFAULT_RUNS_ROOT)
    parser.add_argument("--forward-script", type=Path, default=DEFAULT_FORWARD_SCRIPT)
    parser.add_argument("--hrrr-dir", type=Path, default=DEFAULT_HRRR_DIR)
    parser.add_argument("--hysplit-root", type=Path, default=DEFAULT_HYSPLIT_ROOT)
    parser.add_argument("--ignition-utc", default=DEFAULT_IGNITION_UTC)
    parser.add_argument("--source-heights-m", default=DEFAULT_SOURCE_HEIGHTS_M)
    parser.add_argument("--release-durations-h", default=DEFAULT_RELEASE_DURATIONS_H)
    parser.add_argument("--source-setups", default=DEFAULT_SOURCE_SETUPS)
    parser.add_argument("--window-indices", default=DEFAULT_WINDOW_INDICES)
    parser.add_argument("--execution-shape", choices=("combined", "separate", "cumulative"), default="combined")
    parser.add_argument("--window-hours", type=float, default=4.0)
    parser.add_argument("--window-step-hours", type=float, default=4.0)
    parser.add_argument("--run-tag-prefix", default="phase1")
    parser.add_argument("--source-lat", type=float, default=MOSS_LANDING_LAT)
    parser.add_argument("--source-lon", type=float, default=MOSS_LANDING_LON)
    parser.add_argument("--source-rotation-deg", type=float, default=0.0)
    parser.add_argument("--emission-rate", type=float, default=1.0)
    parser.add_argument("--concentration-level-m", type=float, default=10.0)
    parser.add_argument("--grid-center-lat", type=float, default=36.82)
    parser.add_argument("--grid-center-lon", type=float, default=-121.80)
    parser.add_argument("--grid-spacing-deg", default="0.01,0.01")
    parser.add_argument("--grid-span-deg", default="1.40,1.20")
    parser.add_argument("--numpar", type=int, default=500)
    parser.add_argument("--maxpar", type=int, default=50000)
    parser.add_argument("--krand", type=int, choices=(0, 1, 2, 3, 4, 10, 11, 12, 13), default=2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument(
        "--vary-seed-by-replicate",
        action="store_true",
        help="Increment SEED for each replicate; otherwise replicates use the same seed for determinism tests.",
    )
    parser.add_argument("--plot-styles", default="county")
    return parser.parse_args()


def parse_numbers(raw: str, cast: type[float] | type[int]) -> list[float] | list[int]:
    values = [cast(value.strip()) for value in raw.split(",") if value.strip()]
    if not values:
        raise ValueError("Expected at least one comma-separated value")
    return values


def parse_source_setups(raw: str) -> list[dict[str, str]]:
    setups: list[dict[str, str]] = []
    for chunk in raw.split(";"):
        parts = [part.strip() for part in chunk.split("|")]
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"Bad source setup {chunk!r}; use geometry|footprint|grid_shape")
        geometry, footprint, grid_shape = parts
        if geometry not in {"point", "area_grid"}:
            raise ValueError(f"Unsupported source geometry: {geometry}")
        setups.append({"source_geometry": geometry, "source_footprint_m": footprint, "source_grid_shape": grid_shape})
    if not setups:
        raise ValueError("No source setups configured")
    return setups


def as_utc(raw: str) -> pd.Timestamp:
    value = pd.Timestamp(raw)
    return value.tz_localize("UTC") if value.tzinfo is None else value.tz_convert("UTC")


def token(value: float) -> str:
    return f"{value:g}".replace(".", "p").replace("-", "m")


def scenario_tag(height: float, duration: float, setup: dict[str, str]) -> str:
    geometry = "pt" if setup["source_geometry"] == "point" else "area" + setup["source_grid_shape"].replace(",", "x")
    pieces = [f"h{token(height)}", f"dur{token(duration)}", geometry]
    if setup["source_geometry"] == "area_grid":
        pieces.append("fp" + setup["source_footprint_m"].replace(",", "x"))
    return "_".join(pieces)


def iso(value: pd.Timestamp) -> str:
    return value.isoformat().replace("+00:00", "Z")


def config_hash(config: dict[str, object]) -> str:
    payload = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_rows(args: argparse.Namespace) -> list[dict[str, object]]:
    ignition = as_utc(args.ignition_utc)
    heights = parse_numbers(args.source_heights_m, float)
    durations = parse_numbers(args.release_durations_h, float)
    windows = parse_numbers(args.window_indices, int)
    setups = parse_source_setups(args.source_setups)
    if args.window_hours <= 0 or args.window_step_hours <= 0:
        raise ValueError("Window hours and step must be positive")
    if args.replicates < 1:
        raise ValueError("--replicates must be at least 1")

    all_windows = [
        (index, ignition + pd.Timedelta(hours=index * args.window_step_hours), ignition + pd.Timedelta(hours=(index * args.window_step_hours) + args.window_hours))
        for index in windows
    ]
    rows: list[dict[str, object]] = []
    for height in heights:
        for duration in durations:
            for setup in setups:
                if args.execution_shape == "combined":
                    groups = [all_windows]
                elif args.execution_shape == "separate":
                    groups = [[window] for window in all_windows]
                else:
                    first_start = all_windows[0][1]
                    groups = [[(window[0], first_start, window[2])] for window in all_windows]
                for group in groups:
                    sample_start = min(window[1] for window in group)
                    sample_stop = max(window[2] for window in group)
                    logical_windows = ",".join(str(window[0]) for window in group)
                    base_row = {
                        "manifest_version": 2,
                        "execution_shape": args.execution_shape,
                        "scenario_tag": scenario_tag(height, duration, setup),
                        "logical_window_indices": logical_windows,
                        "simulation_start_utc": iso(ignition),
                        "simulation_end_utc": iso(sample_stop),
                        "release_start_utc": iso(ignition),
                        "release_end_utc": iso(ignition + pd.Timedelta(hours=duration)),
                        "sample_start_utc": iso(sample_start),
                        "sample_stop_utc": iso(sample_stop),
                        "source_lat": args.source_lat,
                        "source_lon": args.source_lon,
                        "source_height_m": height,
                        "source_geometry": setup["source_geometry"],
                        "source_footprint_m": setup["source_footprint_m"],
                        "source_grid_shape": setup["source_grid_shape"],
                        "source_rotation_deg": args.source_rotation_deg,
                        "emission_rate": args.emission_rate,
                        "emission_hours": duration,
                        "concentration_level_m": args.concentration_level_m,
                        "grid_center_lat": args.grid_center_lat,
                        "grid_center_lon": args.grid_center_lon,
                        "grid_spacing_deg": args.grid_spacing_deg,
                        "grid_span_deg": args.grid_span_deg,
                        "sampling_interval_hours": args.window_hours,
                        "numpar": args.numpar,
                        "maxpar": args.maxpar,
                        "krand": args.krand,
                        "plot_styles": args.plot_styles,
                        "hrrr_dir": str(args.hrrr_dir.resolve()),
                        "hysplit_root": str(args.hysplit_root.resolve()),
                        "forward_script": str(args.forward_script.resolve()),
                    }
                    for replicate_index in range(args.replicates):
                        row = dict(base_row)
                        row["replicate_index"] = replicate_index
                        row["seed"] = args.seed + replicate_index if args.vary_seed_by_replicate else args.seed
                        digest = config_hash(row)
                        run_tag = f"{args.run_tag_prefix}_{row['scenario_tag']}_r{replicate_index:02d}_{digest[:12]}"
                        row_output_root = args.runs_root.resolve() / digest
                        geometry_suffix = "" if setup["source_geometry"] == "point" else "_srcarea" + setup["source_grid_shape"].replace(",", "x")
                        expected_run_dir = row_output_root / (
                            f"{run_tag}_t{ignition:%Y%m%d%H}_to_{sample_stop:%Y%m%d%H}_h{int(round(height)):04d}{geometry_suffix}"
                        )
                        row.update(
                            {
                                "config_hash": digest,
                                "run_tag": run_tag,
                                "row_output_root": str(row_output_root),
                                "expected_run_dir": str(expected_run_dir),
                                "status_path": str(row_output_root / "row_status.json"),
                            }
                        )
                        rows.append(row)
    return rows


def main() -> None:
    args = parse_args()
    rows = build_rows(args)
    frame = pd.DataFrame(rows).sort_values(["scenario_tag", "sample_start_utc", "config_hash"]).reset_index(drop=True)
    frame.insert(0, "row_index", frame.index)
    if frame["config_hash"].duplicated().any():
        raise RuntimeError("Manifest contains duplicate configuration hashes")
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.manifest, index=False)
    print(f"Wrote {len(frame)} physical runs to {args.manifest}")
    print(f"Execution shape: {args.execution_shape}; logical comparisons: {len(frame) * (len(parse_numbers(args.window_indices, int)) if args.execution_shape == 'combined' else 1)}")


if __name__ == "__main__":
    main()
