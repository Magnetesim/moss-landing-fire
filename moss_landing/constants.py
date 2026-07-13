"""Event constants shared across PurpleAir and HYSPLIT workflows."""

from __future__ import annotations

import pandas as pd

# Map/source origin used for both visualization and HYSPLIT source terms.
MOSS_LANDING_LAT = 36.8044
MOSS_LANDING_LON = -121.7883

# Project/narrative fire-start assumption (needs an authoritative citation
# before formal use; see docs/project_status.md "PurpleAir Notes").
FIRE_START_LOCAL = pd.Timestamp("2025-01-16 17:35", tz="US/Pacific")
FIRE_START_UTC = FIRE_START_LOCAL.tz_convert("UTC")
FIRE_START_UTC_ISO = "2025-01-17T01:35:00Z"

# Ignition/origin used by the phase-1 sweeps and 4-hour window alignment.
# NOTE: this is 2 h 35 min earlier than FIRE_START_UTC. The 23:00 Z value is
# the historical sweep origin; whether it should equal the fire-start
# assumption is an open question tracked in docs/project_status.md.
DEFAULT_IGNITION_UTC = "2025-01-16T23:00:00Z"

# Enhancement class scheme shared by kriging panels and HYSPLIT scoring.
ENHANCEMENT_BOUNDS = [0, 1, 5, 12, 35, 80]
ENHANCEMENT_LABELS = [
    "Background (0-1)",
    "Low (1-5)",
    "Moderate (5-12)",
    "Elevated (12-35)",
    "High (35+)",
]
ENHANCEMENT_COLORS = ["#2c7bb6", "#00a6ca", "#00cc66", "#f9d057", "#d7191c"]
