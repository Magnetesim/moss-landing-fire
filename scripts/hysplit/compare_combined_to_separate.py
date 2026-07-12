#!/usr/bin/env python3
"""Compare timestamp-matched concentration periods from combined and separate runs."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HYSPLIT_ROOT = PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-manifest", type=Path, required=True)
    parser.add_argument("--separate-manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def import_hysplitdata():
    root = Path(os.environ.get("HYSPLIT_ROOT", DEFAULT_HYSPLIT_ROOT))
    module_root = root / "python" / "hysplitdata"
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
    try:
        import hysplitdata  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(f"Could not import hysplitdata from {module_root}") from exc
    return hysplitdata


def as_utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


def logical_window_period(combined_row: pd.Series, window_index: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return the requested output period, independent of a row's sampling envelope."""
    interval = pd.Timedelta(hours=float(combined_row["sampling_interval_hours"]))
    start = as_utc(combined_row["sample_start_utc"]) + (window_index - 1) * interval
    return start, start + interval


def matching_time_index(cdump: object, start: object, stop: object) -> int:
    target = (as_utc(start), as_utc(stop))
    periods: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for grid in cdump.grids:
        periods.setdefault(grid.time_index, (as_utc(grid.starting_datetime), as_utc(grid.ending_datetime)))
    for index, period in periods.items():
        if period == target:
            return index
    available = ", ".join(f"{index}:{start.isoformat()}–{stop.isoformat()}" for index, (start, stop) in sorted(periods.items()))
    raise ValueError(f"No period matched {target[0].isoformat()}–{target[1].isoformat()}; available {available}")


def read_period(cdump_path: Path, start: object, stop: object, hysplitdata: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cdump = hysplitdata.read_cdump(str(cdump_path))
    index = matching_time_index(cdump, start, stop)
    pollutant = cdump.pollutants[0]
    level = next(grid.vert_level for grid in cdump.grids if grid.time_index == index and grid.pollutant == pollutant)
    grids = [grid.conc for grid in cdump.grids if grid.time_index == index and grid.pollutant == pollutant and grid.vert_level == level]
    return np.asarray(cdump.longitudes), np.asarray(cdump.latitudes), np.asarray(np.sum(grids, axis=0), dtype=float)


def metrics(combined: np.ndarray, separate: np.ndarray) -> dict[str, float | int | None]:
    combined_flat = combined.ravel()
    separate_flat = separate.ravel()
    active = (combined_flat > 0) | (separate_flat > 0)
    active_combined = combined_flat[active]
    active_separate = separate_flat[active]
    denominator = float(np.sum(np.abs(active_separate)))
    relative_l1 = float(np.sum(np.abs(active_combined - active_separate)) / denominator) if denominator else None
    normalized_tv = None
    combined_sum = float(np.sum(active_combined))
    separate_sum = float(np.sum(active_separate))
    if combined_sum > 0 and separate_sum > 0:
        normalized_tv = float(0.5 * np.sum(np.abs(active_combined / combined_sum - active_separate / separate_sum)))
    correlation = None
    if active_combined.size > 1 and np.std(active_combined) > 0 and np.std(active_separate) > 0:
        correlation = float(np.corrcoef(active_combined, active_separate)[0, 1])
    return {
        "active_cells": int(active.sum()),
        "combined_sum": combined_sum,
        "separate_sum": separate_sum,
        "sum_ratio_combined_over_separate": combined_sum / separate_sum if separate_sum else None,
        "relative_l1": relative_l1,
        "normalized_total_variation": normalized_tv,
        "active_cell_correlation": correlation,
        "max_absolute_difference": float(np.max(np.abs(active_combined - active_separate))) if active_combined.size else 0.0,
    }


def main() -> None:
    args = parse_args()
    hysplitdata = import_hysplitdata()
    combined = pd.read_csv(args.combined_manifest)
    separate = pd.read_csv(args.separate_manifest)
    required = {
        "scenario_tag",
        "logical_window_indices",
        "sample_start_utc",
        "sample_stop_utc",
        "sampling_interval_hours",
        "expected_run_dir",
    }
    for name, frame in (("combined", combined), ("separate", separate)):
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{name} manifest missing columns: {sorted(missing)}")

    comparisons: list[dict[str, object]] = []
    for _, combined_row in combined.iterrows():
        scenario = str(combined_row["scenario_tag"])
        separate_rows = separate.loc[separate["scenario_tag"] == scenario]
        if separate_rows.empty:
            raise ValueError(f"No separate rows for scenario {scenario}")
        combined_cdump = Path(combined_row["expected_run_dir"]) / "cdump"
        for _, separate_row in separate_rows.iterrows():
            window = str(separate_row["logical_window_indices"])
            if "," in window:
                raise ValueError(f"Separate manifest row has multiple logical windows: {window}")
            window_index = int(window)
            start, stop = logical_window_period(combined_row, window_index)
            separate_cdump = Path(separate_row["expected_run_dir"]) / "cdump"
            lon_a, lat_a, conc_a = read_period(combined_cdump, start, stop, hysplitdata)
            lon_b, lat_b, conc_b = read_period(separate_cdump, start, stop, hysplitdata)
            if not (np.allclose(lon_a, lon_b) and np.allclose(lat_a, lat_b) and conc_a.shape == conc_b.shape):
                raise ValueError(f"Grid mismatch for {scenario}, window {window}")
            comparisons.append(
                {
                    "scenario_tag": scenario,
                    "window_index": window_index,
                    "sample_start_utc": str(start),
                    "sample_stop_utc": str(stop),
                    "combined_cdump": str(combined_cdump),
                    "separate_cdump": str(separate_cdump),
                    **metrics(conc_a, conc_b),
                }
            )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {"combined_manifest": str(args.combined_manifest), "separate_manifest": str(args.separate_manifest), "comparisons": comparisons}
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Compared {len(comparisons)} timestamp-matched concentration periods")
    print(f"Wrote {args.output_json}")


if __name__ == "__main__":
    main()
