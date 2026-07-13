#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from moss_landing.paths import DATA_DIR

DEFAULT_INPUT_CSV = DATA_DIR / "mbuapcd_pm25_cleaned.csv"
DEFAULT_SENSOR_CSV = DATA_DIR / "sensors_mbuapcd_active_cleaned.csv"
DEFAULT_OUTPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement.csv"
DEFAULT_BASELINE_CSV = DATA_DIR / "mbuapcd_sensor_baselines.csv"
DEFAULT_PREFIRE_END_UTC = "2025-01-17T02:00:00Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a per-sensor baseline and enhancement dataset from cleaned PurpleAir data."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--sensor-csv", type=Path, default=DEFAULT_SENSOR_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--baseline-csv", type=Path, default=DEFAULT_BASELINE_CSV)
    parser.add_argument(
        "--prefire-end-utc",
        default=DEFAULT_PREFIRE_END_UTC,
        help="Rows strictly earlier than this UTC timestamp are used to compute the baseline.",
    )
    parser.add_argument(
        "--baseline-stat",
        choices=("median", "mean"),
        default="median",
        help="Statistic used for the first-pass per-sensor baseline.",
    )
    parser.add_argument(
        "--min-prefire-points",
        type=int,
        default=24,
        help="Minimum number of pre-fire hourly values required to trust a sensor baseline.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    df = pd.read_csv(args.input_csv)
    sensors = pd.read_csv(args.sensor_csv)
    df["time_stamp"] = pd.to_datetime(df["time_stamp"], utc=True)
    prefire_end = pd.Timestamp(args.prefire_end_utc, tz="UTC")

    df = df.merge(
        sensors[["sensor_index", "name", "latitude", "longitude"]],
        on="sensor_index",
        how="left",
        validate="many_to_one",
    )

    prefire = df.loc[df["time_stamp"] < prefire_end].copy()
    grouped = prefire.groupby("sensor_index")["pm2.5_atm"]
    baseline_values = grouped.median() if args.baseline_stat == "median" else grouped.mean()
    baseline_counts = grouped.size()

    baselines = (
        pd.DataFrame(
            {
                "sensor_index": baseline_values.index,
                "baseline_pm25": baseline_values.to_numpy(),
                "prefire_count": baseline_counts.reindex(baseline_values.index).to_numpy(),
            }
        )
        .merge(sensors[["sensor_index", "name", "latitude", "longitude"]], on="sensor_index", how="left")
        .sort_values("sensor_index")
        .reset_index(drop=True)
    )
    baselines["baseline_ok"] = baselines["prefire_count"] >= args.min_prefire_points

    enriched = df.merge(
        baselines[["sensor_index", "baseline_pm25", "prefire_count", "baseline_ok"]],
        on="sensor_index",
        how="left",
        validate="many_to_one",
    )
    enriched["enhancement_pm25"] = enriched["pm2.5_atm"] - enriched["baseline_pm25"]
    enriched["enhancement_pm25_pos"] = enriched["enhancement_pm25"].clip(lower=0)
    enriched["local_time"] = enriched["time_stamp"].dt.tz_convert("US/Pacific")
    enriched["is_prefire_baseline_window"] = enriched["time_stamp"] < prefire_end

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    baselines.to_csv(args.baseline_csv, index=False)
    enriched.to_csv(args.output_csv, index=False)

    print(f"Baseline statistic: {args.baseline_stat}")
    print(f"Pre-fire cutoff: {prefire_end}")
    print(f"Sensors with baselines: {len(baselines)}")
    print(f"Sensors meeting min pre-fire points ({args.min_prefire_points}): {int(baselines['baseline_ok'].sum())}")
    print(f"Saved per-sensor baselines to {args.baseline_csv}")
    print(f"Saved enhancement dataset to {args.output_csv}")


if __name__ == "__main__":
    main()
