#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_PM25_PATH = PROJECT_ROOT / "data" / "purple_air" / "moss_landing_pm25.csv"
DEFAULT_SENSORS_PATH = PROJECT_ROOT / "data" / "purple_air" / "sensors_active.csv"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "purple_air" / "receptor_events.csv"
DEFAULT_FIRE_START_UTC = "2025-01-17T01:35:00Z"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract fire-related PurpleAir receptor events for HYSPLIT back-trajectories."
    )
    parser.add_argument("--pm25-csv", type=Path, default=DEFAULT_PM25_PATH)
    parser.add_argument("--sensors-csv", type=Path, default=DEFAULT_SENSORS_PATH)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--fire-start-utc",
        default=DEFAULT_FIRE_START_UTC,
        help="Fire start timestamp in UTC, e.g. 2025-01-17T01:35:00Z.",
    )
    parser.add_argument(
        "--baseline-end-utc",
        default=None,
        help="End of baseline period in UTC. Defaults to --fire-start-utc.",
    )
    parser.add_argument(
        "--baseline-start-utc",
        default=None,
        help="Optional start of baseline period in UTC. Defaults to earliest record.",
    )
    parser.add_argument(
        "--mad-multiplier",
        type=float,
        default=3.0,
        help="Threshold = baseline_median + mad_multiplier * robust_mad.",
    )
    parser.add_argument(
        "--absolute-threshold",
        type=float,
        default=20.0,
        help="Minimum PM2.5 threshold in ug/m3 to count as an event.",
    )
    parser.add_argument(
        "--mad-floor",
        type=float,
        default=2.0,
        help="Lower bound on robust MAD to avoid tiny thresholds.",
    )
    parser.add_argument(
        "--episode-gap-hours",
        type=float,
        default=2.0,
        help="Gap larger than this starts a new episode.",
    )
    parser.add_argument(
        "--min-event-hours",
        type=int,
        default=1,
        help="Minimum number of hourly records required to keep an event.",
    )
    return parser.parse_args()


def parse_timestamp(value: str | None, fallback: pd.Timestamp | None = None) -> pd.Timestamp:
    if value is None:
        if fallback is None:
            raise ValueError("Timestamp value is required")
        return fallback
    return pd.Timestamp(value, tz="UTC") if pd.Timestamp(value).tzinfo is None else pd.Timestamp(value).tz_convert("UTC")


def load_inputs(pm25_csv: Path, sensors_csv: Path) -> pd.DataFrame:
    pm = pd.read_csv(pm25_csv)
    pm["time_stamp"] = pd.to_datetime(pm["time_stamp"], utc=True)

    sensors = pd.read_csv(sensors_csv)
    sensor_cols = ["sensor_index", "name", "latitude", "longitude"]
    missing = [col for col in sensor_cols if col not in sensors.columns]
    if missing:
        raise ValueError(f"Missing required sensor columns: {missing}")

    sensors = sensors[sensor_cols].drop_duplicates()
    merged = pm.merge(sensors, on="sensor_index", how="left", validate="many_to_one")

    if merged[["name", "latitude", "longitude"]].isna().any().any():
        missing_rows = merged[merged["latitude"].isna()]["sensor_index"].nunique()
        raise ValueError(f"Missing sensor metadata for {missing_rows} sensors")

    return merged.sort_values(["sensor_index", "time_stamp"]).reset_index(drop=True)


def compute_baseline_stats(
    df: pd.DataFrame,
    baseline_start: pd.Timestamp | None,
    baseline_end: pd.Timestamp,
    mad_multiplier: float,
    absolute_threshold: float,
    mad_floor: float,
) -> pd.DataFrame:
    baseline = df[df["time_stamp"] < baseline_end].copy()
    if baseline_start is not None:
        baseline = baseline[baseline["time_stamp"] >= baseline_start]

    if baseline.empty:
        raise ValueError("No baseline rows available. Check --baseline-start-utc/--baseline-end-utc.")

    grouped = baseline.groupby("sensor_index")["pm2.5_atm"]
    stats = grouped.median().rename("baseline_median").to_frame()
    stats["baseline_mad_raw"] = grouped.apply(lambda s: np.median(np.abs(s - np.median(s))))
    stats["baseline_count"] = grouped.size()
    stats["robust_mad"] = (stats["baseline_mad_raw"] * 1.4826).clip(lower=mad_floor)
    stats["event_threshold"] = np.maximum(
        absolute_threshold,
        stats["baseline_median"] + mad_multiplier * stats["robust_mad"],
    )
    stats["baseline_source"] = "pre_fire_window"

    missing_sensor_ids = sorted(set(df["sensor_index"]) - set(stats.index))
    if missing_sensor_ids:
        fallback_rows: list[dict[str, object]] = []
        for sensor_index in missing_sensor_ids:
            series = df.loc[df["sensor_index"] == sensor_index, "pm2.5_atm"].dropna().sort_values()
            if series.empty:
                continue

            sample_size = max(6, int(np.ceil(len(series) * 0.25)))
            sample = series.iloc[:sample_size]
            baseline_median = float(sample.median())
            mad_raw = float(np.median(np.abs(sample - baseline_median)))
            robust_mad = max(mad_raw * 1.4826, mad_floor)
            fallback_rows.append(
                {
                    "sensor_index": sensor_index,
                    "baseline_median": baseline_median,
                    "baseline_mad_raw": mad_raw,
                    "baseline_count": int(len(sample)),
                    "robust_mad": robust_mad,
                    "event_threshold": max(absolute_threshold, baseline_median + mad_multiplier * robust_mad),
                    "baseline_source": "fallback_low_quantile",
                }
            )

        if fallback_rows:
            stats = pd.concat([stats.reset_index(), pd.DataFrame(fallback_rows)], ignore_index=True)
            return stats

    return stats.reset_index()


def extract_events(
    df: pd.DataFrame,
    baseline_stats: pd.DataFrame,
    fire_start: pd.Timestamp,
    episode_gap_hours: float,
    min_event_hours: int,
) -> pd.DataFrame:
    post_fire = df[df["time_stamp"] >= fire_start].copy()
    if post_fire.empty:
        raise ValueError("No post-fire rows available after the requested fire-start time.")

    post_fire = post_fire.merge(baseline_stats, on="sensor_index", how="left", validate="many_to_one")
    if post_fire["event_threshold"].isna().any():
        missing = post_fire[post_fire["event_threshold"].isna()]["sensor_index"].nunique()
        raise ValueError(f"Missing baseline statistics for {missing} sensors")

    flagged = post_fire[post_fire["pm2.5_atm"] >= post_fire["event_threshold"]].copy()
    if flagged.empty:
        return pd.DataFrame()

    flagged["gap_hours"] = (
        flagged.groupby("sensor_index")["time_stamp"].diff().dt.total_seconds().div(3600)
    )
    flagged["episode_number"] = flagged.groupby("sensor_index")["gap_hours"].transform(
        lambda s: (s.isna() | (s > episode_gap_hours)).cumsum()
    )

    event_rows: list[dict[str, object]] = []

    for (sensor_index, episode_number), group in flagged.groupby(["sensor_index", "episode_number"], sort=True):
        if len(group) < min_event_hours:
            continue

        group = group.sort_values("time_stamp")
        peak_row = group.loc[group["pm2.5_atm"].idxmax()]
        onset_row = group.iloc[0]
        end_row = group.iloc[-1]
        duration_hours = (end_row["time_stamp"] - onset_row["time_stamp"]).total_seconds() / 3600.0 + 1.0
        excess = (group["pm2.5_atm"] - group["baseline_median"]).clip(lower=0)

        event_rows.append(
            {
                "sensor_index": int(sensor_index),
                "name": peak_row["name"],
                "latitude": float(peak_row["latitude"]),
                "longitude": float(peak_row["longitude"]),
                "episode_number": int(episode_number),
                "onset_time_utc": onset_row["time_stamp"],
                "peak_time_utc": peak_row["time_stamp"],
                "end_time_utc": end_row["time_stamp"],
                "duration_hours": duration_hours,
                "hours_flagged": int(len(group)),
                "peak_pm25_atm": float(peak_row["pm2.5_atm"]),
                "mean_pm25_atm": float(group["pm2.5_atm"].mean()),
                "event_integrated_excess": float(excess.sum()),
                "baseline_median": float(peak_row["baseline_median"]),
                "robust_mad": float(peak_row["robust_mad"]),
                "event_threshold": float(peak_row["event_threshold"]),
                "baseline_source": peak_row["baseline_source"],
            }
        )

    events = pd.DataFrame(event_rows)
    if events.empty:
        return events

    events = events.sort_values(["sensor_index", "onset_time_utc", "peak_pm25_atm"], ascending=[True, True, False])
    events["event_rank"] = events.groupby("sensor_index").cumcount() + 1

    # Use the earliest post-fire event as the default HYSPLIT receptor target.
    events["is_primary_event"] = events["event_rank"] == 1
    events["hours_after_fire_start"] = (
        events["peak_time_utc"] - fire_start
    ).dt.total_seconds().div(3600)
    return events.reset_index(drop=True)


def main() -> None:
    args = parse_args()

    fire_start = parse_timestamp(args.fire_start_utc)
    baseline_end = parse_timestamp(args.baseline_end_utc, fallback=fire_start)
    baseline_start = parse_timestamp(args.baseline_start_utc) if args.baseline_start_utc else None

    df = load_inputs(args.pm25_csv, args.sensors_csv)
    baseline_stats = compute_baseline_stats(
        df=df,
        baseline_start=baseline_start,
        baseline_end=baseline_end,
        mad_multiplier=args.mad_multiplier,
        absolute_threshold=args.absolute_threshold,
        mad_floor=args.mad_floor,
    )
    events = extract_events(
        df=df,
        baseline_stats=baseline_stats,
        fire_start=fire_start,
        episode_gap_hours=args.episode_gap_hours,
        min_event_hours=args.min_event_hours,
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(args.output_csv, index=False)

    primary_count = int(events["is_primary_event"].sum()) if not events.empty else 0
    print(f"Loaded {len(df):,} PurpleAir rows across {df['sensor_index'].nunique()} sensors")
    print(f"Baseline stats computed for {len(baseline_stats):,} sensors")
    print(f"Saved {len(events):,} receptor events to {args.output_csv}")
    print(f"Primary events available for HYSPLIT: {primary_count:,}")


if __name__ == "__main__":
    main()
