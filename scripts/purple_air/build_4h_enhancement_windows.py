#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
DEFAULT_INPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement.csv"
DEFAULT_OUTPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate hourly PurpleAir enhancement data into 4-hour sensor windows."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument(
        "--window-hours",
        type=int,
        default=4,
        help="Window size in hours for aggregation.",
    )
    parser.add_argument(
        "--origin-utc",
        default="2025-01-16T23:00:00Z",
        help="UTC origin used to align the windows, typically ignition time.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.window_hours < 1:
        raise ValueError("--window-hours must be at least 1")

    df = pd.read_csv(args.input_csv)
    df["time_stamp"] = pd.to_datetime(df["time_stamp"], utc=True)
    df["local_time"] = pd.to_datetime(df["local_time"], utc=True)
    origin = pd.Timestamp(args.origin_utc, tz="UTC")
    window_delta = pd.Timedelta(hours=args.window_hours)

    offset_hours = ((df["time_stamp"] - origin) / pd.Timedelta(hours=1)).astype(float)
    window_index = (offset_hours // args.window_hours).astype(int)
    df["window_index"] = window_index
    df["window_start_utc"] = origin + window_index * window_delta
    df["window_stop_utc"] = df["window_start_utc"] + window_delta
    df["window_start_local"] = df["window_start_utc"].dt.tz_convert("US/Pacific")
    df["window_stop_local"] = df["window_stop_utc"].dt.tz_convert("US/Pacific")

    grouped = df.groupby(
        [
            "window_index",
            "window_start_utc",
            "window_stop_utc",
            "window_start_local",
            "window_stop_local",
            "sensor_index",
            "name",
            "latitude",
            "longitude",
            "baseline_pm25",
            "baseline_ok",
        ],
        as_index=False,
    )

    windowed = grouped.agg(
        n_hours=("pm2.5_atm", "size"),
        pm25_mean=("pm2.5_atm", "mean"),
        pm25_max=("pm2.5_atm", "max"),
        enhancement_mean=("enhancement_pm25", "mean"),
        enhancement_pos_mean=("enhancement_pm25_pos", "mean"),
        enhancement_pos_max=("enhancement_pm25_pos", "max"),
        humidity_mean=("humidity", "mean"),
    )

    windowed["window_label_utc"] = (
        windowed["window_start_utc"].dt.strftime("%Y-%m-%d %H:%M")
        + " to "
        + windowed["window_stop_utc"].dt.strftime("%H:%M UTC")
    )
    windowed["window_label_local"] = (
        windowed["window_start_local"].dt.strftime("%b %d %I:%M %p")
        + " to "
        + windowed["window_stop_local"].dt.strftime("%I:%M %p PT")
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    windowed.to_csv(args.output_csv, index=False)

    print(f"Input rows: {len(df)}")
    print(f"Output sensor-window rows: {len(windowed)}")
    print(f"Distinct windows: {windowed['window_index'].nunique()}")
    print(f"Window size: {args.window_hours} hours")
    print(f"Origin UTC: {origin}")
    print(f"Saved 4-hour enhancement windows to {args.output_csv}")


if __name__ == "__main__":
    main()
