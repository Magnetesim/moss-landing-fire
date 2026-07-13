#!/usr/bin/env python3

import numpy as np
import pandas as pd

from moss_landing.constants import MOSS_LANDING_LAT, MOSS_LANDING_LON
from moss_landing.paths import DATA_DIR


def main() -> None:
    df = pd.read_csv(DATA_DIR / "sensors.csv")

    df["dist"] = np.sqrt((df["latitude"] - MOSS_LANDING_LAT) ** 2 + (df["longitude"] - MOSS_LANDING_LON) ** 2)
    df_nearby = df[df["dist"] < 0.5].copy()

    print(f"{len(df_nearby)} sensors within ~35 miles of Moss Landing")
    df_nearby.to_csv(DATA_DIR / "sensors_nearby.csv", index=False)


if __name__ == "__main__":
    main()
