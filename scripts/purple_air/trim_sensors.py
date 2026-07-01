#!/usr/bin/env python3

import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"

df = pd.read_csv(DATA_DIR / "sensors.csv")

ml_lat, ml_lon = 36.8044, -121.7883

df["dist"] = np.sqrt((df["latitude"] - ml_lat)**2 + (df["longitude"] - ml_lon)**2)
df_nearby = df[df["dist"] < 0.5].copy()

print(f"{len(df_nearby)} sensors within ~35 miles of Moss Landing")
df_nearby.to_csv(DATA_DIR / "sensors_nearby.csv", index=False)
