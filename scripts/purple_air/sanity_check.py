#!/usr/bin/env python3
"""
Sanity check before the full 168-sensor historical pull.
Picks the sensor closest to Moss Landing, pulls its PM2.5 history
for Jan 14–25 2025, and plots it to confirm the Jan 16 spike is visible.
"""

import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
FIGURES_DIR = PROJECT_ROOT / "figures" / "visualization"
API_KEY = (PROJECT_ROOT / "purple_air_api.txt").read_text(encoding="utf-8").strip()

# --- 1. Load sensors and sort by distance to Moss Landing ---
df = pd.read_csv(DATA_DIR / "sensors.csv")

ml_lat, ml_lon = 36.8044, -121.7883
df["dist"] = np.sqrt((df["latitude"] - ml_lat)**2 + (df["longitude"] - ml_lon)**2)
df = df.sort_values("dist")

# --- 2. Find the closest sensor that actually has historical data ---
start = int(datetime.datetime(2025, 1, 14, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
end   = int(datetime.datetime(2025, 1, 25, 0, 0, tzinfo=datetime.timezone.utc).timestamp())

print(f"Searching for a sensor with historical data (Jan 14–25, 2025)...")
print(f"(Local Pacific: Jan 13 4pm to Jan 24 4pm)\n")

found_idx = None
found_name = None
found_dist = None
max_try = 20  # check up to the 20 closest sensors

for i, (_, row) in enumerate(df.head(max_try).iterrows()):
    sidx = int(row["sensor_index"])
    sname = row["name"]
    sdist = row["dist"]
    
    r = requests.get(
        f"https://api.purpleair.com/v1/sensors/{sidx}/history",
        headers={"X-API-Key": API_KEY},
        params={
            "start_timestamp": start,
            "end_timestamp": end,
            "average": 60,
            "fields": "pm2.5_atm"  # light query, just checking for data
        }
    )
    data = r.json()
    n_records = len(data.get("data", []))
    print(f"  #{i+1:2d}  Sensor {sidx:6d}  dist={sdist*111:5.1f} km  — {n_records} records  ({sname})")
    
    if n_records > 0:
        found_idx = sidx
        found_name = sname
        found_dist = sdist
        print(f"\n  ✓ Using sensor #{found_idx} — {found_name}")
        break

if found_idx is None:
    print(f"\nERROR: None of the {max_try} closest sensors have data for this time window.")
    exit(1)

# --- 3. Full pull with all fields ---
r = requests.get(
    f"https://api.purpleair.com/v1/sensors/{found_idx}/history",
    headers={"X-API-Key": API_KEY},
    params={
        "start_timestamp": start,
        "end_timestamp": end,
        "average": 60,
        "fields": "pm2.5_atm,pm2.5_cf_1,humidity"
    }
)

data = r.json()

test_df = pd.DataFrame(data["data"], columns=data["fields"])
test_df["time_stamp"] = pd.to_datetime(test_df["time_stamp"], unit="s", utc=True)

print(f"  Distance: {found_dist:.4f} degrees (~{found_dist*111:.1f} km)")
print(f"Got {len(test_df)} hourly records")
print(f"PM2.5 ATM:  min={test_df['pm2.5_atm'].min():.1f}, "
      f"max={test_df['pm2.5_atm'].max():.1f}, "
      f"median={test_df['pm2.5_atm'].median():.1f} µg/m³")

# --- 4. Identify the peak ---
peak_row = test_df.loc[test_df["pm2.5_atm"].idxmax()]
print(f"\nPeak PM2.5: {peak_row['pm2.5_atm']:.1f} µg/m³ at {peak_row['time_stamp']} UTC")
print(f"  ({peak_row['time_stamp'].tz_convert('US/Pacific')} Pacific)")

# Check if peak is during the fire window
fire_start_utc = pd.Timestamp("2025-01-17 02:00", tz="UTC")
fire_end_utc   = pd.Timestamp("2025-01-18 00:00", tz="UTC")
if fire_start_utc <= peak_row["time_stamp"] <= fire_end_utc:
    print("  ✓ Peak falls within the fire window — spike confirmed!")
else:
    print(f"  ⚠ Peak is outside the expected fire window ({fire_start_utc}–{fire_end_utc} UTC)")
    print(f"  The fire started ~7pm Pacific Jan 16 = ~03:00 UTC Jan 17.")

# --- 5. Plot ---
fig, ax1 = plt.subplots(figsize=(14, 6))

ax1.plot(test_df["time_stamp"], test_df["pm2.5_atm"],
         color="black", linewidth=0.8, label="PM2.5 ATM")
ax1.axvline(pd.Timestamp("2025-01-17 00:00", tz="UTC"), color="red",
            linestyle="--", linewidth=1.5, label="Fire start (~Jan 16 evening)")
ax1.set_ylabel("PM2.5 ATM (µg/m³)", color="black")
ax1.set_xlabel("Time (UTC)")
ax1.set_title(f"PurpleAir Sensor #{found_idx} — {found_name}\n"
              f"Distance: {found_dist*111:.0f} km from Moss Landing")
ax1.legend(loc="upper left")
ax1.grid(alpha=0.3)

# Optional: humidity on secondary axis
if "humidity" in test_df.columns:
    ax2 = ax1.twinx()
    ax2.plot(test_df["time_stamp"], test_df["humidity"],
             color="blue", linewidth=0.5, alpha=0.5, label="Humidity")
    ax2.set_ylabel("Humidity (%)", color="blue")
    ax2.legend(loc="upper right")

plt.tight_layout()
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
plt.savefig(FIGURES_DIR / "sanity_check.png", dpi=150)
plt.show()

print(f"\nPlot saved to {FIGURES_DIR / 'sanity_check.png'}")
print("If the spike is clear, you're good to run the full pull (pull_data.py).")
