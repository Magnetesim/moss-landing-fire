import time
import datetime
import argparse
from pathlib import Path

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
API_KEY = (PROJECT_ROOT / "purple_air_api.txt").read_text(encoding="utf-8").strip()

def get_sensor_history(sensor_index, start_ts, end_ts, average=60):
    """
    average: 60 = hourly averages (recommended for plume work)
    """
    r = requests.get(
        f"https://api.purpleair.com/v1/sensors/{sensor_index}/history",
        headers={"X-API-Key": API_KEY},
        params={
            "start_timestamp": start_ts,
            "end_timestamp": end_ts,
            "average": average,
            "fields": "pm2.5_atm,pm2.5_cf_1,humidity"
        }
    )
    data = r.json()
    df = pd.DataFrame(data["data"], columns=data["fields"])
    df["sensor_index"] = sensor_index
    df["time_stamp"] = pd.to_datetime(df["time_stamp"], unit="s", utc=True)
    return df



def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pull PurpleAir historical hourly data for a filtered sensor list."
    )
    parser.add_argument("--input-sensors", type=Path, default=DATA_DIR / "sensors_active.csv")
    parser.add_argument("--output-csv", type=Path, default=DATA_DIR / "moss_landing_pm25.csv")
    parser.add_argument("--start-utc", default="2025-01-14T00:00:00Z")
    parser.add_argument("--end-utc", default="2025-01-25T00:00:00Z")
    parser.add_argument("--sleep-seconds", type=float, default=0.4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    df = pd.read_csv(args.input_sensors)
    print(f"Loaded {len(df)} active sensors from {args.input_sensors}")

    start = int(pd.Timestamp(args.start_utc).timestamp())
    end = int(pd.Timestamp(args.end_utc).timestamp())

    all_dfs = []
    failed = []

    sensor_indices = df["sensor_index"].tolist()
    print(f"Pulling history for {len(sensor_indices)} sensors...")
    print(f"Expected time: ~{len(sensor_indices) * 0.8 / 60:.1f} minutes\n")

    for i, idx in enumerate(sensor_indices):
        try:
            hist = get_sensor_history(idx, start, end)
            all_dfs.append(hist)
            if (i + 1) % 20 == 0:
                print(f"  Progress: {i+1}/{len(sensor_indices)}")
        except Exception as e:
            print(f"  Failed sensor {idx}: {e}")
            failed.append(idx)
        time.sleep(args.sleep_seconds)

    print(f"\nDone. {len(all_dfs)} succeeded, {len(failed)} failed.")
    if failed:
        print("Failed sensor indices:", failed)

    full_df = pd.concat(all_dfs).reset_index(drop=True)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    full_df.to_csv(args.output_csv, index=False)
    print(f"Saved {len(full_df)} rows to {args.output_csv}")


if __name__ == "__main__":
    main()
