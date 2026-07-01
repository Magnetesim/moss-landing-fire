# Moss Landing Plume Visualization - Project Handoff

**Date:** May 29, 2026
**Project:** PM2.5 plume visualization from the Moss Landing Vistra Energy lithium battery fire
**Researcher:** Myles (UCSC Baskin Engineering, Prof. Gonzalez Rocha's group)
**Status:** Data acquisition complete ✅ — Tier 1 animated bubble map built ✅ — Tier 2 & 3 next

---

## Project Goal

Visualize how smoke/PM2.5 plumes from the Moss Landing lithium battery fire moved through the Santa Cruz/Monterey area using a network of air quality sensors. The end goal is an animated, multi-sensor visualization showing plume transport over time - ideally paired with HYSPLIT backward trajectories for attribution.

---

## The Fire Event

- **Location:** Moss Landing, CA - Vistra Energy battery storage facility
- **Coordinates:** 36.8044°N, 121.7883°W
- **Date:** January 16-17, 2025 (fire ignited evening of Jan 16)
- **Data window to pull:** January 14 - January 25, 2025
  - Jan 14-15: baseline (clean air before the fire)
  - Jan 16-17: fire ignition and peak smoke
  - Jan 18-25: plume dissipation and transport

---

## Data Sources

### Primary: PurpleAir (current focus)
- Consumer-grade sensor network with very high spatial density in the Santa Cruz/Monterey area
- API access at `https://api.purpleair.com/v1/`
- API key already obtained (1 million free points available)
- **Point cost is not a concern** - pulling all 168 sensors costs estimated 50k-100k points total
- Key field: `pm2.5_atm` (ATM correction, best for ambient/smoke conditions)
- Also pull `pm2.5_cf_1` and `humidity` for correction reference
- Data is returned in UTC unix timestamps - convert carefully (local time is Pacific)

### Secondary: CARB AQMIS2 (future work)
- Official regulatory monitors, fewer but higher-quality/calibrated
- Santa Cruz AMS sensor already identified (screenshot in project notes)
- No clean public API - requires scraping with requests + BeautifulSoup
- URL structure is predictable by station ID and date
- Good for cross-validation against PurpleAir consumer sensors

---

## What's Been Done

### Step 1: Sensor Discovery ✅
Called the PurpleAir `/v1/sensors` endpoint with a bounding box covering Santa Cruz, Aptos, Capitola, Watsonville, Moss Landing, Castroville, Prunedale, and inland toward Gilroy/Aromas.

**Bounding box used:**
```
nwlng: -122.10, nwlat: 37.05
selng: -121.50, selat: 36.55
```

**Result:** 168 sensors discovered. Saved to `sensors.csv`.

**Sensor distribution (from PurpleAir map screenshot):**
- Dense cluster in Santa Cruz / Capitola / Seacliff (upwind baseline sensors)
- Good mid-corridor coverage through Aptos / La Selva Beach / Seascape
- Sensors near Moss Landing / Castroville (ground zero - will show strongest spike)
- Inland sensors toward Prunedale / Aromas / Gilroy (cross-wind transport)

**Decision: Keep all 168 sensors.** Distance filtering to 55 sensors (0.2 degree threshold) was considered but rejected because:
1. Points cost is negligible
2. Farther sensors show plume dissipation, making the visualization much richer
3. The Santa Cruz cluster provides clean upwind baseline readings

**Discovery script (for reference/reuse):**
```python
import requests
import pandas as pd

API_KEY = "your_key_here"

params = {
    "fields": "sensor_index,name,latitude,longitude,pm2.5_atm",
    "location_type": "0",  # outdoor sensors only
    "nwlng": -122.10,
    "nwlat": 37.05,
    "selng": -121.50,
    "selat": 36.55,
}

r = requests.get(
    "https://api.purpleair.com/v1/sensors",
    headers={"X-API-Key": API_KEY},
    params=params
)

data = r.json()
fields = data["fields"]
rows = data["data"]
df = pd.DataFrame(rows, columns=fields)
df.to_csv("sensors.csv", index=False)
print(f"Saved {len(df)} sensors")
```

---

## Next Steps

### Step 2: Sanity Check One Sensor First (do this before the full loop)

Pick the sensor closest to Moss Landing and pull its history to confirm the Jan 16 spike is visible. This validates that the API call structure is correct and timestamps are handled right before committing to 168 API calls.

```python
import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import datetime

API_KEY = "your_key_here"

df = pd.read_csv("sensors.csv")

# Add distance column if not already there
ml_lat, ml_lon = 36.8044, -121.7883
df["dist"] = np.sqrt((df["latitude"] - ml_lat)**2 + (df["longitude"] - ml_lon)**2)

# Find closest sensor to Moss Landing
closest_idx = df.loc[df["dist"].idxmin(), "sensor_index"]
print(f"Testing sensor {closest_idx}: {df.loc[df['dist'].idxmin(), 'name']}")

# Time window - UTC unix timestamps
start = int(datetime.datetime(2025, 1, 14, 0, 0, tzinfo=datetime.timezone.utc).timestamp())
end   = int(datetime.datetime(2025, 1, 25, 0, 0, tzinfo=datetime.timezone.utc).timestamp())

def get_sensor_history(sensor_index, start_ts, end_ts, average=60):
    """
    average=60 means hourly averages.
    Hourly is the right resolution for plume work - fine enough to see
    transport timing, coarse enough to reduce noise.
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
    df_out = pd.DataFrame(data["data"], columns=data["fields"])
    df_out["sensor_index"] = sensor_index
    df_out["time_stamp"] = pd.to_datetime(df_out["time_stamp"], unit="s", utc=True)
    return df_out

# Test single sensor
test_df = get_sensor_history(closest_idx, start, end)
print(test_df.head())
print(f"Max PM2.5: {test_df['pm2.5_atm'].max():.1f} at {test_df.loc[test_df['pm2.5_atm'].idxmax(), 'time_stamp']}")

# Quick plot - should show obvious spike around Jan 16 evening UTC
test_df.plot(x="time_stamp", y="pm2.5_atm", title=f"Sensor {closest_idx} - PM2.5")
plt.axvline(pd.Timestamp("2025-01-16", tz="UTC"), color="red", linestyle="--", label="Fire start")
plt.ylabel("PM2.5 (μg/m3)")
plt.legend()
plt.tight_layout()
plt.show()
```

**What to look for:** A sharp spike on Jan 16 evening (UTC) reaching well above baseline. The Moss Landing-area sensor should be dramatic - the fire was severe. If you don't see a spike, check timezone handling first (the fire started ~evening Pacific = early morning Jan 17 UTC).

---

### Step 3: Full Historical Pull (all 168 sensors)

Once the sanity check passes, run this. Expect ~2-3 minutes for the full loop.

```python
import time

all_dfs = []
failed = []

sensor_indices = df["sensor_index"].tolist()

for i, idx in enumerate(sensor_indices):
    try:
        hist = get_sensor_history(idx, start, end)
        all_dfs.append(hist)
        if i % 10 == 0:
            print(f"Progress: {i}/{len(sensor_indices)}")
    except Exception as e:
        print(f"Failed sensor {idx}: {e}")
        failed.append(idx)
    time.sleep(0.5)  # rate limit politeness

print(f"\nDone. {len(all_dfs)} succeeded, {len(failed)} failed.")
if failed:
    print("Failed sensor indices:", failed)

full_df = pd.concat(all_dfs).reset_index(drop=True)
full_df.to_csv("moss_landing_pm25.csv", index=False)
print(f"Saved {len(full_df)} rows to moss_landing_pm25.csv")
```

**Output:** `moss_landing_pm25.csv` - the main data file for all visualization work going forward.

---

## Planned Visualization Pipeline (after data is collected)

### Tier 1 - Animated bubble map (primary deliverable)
- One frame per hour
- Each sensor rendered as a circle at its lat/lon, sized/colored by PM2.5
- Color scale: green → yellow → orange → red → purple (AQI standard)
- Tools: `plotly` (easiest interactive animation) or `matplotlib.animation`
- Overlay on a basemap: `folium` or `cartopy` with OpenStreetMap tiles
- Should clearly show the plume originating at Moss Landing and spreading

### Tier 2 - Spatial interpolation (smoother plume shape)
- Interpolate PM2.5 values across a lat/lon grid between sensor points
- Options: IDW (inverse distance weighting) via `scipy.interpolate`, or kriging via `pykrige`
- Kriging is more physically appropriate for atmospheric dispersion but more complex
- Render as a heatmap overlay on the basemap

### Tier 3 - HYSPLIT integration (most rigorous, publication-quality)
- Run backward trajectories from each sensor location at the time of their PM2.5 peak
- Trajectories that converge on Moss Landing = strong causal attribution
- Directly relevant to existing research with Prof. Gonzalez Rocha
- Wind data source: NOAA HRRR (3km resolution, archived for Jan 2025)

### Wind data (needed for context regardless of tier)
- **NOAA HRRR archives** - best spatial resolution for this area and time
- **Mesonet API** - surface wind obs from nearby ASOS stations (Monterey and Watsonville airports are closest)
- Wind vectors overlaid on the animation explain *why* the plume moves the direction it does

---

## Key Technical Notes

- **Timezone:** PurpleAir returns UTC unix timestamps. Always convert with `utc=True` in `pd.to_datetime()`. The fire started Jan 16 evening Pacific = Jan 17 ~02:00-04:00 UTC.
- **PM2.5 field choice:** Use `pm2.5_atm` for ambient/smoke conditions. `pm2.5_cf_1` is the raw CF=1 correction, useful as a secondary check but `_atm` is better for outdoor smoke.
- **Sensor reliability:** PurpleAir sensors have two channels (A and B). If the API returns both, flagged/divergent readings can be filtered. For this project `pm2.5_atm` is the averaged/corrected value, so it's fine to use directly.
- **Distance column:** The `dist` column in `sensors.csv` was added locally - it won't be in the raw API response. It's in Euclidean degrees, not km. At this latitude, 0.1 degrees ≈ ~9km.

---

## File Map

| File | Contents |
|------|----------|
| `sensors.csv` | 168 PurpleAir sensors in the bounding box - sensor_index, name, lat, lon, current pm2.5, dist from Moss Landing |
| `moss_landing_pm25.csv` | (to be created) Full hourly PM2.5 history for all sensors, Jan 14-25 2025 |

---

## Future: CARB AQMIS2 Integration

The CARB data (from the AQMIS2 screenshot showing the Santa Cruz AMS sensor) is useful for cross-validation because it's regulatory-grade and calibrated, unlike consumer PurpleAir sensors. The AQMIS2 chart showed January data with the x-axis labeled 01/01-01/29, consistent with the fire timeframe.

To scrape AQMIS2 programmatically:
- Inspect the URL structure when navigating to a specific station/parameter/date range
- The station ID and date range parameters are typically URL query params
- Use `requests` + `BeautifulSoup` to parse the returned HTML table or chart data
- This is lower priority - PurpleAir gives better spatial density for visualization

---

## Recommended Python Environment

```
pandas
numpy
requests
matplotlib
scipy
plotly          # for interactive animated maps
folium          # for basemap rendering
pykrige         # optional, for kriging interpolation
```

---

# APPENDIX: May 29, 2026 Work Session

*Appended after completing Steps 2–3 and Tier 1 visualization. Documents decisions, results, and updates to the file map.*

---

## Step 1.5: Pre-Screening Active Sensors (Unexpected)

### Problem

The discovery endpoint (`/v1/sensors`) only returns metadata about sensors that exist **right now**. It has no mechanism to indicate whether a sensor was active or had data 1.5 years ago. When we began the sanity check, the absolute closest sensor to Moss Landing (#294423, 3.7 km) returned empty historical data — it was installed after January 2025.

This meant blindly pulling all 168 sensors would waste ~22% of API calls on sensors with no data, and worse, the `pull_data.py` loop would hit empty-data errors.

### Solution: `filter_active_sensors.py`

A lightweight pre-screening script that queries the history endpoint for each sensor using just one field (`pm2.5_atm`) to check for data availability. It iterates through all 168 sensors in `sensors.csv` and splits them into active and dead.

**Results:**
- **132 sensors** have historical data (79%)
- **36 sensors** have no data for Jan 14–25, 2025
- Saved to `sensors_active.csv`

Dead sensors (installed after Jan 2025 or offline during the fire window):
```
#265737 CC5, #265781 CCA3, #265801 Javiland, #4797 Glengarry,
#268632 López Family, #271856 Cerezes, #271858 AllisonSt, #271866 Corralitos1,
#271908 Pajaro 4, #272771 Pajaro2, #273795 1425 Hidden Valley Road,
#283492 Calabas1, #283535 E Fifth, #283540 Javier Gonzalez-Rocha,
#284682 Beverly Drive, #294423 1900 highway 1 space8, #294439 Airpace Integrated,
#298499 Monterey Bees, #301473 1244 Laurent St, #302722 El Capitan,
#304094 Vierra Meadows PL, #308800 Brook Knoll, #50745 Meder St,
#60191 Woodcrest Outdoor, #65947 Sunny Cove, #70011 Teahouse,
#70323 West Cliff, #77359 So Salinas 776, #99657 Oxford Way,
#204729 Ruthies, #238567 CCA1, #238577 ACC2B, #238583 Holand,
#238585 CCA10, #238609 CCA8, #258525 Banana belt
```

**Design note:** Each check takes ~0.7s (API round-trip). With a 0.2s sleep between calls, the full 168-sensor pre-screen takes about 2.5 minutes. The request uses `timeout=5` to prevent hanging.

### Updated Pipeline
```
sensors.csv (168)
    → filter_active_sensors.py  →  sensors_active.csv (132)
    → sanity_check.py
    → pull_data.py              →  moss_landing_pm25.csv
```

---

## Step 2: Sanity Check (Completed)

### What We Actually Did

The naive approach in the original plan — "pick the closest sensor" — failed because 7 of the 10 closest sensors to Moss Landing had no January 2025 data. They were all installed later.

**Adapted approach:** `sanity_check.py` iterates through the closest 20 sensors (by Euclidean distance) and takes the first one that returns historical records. It prints a table of each sensor's distance and record count so the user sees which sensors are active/inactive.

### Sensor Selected

**#75019 — "The Cosmic Center"** at 6.6 km from Moss Landing (36.8166°N, 121.7300°W).

This was the first sensor in the sorted-by-distance list with data (position #7). It returned 264 hourly records.

### Spike Analysis

| Time (Pacific) | PM2.5 (µg/m³) | Notes |
|---|---|---|
| Jan 14–16 daytime | 0.5–12.8 | Clean baseline |
| Jan 17 early AM | 20.4 → 26.8 → 27.5 | First plume arrival |
| Jan 17 evening | 24.1 → 31.3 → 33.1 | Second pulse |
| Jan 18 evening | **37.6 → 43.2** | **PEAK** at 8pm Pacific |
| Jan 19 | 36.2 → 32.8 → 40.4 | Third pulse, recirculation |
| Jan 20 | 37.7 → tapering | Dissipation |

**Key finding:** The spike is undeniable. The peak comes ~48 hours after fire ignition, which is consistent with a multi-day industrial fire — the plume pulses as different battery racks burn, and smoke transport/recirculation extends the elevated period well beyond the initial ignition window.

**Important:** There are also modest elevated values on Jan 14–15 (up to 29.7 µg/m³) before the fire. These are likely winter inversion/wood-burning baseline and should not be confused with the fire signal.

### Output
- `sanity_check.png` — time series plot with PM2.5 (black), fire-start line (red), and humidity overlay (blue)

---

## Step 3: Full Historical Pull (Completed)

### What Changed from Original Plan

1. **Source file:** Reads `sensors_active.csv` (132) instead of `sensors.csv` (168) — avoids 36 guaranteed-empty API calls
2. **Timezone fix:** Added `utc=True` to `pd.to_datetime()` — the original `pull_data.py` was missing this, which would offset all timestamps by local time
3. **Progress reporting:** Every 20 sensors instead of every 10 (cleaner output for 132 sensors)
4. **Sleep reduced:** 0.4s instead of 0.5s (132 sensors × 0.8s avg = ~105 seconds)

### Results

```
Loaded 132 active sensors from sensors_active.csv
Pulling history for 132 sensors...

Progress: 20/132
Progress: 40/132
...
Progress: 120/132

Done. 132 succeeded, 0 failed.
Saved 33935 rows to moss_landing_pm25.csv
```

### Output: `moss_landing_pm25.csv`

| Property | Value |
|---|---|
| Rows | 33,935 |
| Columns | `time_stamp`, `humidity`, `pm2.5_atm`, `pm2.5_cf_1`, `sensor_index` |
| Sensors | 132 |
| Date range | 2025-01-14 00:00 to 2025-01-24 23:00 UTC |
| Records/sensor | 257 avg (most: 264 = 11 days × 24 hours) |
| Median PM2.5 | 7.7 µg/m³ (clean baseline) |
| Max PM2.5 | **2,183.3 µg/m³** at sensor #84331 (Light Springs Road, 23.1 km from Moss Landing) |
| Top peak sensors | #84331: 2183, #134408: 1679, #118477: 1678, #120355: 1678, #116111: 1677 |

**Note on the 2,183 µg/m³ peak:** This is at the upper limit of PurpleAir sensor saturation for PM2.5. Multiple sensors within ~20 km hit ~1,678 µg/m³, suggesting that's a hardware saturation ceiling. The true concentration may have been even higher. For visualization purposes, values above ~250 µg/m³ are all "Hazardous" AQI — the exact number beyond that is academic.

---

## Tier 1: Animated Bubble Map (Completed)

### Script: `tier1_bubble_map.py`

Output: `tier1_bubble_map.html` (9.7 MB, self-contained interactive HTML)

### Design Decisions

#### Library: Plotly `scatter_map` (not `scatter_mapbox`)

As of Plotly v5.24, `scatter_mapbox` is deprecated in favor of `scatter_map`, which uses MapLibre instead of Mapbox as the rendering engine. Benefits:
- No API key required for built-in styles
- Improved WebGL2 rendering performance
- Same API surface — just drop the "box" suffix

We use `map_style="open-street-map"` (free OpenStreetMap tiles via Carto).

#### Color Encoding: EPA AQI Categories

Rather than a continuous color scale, we bucket PM2.5 into the standard EPA AQI categories. This makes the visualization immediately interpretable — viewers familiar with AirNow will recognize the colors:

| PM2.5 (µg/m³) | Color | AQI Category |
|---|---|---|
| 0–12 | 🟢 `#00e400` | Good |
| 12–35 | 🟡 `#ffff00` | Moderate |
| 35–55 | 🟠 `#ff7e00` | Unhealthy for Sensitive Groups |
| 55–150 | 🔴 `#ff0000` | Unhealthy |
| 150–250 | 🟣 `#8f3f97` | Very Unhealthy |
| 250+ | 🟤 `#7e0023` | Hazardous |

**Why categories over continuous:** With a 300× range (7 to 2,183 µg/m³), a continuous linear or log scale would be dominated by the extreme values. The categorical approach makes every threshold crossing visually meaningful.

#### Size Encoding: Power-Law Scaling

```python
bubble_size = pm2.5 ** 0.4 * 3
```

**Why exponent 0.4:** 
- `sqrt` (0.5): Too aggressive — squashes the spike too much, the fire zone doesn't visually pop
- `cube root` (0.33): Too aggressive in the other direction — makes low values too similar in size
- **0.4**: Sweet spot — baseline values (~7 µg/m³) map to a ~6px radius, the peak (~2,183 µg/m³) maps to ~65px. The spike is visually dominant but doesn't obliterate surrounding sensors.

The `* 3` multiplier scales the raw power values to sit in the 2–65 range, which is then capped by `size_max=20` in plotly for reasonable map rendering.

#### Animation

- **264 frames**, one per hour from Jan 14 00:00 to Jan 24 23:00 UTC
- Frame labels shown in **Pacific time** (`tz_convert("US/Pacific")`) for readability
- Plotly's built-in animation player with play/pause and a timeline slider
- Each frame shows all 132 sensors at their PM2.5 value for that hour

#### Map Features

- Centered on Moss Landing at zoom level 9 (covers Santa Cruz to Salinas)
- Black **X marker** at Moss Landing (36.8044°N, 121.7883°W) — the fire origin
- Hover tooltip per sensor: name, PM2.5 (1 decimal), humidity (integer)
- Legend at top-left with translucent white background

### How to View

Open `tier1_bubble_map.html` in any browser. Use the play button to animate, drag the slider to scrub through time. The file is fully self-contained (all data embedded inline).

### Known Limitations

- 264 frames at 132 sensors each = 9.7 MB HTML. Reasonable for local use, large for web hosting.
- No wind overlay yet — wind vectors would explain *why* the plume moves (see Tier 3 / wind data section above)
- Bubbles overlap in dense sensor clusters (especially Santa Cruz). The AQI color still shows the worst reading, but individual sensors can be hard to distinguish.

---

## Updated File Map

| File | Contents | Status |
|---|---|---|
| `sensors.csv` | 168 PurpleAir sensors in bounding box | ✅ discovery.py |
| `sensors_nearby.csv` | Same 168 sensors with distance column | ✅ trim_sensors.py |
| `sensors_active.csv` | 132 sensors with historical data for Jan 14–25 2025 | ✅ filter_active_sensors.py |
| `sanity_check.png` | PM2.5 time series for sensor #75019, confirming spike | ✅ sanity_check.py |
| `moss_landing_pm25.csv` | 33,935 rows — full hourly PM2.5 history for all active sensors | ✅ pull_data.py |
| `tier1_bubble_map.html` | Interactive animated bubble map, 264 frames, AQI colors | ✅ tier1_bubble_map.py |

### Python Scripts

| Script | Purpose |
|---|---|
| `discovery.py` | Query `/v1/sensors` for bounding box, save sensors.csv |
| `trim_sensors.py` | Add distance column, filter by distance (optional) |
| `filter_active_sensors.py` | Pre-screen all sensors for historical data availability |
| `sanity_check.py` | Find closest active sensor, pull history, plot/validate spike |
| `pull_data.py` | Full historical pull of all active sensors → moss_landing_pm25.csv |
| `tier1_bubble_map.py` | Build interactive animated bubble map → tier1_bubble_map.html |

### Python Environment

A virtual environment at `.venv/` was created to install plotly (not available system-wide on this Arch Linux setup). Activate with:
```bash
source .venv/bin/activate
```

Installed packages: `pandas`, `numpy`, `matplotlib`, `requests`, `plotly`

---

## Next Steps (Updated)

### Tier 1 Refinements (quick wins)
- [ ] Add wind vector overlay from Mesonet or HRRR data — explains plume direction
- [ ] Experiment with 3-hour or 6-hour frame intervals to reduce file size for web hosting
- [ ] Add a PM2.5 time-series inset for a selected "highlight" sensor
- [ ] Export as MP4/GIF for embedding in presentations (plotly can render frames via kaleido)

### Tier 2 — Spatial Interpolation
- [ ] Implement IDW (inverse distance weighting) via `scipy.interpolate.RBFInterpolator`
- [ ] Render as a smooth heatmap overlay instead of discrete bubbles
- [ ] Better represents continuous plume shape between sparse sensors
- [ ] Kriging (`pykrige`) is the physically-correct choice for atmospheric dispersion but requires semivariogram fitting

### Tier 3 — HYSPLIT Integration
- [ ] Run backward trajectories from each sensor at its peak PM2.5 time
- [ ] Trajectories converging on Moss Landing = causal attribution
- [ ] Requires NOAA HRRR wind data (3km, archived for Jan 2025)
- [ ] Directly relevant to Prof. Gonzalez Rocha's research

### CARB AQMIS2
- [ ] Scrape regulatory monitor data for cross-validation against PurpleAir
- [ ] Santa Cruz AMS sensor already identified
- [ ] Lower priority — PurpleAir spatial density is the strength of this project

---

# APPENDIX: June 5, 2026 Work Session

*Appended after a second round of Tier 1 refinement work. This section documents the visualization cleanup, the export path for presentation-friendly animations, and the reasoning behind the current design so the project can be resumed later without needing chat context.*

---

## Summary of What Changed

The original Tier 1 deliverable (`figures/tier1_bubble_map.html`) was useful as an exploratory interactive artifact, but it still had two practical gaps:

1. It was not ideal for embedding in slides, documents, or email because it required a browser and Plotly's player controls
2. The non-interactive export looked too bare when converted into a plain frame animation — especially without a basemap or an explicit indicator of when the fire actually began

This work session focused on improving those problems without changing the underlying data pipeline. No new data was pulled. The source dataset remains `data/moss_landing_pm25.csv` merged with sensor metadata from `data/sensors_active.csv` or `data/sensors.csv`.

The main code changes were made in:

- `scripts/tier1_bubble_map.py`

The main outputs are now:

- `figures/tier1_bubble_map.html` — improved interactive HTML animation
- `figures/tier1_bubble_map.gif` — animated GIF export for presentations/docs

---

## Why the Export Path Changed

### Initial Question

The project originally produced only a self-contained Plotly HTML. The immediate question was whether this could also produce a `.gif` or similar shareable animation.

### Practical Constraint

At the time of this work, Plotly was not installed system-wide, and the previous handoff notes referenced a `.venv/` that no longer exists in the current workspace layout. The user clarified that `uv` is the preferred environment/tooling path.

### Design Decision

Rather than reintroducing a hard-coded `.venv` workflow, the script was updated to work cleanly with `uv run --with ...` so dependencies can be resolved on demand.

This was the right choice because:

- it avoids baking environment assumptions into the repo state
- it makes the script runnable on a clean machine with one command
- it keeps the handoff honest: the current reproducible path is `uv`, not a local virtualenv sitting in the workspace

### Why Not Export the Plotly Map Directly?

In theory, Plotly frames can be rendered into static images and stitched into GIF/MP4. In practice, that path usually depends on extra rendering components such as `kaleido`, browser-backed rendering, or frame-by-frame screenshot logic. That adds fragility, especially when the goal is simply to produce a portable presentation asset.

Instead, the script now has two distinct rendering modes:

- Plotly for the interactive HTML map
- Matplotlib for the exported GIF

This split is intentional. Plotly is better for interactive exploration; Matplotlib is more predictable for deterministic frame export.

---

## Script Refactor: `scripts/tier1_bubble_map.py`

The visualization script was rewritten from a single-purpose HTML generator into a small command-line tool with explicit output modes.

### Current CLI

The script now accepts:

- `--html` to build the interactive map
- `--gif` to build the animated GIF
- `--gif-step-hours N` to subsample frames for export
- `--gif-fps N` to set playback speed

If no flags are passed, it defaults to HTML output only.

### Why Add CLI Flags?

The older script assumed one output and one fixed rendering style. That becomes awkward once export is added because HTML and GIF have different tradeoffs:

- HTML can comfortably carry all 264 hourly frames and map tiles interactively
- GIF should usually be downsampled to avoid huge files and sluggish playback

Putting both outputs behind flags keeps one codepath for data prep while allowing different renderers and output defaults.

---

## Data Handling Decisions Preserved in the Refactor

The refactor preserved several core Tier 1 design choices because they were still valid:

### 1. Sensor Metadata Merge

The script still reads `data/moss_landing_pm25.csv` and merges location/name data from sensor metadata.

It first looks for:

- `data/sensors_active.csv`

and falls back to:

- `data/sensors.csv`

This fallback exists because the active-sensor file is the most semantically correct metadata source for the final plume dataset, but the raw sensor file is still a safe backup if the active file is unavailable.

### 2. UTC In, Pacific Out

Timestamps are still parsed with `utc=True`, then converted to `US/Pacific` for labels.

This remains critical. The core data are UTC, but the event narrative is local. A visualization intended for human interpretation should speak local time, especially for a fire event where people reason about "evening of Jan 16" rather than UTC offsets.

### 3. EPA AQI Category Colors

The AQI bucketing was preserved instead of switching to a continuous colormap.

Reasoning:

- the PM2.5 range is extremely skewed because some near-source sensors saturated above 1,600-2,100 ug/m3
- a continuous scale would compress the low-to-moderate range and hide threshold crossings
- categorical AQI colors are immediately interpretable to non-technical audiences

This remains the best choice for communication, even if it is less numerically granular than a continuous color scale.

---

## Bubble Size Re-Tuning

### Problem

The original size encoding was acceptable in the browser, but once exported to a static-frame animation, the most extreme sensors could visually dominate too much. PurpleAir saturation-level values near the fire can make the map read as "one giant red dot plus noise," which weakens the transport story.

### Change

The rendered size now uses a clipped PM2.5 value before the power-law transform:

```python
clipped_pm = df["pm2.5_atm"].clip(lower=0.5, upper=400)
df["bubble_size"] = clipped_pm.pow(0.43) * 3.1
df["bubble_area"] = (df["bubble_size"] * 1.35).clip(lower=18, upper=220)
```

### Why This Is Better

This is a visual encoding decision, not a scientific data edit. The raw PM2.5 values are untouched in the dataset and still shown in labels/stats. Only marker size is clipped.

The rationale is:

- marker area is a visual device, not the measurement itself
- above ~250 ug/m3, the AQI category is already "Hazardous," so exact size differences become less meaningful visually
- clipping the top end prevents one or two saturated sensors from swallowing the map and makes regional structure easier to see

If publication-quality quantitative interpretation becomes the priority later, the team may want to separate "communication styling" and "analysis styling" into different output presets.

---

## HTML Visualization Improvements

The Plotly output remains the interactive Tier 1 artifact, but it was polished in a few ways.

### Basemap and General Styling

The interactive map now uses:

- `map_style="carto-positron"`

instead of a more basic OpenStreetMap presentation.

Reasoning:

- it is lighter and cleaner
- it keeps roads/coastline/context without competing heavily with the plume symbols
- it feels more presentation-ready with minimal extra styling work

### Local Time Messaging

The HTML title/subtitle now explicitly mention:

- Jan 14-25, 2025
- hourly PurpleAir observations
- EPA AQI colors
- reported fire start at Jan 16, 2025 5:35 PM PT

This matters because a self-contained HTML file may circulate without the surrounding handoff notes.

### Fire-Origin Marker

The HTML map still marks Moss Landing with a black `x`, but also includes a translucent red halo beneath it. This gives the origin more visual presence without turning it into a dominant annotation.

---

## GIF Export Path

### Why a Separate GIF Renderer Was Added

The GIF is aimed at a different use case than the HTML:

- slide decks
- quick sharing in chat/email
- documents where a browser-based widget is not practical

For that purpose, a deterministic frame renderer is more useful than a fully interactive web map.

### Renderer Choice

The GIF uses:

- `matplotlib.animation.FuncAnimation`
- `PillowWriter`

This was chosen because it is stable, dependency-light, and works cleanly with `uv run`.

### Default Frame Cadence

The GIF defaults to:

- every 3 hours
- 6 frames per second

This yields 88 frames for the Jan 14-25 period, which is a good compromise between smooth temporal progression and manageable file size.

The reasoning here is simple:

- hourly GIFs are possible, but they become longer/heavier and can feel repetitive
- 3-hour cadence still captures plume transport direction and multi-day intensity changes
- the full-hourly interactive HTML still exists for detailed scrubbing

### Sample Output Size

At the time of this session, `figures/tier1_bubble_map.gif` was approximately 602 KB, which is small enough to be practical for presentations and casual sharing.

---

## Adding a Basemap to the GIF

### Problem

The first GIF export worked technically, but looked sparse because it showed only points on a blank lat/lon background. For the Moss Landing story, geographic context matters: viewers need to immediately orient to Monterey Bay, Watsonville, Gilroy, Salinas, and the coast.

### Solution

The GIF renderer now attempts to import `contextily` and, if available, draws a Carto Positron tile basemap beneath the points:

```python
try:
    import contextily as cx
except ImportError:
    cx = None
```

and then:

```python
cx.add_basemap(
    ax,
    crs="EPSG:4326",
    source=cx.providers.CartoDB.Positron,
    attribution=False,
    zoom=10,
)
```

### Why This Was Implemented as Optional

`contextily` pulls in heavier GIS dependencies, including `rasterio`. That is acceptable for rendering, but it is not necessary for the entire project pipeline.

Making it optional was the right tradeoff because:

- the script still works without it
- the user can get a basic GIF even in a lighter Python environment
- a better-looking map is available whenever `contextily` is installed via `uv`

This is a graceful degradation approach rather than a hard dependency.

---

## Fire Event Annotation

### User Request

The exported visualization needed a clearer indicator of when the fire/explosion actually happened. The reported start time used in this session is:

- **Jan 16, 2025, 5:35 PM Pacific**

### Implementation

Two related pieces were added to the GIF:

1. A status box in the upper-right corner
2. A growing ring centered on Moss Landing

The status box shows:

- `Pre-fire baseline` before the event time
- `Fire active` afterward, along with elapsed hours since ignition

The growing ring appears only after the fire starts.

### Why a Growing Ring Was Chosen

This is not meant to represent a blast radius or physically modeled plume edge. It is a narrative cue marking the event origin in time.

It works well because:

- it is visually obvious without being text-heavy
- it ties the timing cue directly to Moss Landing's location
- it helps viewers understand that the plume is a response to a known event, not just ambient fluctuation

This is an annotation device, not an analytical layer.

### Important Caveat

The handoff should preserve that the ring is symbolic. If this project evolves toward publication or scientific presentation, the annotation should either be explicitly labeled as a fire-start marker or replaced with a more restrained timeline/event indicator.

---

## Title/Timestamp Layout Fix

### Problem Encountered

After the first GIF refinement pass, the timestamp text still collided with the main title. The initial attempt moved the date upward, but because both pieces of text were anchored relative to the plotting axes, they effectively shifted together.

### Fix

The title and timestamp were moved into figure-level text rather than axes-level text:

- `fig.suptitle(...)` for the main title
- `fig.text(...)` for the timestamp line

The figure top margin was also opened with:

```python
fig.subplots_adjust(top=0.86)
```

### Why This Works Better

Axes coordinates are convenient until annotations begin competing for the same space. Once a plot has a title, a subtitle, a legend, and corner status boxes, figure-level layout is more reliable. This fix separates "page furniture" from "data area" and should be kept.

If more header elements are added later, consider migrating to a `GridSpec` or dedicated header strip.

---

## Current Rebuild Commands

The current reproducible commands are:

### HTML

```bash
uv run --with pandas --with numpy --with plotly --with matplotlib python scripts/tier1_bubble_map.py --html
```

### GIF with basemap

```bash
uv run --with pandas --with numpy --with matplotlib --with contextily python scripts/tier1_bubble_map.py --gif
```

### GIF with denser temporal sampling

```bash
uv run --with pandas --with numpy --with matplotlib --with contextily python scripts/tier1_bubble_map.py --gif --gif-step-hours 1
```

### Combined HTML + GIF

```bash
uv run --with pandas --with numpy --with plotly --with matplotlib --with contextily python scripts/tier1_bubble_map.py --html --gif
```

---

## Updated State of Tier 1

Tier 1 is now effectively split into two deliverables rather than one:

### 1. Interactive analysis artifact

- `figures/tier1_bubble_map.html`
- Best for detailed inspection, scrubbing, hovering, and exploring all frames

### 2. Communication artifact

- `figures/tier1_bubble_map.gif`
- Best for embedding in slides, quick reviews, or sending to collaborators

This split is probably worth keeping. In practice, one artifact rarely serves both exploration and communication equally well.

---

## Known Limitations After This Session

Even after the refinement pass, several limitations remain:

### 1. The GIF is still a point-based map, not a continuous plume field

It communicates sensor behavior and transport direction well, but it does not depict a continuous concentration surface between sensors. Tier 2 interpolation is still the next major leap in realism.

### 2. No wind vectors yet

The animation shows *what* happened but not yet *why the plume moved the way it did*. Wind context remains the most useful next explanatory layer.

### 3. Event timing is approximate and narrative-facing

The fire-start annotation uses a reported start time of 5:35 PM PT on Jan 16, 2025. If a more authoritative ignition/explosion timeline is obtained later, update the constant in the script and document the source.

### 4. The GIF basemap depends on optional rendering dependencies

If `contextily` is unavailable, the script will still render the GIF, but without the geographic tile background.

### 5. The handoff earlier mentions `.venv/`

That reflects an earlier work session, not the currently verified path. The current tested workflow in this workspace is `uv run --with ...`.

---

## Recommended Next Steps From Here

If work resumes from this point, the most sensible next steps are:

1. Add wind context to Tier 1.
   Mesonet or HRRR wind vectors would explain directionality and likely add more insight than further cosmetic map tuning.

2. Build a smooth Tier 2 surface.
   Even a relatively simple inverse-distance interpolation would make the animation read more like a plume instead of a sensor network.

3. Add one or two curated narrative overlays.
   Examples: label the strongest impacted corridor, annotate the first major spike near Moss Landing, or add a compact ignition marker on the time axis.

4. Decide whether the primary audience is scientific, public-facing, or presentation-facing.
   That will determine whether the next version should optimize for accuracy/traceability, aesthetic clarity, or storytelling.

5. If this is headed for publication or formal presentation, record the source used for the 5:35 PM event time.
   Right now it is encoded as a project assumption/request from this work session and should be backed by a citation if it becomes part of a figure caption.
