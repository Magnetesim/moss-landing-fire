#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from moss_landing.paths import DATA_DIR


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pre-clean PurpleAir data before interpolation or enhancement analysis."
    )
    parser.add_argument("--input-csv", type=Path, default=DATA_DIR / "mbuapcd_pm25.csv")
    parser.add_argument("--sensor-csv", type=Path, default=DATA_DIR / "sensors_mbuapcd_active.csv")
    parser.add_argument("--output-csv", type=Path, default=DATA_DIR / "mbuapcd_pm25_cleaned.csv")
    parser.add_argument("--output-sensors", type=Path, default=DATA_DIR / "sensors_mbuapcd_active_cleaned.csv")
    parser.add_argument("--sensor-report", type=Path, default=DATA_DIR / "mbuapcd_cleaning_sensor_report.csv")
    parser.add_argument("--row-report", type=Path, default=DATA_DIR / "mbuapcd_cleaning_row_report.csv")
    parser.add_argument(
        "--stuck-threshold",
        type=float,
        default=1000.0,
        help="Whole-sensor removal threshold for extremely high stuck values.",
    )
    parser.add_argument(
        "--stuck-fraction",
        type=float,
        default=0.9,
        help="Whole-sensor removal fraction for --stuck-threshold.",
    )
    parser.add_argument(
        "--spiky-threshold",
        type=float,
        default=500.0,
        help="Whole-sensor removal threshold for repeated extreme spikes.",
    )
    parser.add_argument(
        "--spiky-fraction",
        type=float,
        default=0.05,
        help="Whole-sensor removal fraction for --spiky-threshold on otherwise low-median sensors.",
    )
    parser.add_argument(
        "--spiky-median-max",
        type=float,
        default=60.0,
        help="Only classify a sensor as globally spiky if its median is at or below this value.",
    )
    parser.add_argument(
        "--row-outlier-threshold",
        type=float,
        default=500.0,
        help="Single-row outlier threshold for otherwise retained sensors.",
    )
    parser.add_argument(
        "--row-outlier-multiplier",
        type=float,
        default=15.0,
        help="Single-row outlier multiplier over the sensor median.",
    )
    return parser.parse_args()


def summarize_sensors(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("sensor_index")["pm2.5_atm"]
    summary = grouped.agg(["count", "min", "median", "max", "mean"]).reset_index()
    summary["std"] = grouped.std().to_numpy()
    summary["gt250_frac"] = grouped.apply(lambda s: (s > 250).mean()).to_numpy()
    summary["gt500_frac"] = grouped.apply(lambda s: (s > 500).mean()).to_numpy()
    summary["gt1000_frac"] = grouped.apply(lambda s: (s > 1000).mean()).to_numpy()
    return summary


def main() -> None:
    args = parse_args()
    sensors = pd.read_csv(args.sensor_csv)
    df = pd.read_csv(args.input_csv)
    df["time_stamp"] = pd.to_datetime(df["time_stamp"], utc=True)

    summary = summarize_sensors(df).merge(
        sensors[["sensor_index", "name", "latitude", "longitude"]],
        on="sensor_index",
        how="left",
    )

    summary["remove_reason"] = ""
    stuck_mask = summary["gt1000_frac"] >= args.stuck_fraction
    summary.loc[stuck_mask, "remove_reason"] = "stuck_high"

    spiky_mask = (
        (summary["remove_reason"] == "")
        & (summary["median"] <= args.spiky_median_max)
        & (summary["gt500_frac"] >= args.spiky_fraction)
    )
    summary.loc[spiky_mask, "remove_reason"] = "repeated_extreme_spikes"

    removed_sensor_ids = set(summary.loc[summary["remove_reason"] != "", "sensor_index"].tolist())
    kept_sensor_summary = summary.loc[~summary["sensor_index"].isin(removed_sensor_ids)].copy()

    kept_df = df.loc[~df["sensor_index"].isin(removed_sensor_ids)].copy()
    median_lookup = kept_sensor_summary.set_index("sensor_index")["median"]
    kept_df["sensor_median_pm25"] = kept_df["sensor_index"].map(median_lookup)
    row_outlier_mask = (
        (kept_df["pm2.5_atm"] >= args.row_outlier_threshold)
        & (kept_df["pm2.5_atm"] >= args.row_outlier_multiplier * kept_df["sensor_median_pm25"].clip(lower=1.0))
        & (kept_df["sensor_median_pm25"] <= args.spiky_median_max)
    )

    row_report = kept_df.loc[row_outlier_mask, [
        "time_stamp",
        "sensor_index",
        "pm2.5_atm",
        "pm2.5_cf_1",
        "humidity",
        "sensor_median_pm25",
    ]].merge(
        sensors[["sensor_index", "name", "latitude", "longitude"]],
        on="sensor_index",
        how="left",
    )
    row_report["remove_reason"] = "single_row_extreme_outlier"

    cleaned_df = kept_df.loc[~row_outlier_mask].drop(columns=["sensor_median_pm25"]).copy()
    cleaned_sensors = sensors.loc[~sensors["sensor_index"].isin(removed_sensor_ids)].copy()

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    cleaned_df.to_csv(args.output_csv, index=False)
    cleaned_sensors.to_csv(args.output_sensors, index=False)
    summary.to_csv(args.sensor_report, index=False)
    row_report.to_csv(args.row_report, index=False)

    print(f"Input rows: {len(df)}")
    print(f"Input sensors: {df['sensor_index'].nunique()}")
    print(f"Removed whole sensors: {len(removed_sensor_ids)}")
    if removed_sensor_ids:
        removed = summary.loc[summary['remove_reason'] != '', ['sensor_index', 'name', 'remove_reason', 'median', 'max', 'gt500_frac', 'gt1000_frac']]
        print(removed.to_string(index=False))
    print(f"Removed single rows: {len(row_report)}")
    print(f"Output rows: {len(cleaned_df)}")
    print(f"Output sensors: {cleaned_df['sensor_index'].nunique()}")
    print(f"Saved cleaned data to {args.output_csv}")
    print(f"Saved cleaned sensor metadata to {args.output_sensors}")
    print(f"Saved sensor report to {args.sensor_report}")
    print(f"Saved row report to {args.row_report}")


if __name__ == "__main__":
    main()
