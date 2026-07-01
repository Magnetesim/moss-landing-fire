#!/usr/bin/env python3
"""
Pre-screen all 168 sensors: which ones have historical data for Jan 14–25, 2025?
Does a lightweight query (just one field) on each sensor, keeps only active ones.
Run this before the full data pull to avoid wasting API calls on dead sensors.
"""

import requests
import pandas as pd
import datetime
import time
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
API_KEY = (PROJECT_ROOT / "purple_air_api.txt").read_text(encoding="utf-8").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter discovered PurpleAir sensors to only those with historical data in the event window."
    )
    parser.add_argument("--input-sensors", type=Path, default=DATA_DIR / "sensors.csv")
    parser.add_argument("--output-sensors", type=Path, default=DATA_DIR / "sensors_active.csv")
    parser.add_argument("--start-utc", default="2025-01-14T00:00:00Z")
    parser.add_argument("--end-utc", default="2025-01-25T00:00:00Z")
    parser.add_argument("--sleep-seconds", type=float, default=0.3)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start = int(pd.Timestamp(args.start_utc).timestamp())
    end = int(pd.Timestamp(args.end_utc).timestamp())

    df = pd.read_csv(args.input_sensors)
    print(f"Loaded {len(df)} sensors from {args.input_sensors}")
    print(f"Checking which have historical data for {args.start_utc} to {args.end_utc}...\n")

    active = []
    dead = []

    for i, row in df.iterrows():
        sidx = int(row["sensor_index"])
        try:
            r = requests.get(
                f"https://api.purpleair.com/v1/sensors/{sidx}/history",
                headers={"X-API-Key": API_KEY},
                params={
                    "start_timestamp": start,
                    "end_timestamp": end,
                    "average": 60,
                    "fields": "pm2.5_atm"
                },
                timeout=15
            )
            data = r.json()
            n = len(data.get("data", []))

            if n > 0:
                active.append(row)
            else:
                dead.append(row)
        except Exception:
            dead.append(row)

        if (i + 1) % 20 == 0:
            print(f"  Progress: {i+1}/{len(df)}  |  {len(active)} active, {len(dead)} dead")
        time.sleep(args.sleep_seconds)

    print(f"\nDone. {len(active)} sensors have data, {len(dead)} have no data.")

    df_active = pd.DataFrame(active).reset_index(drop=True)
    args.output_sensors.parent.mkdir(parents=True, exist_ok=True)
    df_active.to_csv(args.output_sensors, index=False)
    print(f"Saved {len(df_active)} active sensors to {args.output_sensors}")

    if dead:
        print("\nDead sensors (no data for this time window):")
        for row in dead:
            print(f"  #{int(row['sensor_index']):6d}  {row['name']}")


if __name__ == "__main__":
    main()
