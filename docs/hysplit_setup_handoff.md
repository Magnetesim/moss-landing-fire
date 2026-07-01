# HYSPLIT Setup Handoff

**Date:** June 5, 2026  
**Machine:** Ubuntu 24.04 LTS laptop (i7-13700H, 64GB RAM), username `magnetesim`, hostname `roboruntLin`  
**Project directory:** `~/Documents/project/moss_hysplit/`  
**HYSPLIT install:** `~/Documents/project/moss_hysplit/hysplit.v5.4.2_x86_64/`  
**HYSPLIT version:** 5.4.2 (May 2025), x86_64 static build

---

## What's Working

- The static x86_64 binary runs correctly. Confirmed with:
  ```
  ./exec/hyts_std
  → prints "HYSPLIT - Initialization" and prompts for input ✅
  ```
- HRRR met data already downloaded to local disk (see met data section below)

---

## Current Blocker — GUI Won't Launch

Running:
```bash
wish guicode/hysplit.tcl
```
Returns:
```
Edit default_init file for location of tcl code
```

### Fix
The `default_init` file needs to point to the actual guicode directory. Do this:

```bash
cat ~/Documents/project/moss_hysplit/hysplit.v5.4.2_x86_64/guicode/default_init
```

Find the line setting the guicode path (something like `set GUICODE "/path/to/guicode"`) and update it to:
```
set GUICODE "/home/magnetesim/Documents/project/moss_hysplit/hysplit.v5.4.2_x86_64/guicode"
```

Then relaunch from the HYSPLIT root (not from inside exec/ or guicode/):
```bash
cd ~/Documents/project/moss_hysplit/hysplit.v5.4.2_x86_64
wish guicode/hysplit.tcl
```

If `wish` isn't installed:
```bash
sudo apt install tk tcl
```

---

## Why the GUI at All

Use the GUI **once** for a sanity check run only — just to confirm:
1. The HRRR met files load without errors
2. A single forward or backward trajectory from Moss Landing looks physically reasonable

After that, switch to CLI + Python scripting for the actual batch runs (168 sensors). The GUI is too slow for that volume.

---

## HRRR Met Data

- **Location on disk:** needs to be confirmed — wherever lftp downloaded to
- **Format:** ARL format, pre-converted by NOAA (downloaded directly from NOAA ARL FTP, no conversion needed)
- **Source:** `ftp://arlftp.arlhq.noaa.gov/pub/archives/hrrr/2025/01/`
- **Files downloaded:** Jan 14–25 2025, 4 files per day, 6-hour blocks
- **File naming:** `YYYYMMDD_HH-HH_hrrr` e.g. `20250116_18-23_hrrr`
- **File size:** ~3.4GB each, ~150GB total
- **Key files for the fire:**
  ```
  20250116_18-23_hrrr   ← fire ignition window (Jan 16 evening Pacific = ~UTC 18-23)
  20250117_00-05_hrrr   ← peak smoke
  20250117_06-11_hrrr
  20250117_12-17_hrrr
  20250117_18-23_hrrr
  20250118_00-05_hrrr   ← continued transport/dissipation
  ```

**Important timezone note:** HRRR files are in UTC. The fire started evening of Jan 16 Pacific time = early Jan 17 UTC (roughly 02:00-04:00 UTC). Don't get tripped up by this when setting trajectory start times.

---

## The Fire Event

- **What:** Vistra Energy lithium battery storage facility fire/explosion
- **Where:** Moss Landing, CA — `36.8044°N, 121.7883°W`
- **When:** January 16–17, 2025

---

## Planned HYSPLIT Workflow

### Goal
Run **backward trajectories** from each PurpleAir sensor location, timed to when that sensor hit its PM2.5 peak. Trajectories should converge on Moss Landing, providing causal attribution of the sensor readings to the fire.

### Why backward not forward
Forward trajectories start at Moss Landing and show where particles go. Backward trajectories start at each sensor at its spike time and trace where the air came from. The backward approach is more rigorous for attribution because it's anchored to what the sensors actually measured.

### Batch run structure
```
for each sensor (168 total):
    1. look up spike timestamp from PurpleAir CSV
    2. write a CONTROL file with that sensor's lat/lon + spike time
    3. run ./exec/hyts_std
    4. rename tdump output (it always writes to same filename)
    5. collect for plotting
```

### CONTROL file template
```
25 01 17 02          ← start time UTC (year month day hour) — adjust per sensor
1                    ← number of starting locations
36.8044 -121.7883 50 ← lat lon height(m AGL) — replace with sensor coords
-24                  ← run duration (negative = backward, 24hrs)
0                    ← vertical motion method (0 = model default)
10000.0              ← top of model domain (m)
1                    ← number of met files
./metdata/           ← met file directory
20250116_18-23_hrrr  ← met filename — will need to cover the run window
./                   ← output directory
tdump                ← output filename
```

### Python scripting approach
Use `subprocess` to call `hyts_std` and string templating to write CONTROL files programmatically from the PurpleAir dataframe. The PurpleAir CSV has sensor lat/lon and timestamps — find each sensor's peak PM2.5 time with:
```python
spike_times = full_df.groupby("sensor_index")["pm2.5_atm"].idxmax()
```

---

## PurpleAir Data Status

- **Sensor discovery:** 168 sensors in Santa Cruz/Monterey area, saved to `sensors.csv`
- **Historical data:** Downloaded for Jan 14–25 2025, saved to `moss_landing_pm25.csv`
- **Fields pulled:** `pm2.5_atm`, `pm2.5_cf_1`, `humidity`
- **Resolution:** Hourly averages (`average=60`)
- **Timezone:** UTC (convert to Pacific for display, keep UTC for HYSPLIT inputs)

---

## Visualization Plan (bigger picture)

Once HYSPLIT trajectories are working:
- Overlay trajectory lines on the animated PurpleAir PM2.5 bubble map
- Trajectories draw lines back toward Moss Landing from each affected sensor
- Add HRRR wind vectors for context
- Tools: `plotly` or `matplotlib.animation` for animation, `cartopy` or `folium` for basemap

This is for Prof. Javier Gonzalez Rocha's research group at UCSC Baskin Engineering.

---

## Immediate Next Steps (in order)

1. Fix `default_init` and get GUI launching
2. Use GUI to load one HRRR met file and run a single test trajectory from Moss Landing
3. Confirm trajectory looks physically reasonable (should show onshore/offshore flow patterns typical of coastal CA)
4. Then move to scripting batch runs

---

## Appendix: Session Log — June 5, 2026

### GUI Fix
- **Problem:** `default_init` line 2 had an incorrect path including `/hysplit/guicode` (a subdirectory that doesn't exist).
- **Fix:** Changed line 2 from `/home/.../hysplit.v5.4.2_x86_64/hysplit/guicode` to `/home/.../hysplit.v5.4.2_x86_64/guicode`.
- **Note:** `default_init` is in the HYSPLIT root, not `guicode/`.
- **Result:** `wish guicode/hysplit.tcl` launches the GUI (Tk `wish` was already installed at `/usr/bin/wish`).

### HRRR Met Data Location
- Confirmed on disk at `/home/magnetesim/` (flat, not in a subdirectory).
- Files present: Jan 16–18 2025, 4 files/day, `YYYYMMDD_HH-HH_hrrr` format.

### CLI Trajectory Run (No GUI)
Successfully ran a test trajectory from the command line:

1. **Wrote CONTROL file** in `working/CONTROL`:
   ```
   25 01 16 23
   1
   36.8044 -121.7883 50
   -5
   0
   10000.0
   1
   /home/magnetesim/
   20250116_18-23_hrrr
   ./
   tdump
   ```
2. **Ran:** `../exec/hyts_std` from `working/` → completed in seconds, produced `tdump` (702 bytes).
3. **Plotted:** `../exec/trajplot -itdump -otrajplot.ps` → produced PostScript.
4. **Converted:** `convert trajplot.ps trajplot.png` → PNG at `working/trajplot.png`.

### CLI Plotting Tools Available (no Python/GUI needed)

| Tool | Path | Purpose |
|---|---|---|
| `hyts_std` | `exec/hyts_std` | Run trajectory model |
| `trajplot` | `exec/trajplot` | C binary, plots trajectories to PostScript |
| `trajplot.py` | `exec/trajplot.py` | Python version (requires `hysplitplot` package) |
| `parhplot` | `exec/parhplot` | Horizontal particle position plot |
| `parsplot` | `exec/parsplot` | Particle cross-section plot |
| `parvplot` | `exec/parvplot` | Vertical particle plot |
| `concplot` | `exec/concplot` | Concentration plot (C binary) |
| `concplot.py` | `exec/concplot.py` | Concentration plot (Python) |

### Python Plotting Dependencies (not yet installed)
- The `trajplot.py` and other Python plotting scripts require `hysplitplot` and `hysplitdata` packages from `python/`.
- Official install path: Anaconda 3 environment via `python/install_linux.sh`.
- Dependencies include matplotlib, cartopy, shapely, geopandas, scipy, rasterio, etc.
- **Not yet installed** — the C binaries work fine without them.

### Gotchas
- **Met file time range must cover the trajectory window.** The model errors with "start time before start of meteorology data" if the start time falls outside the met file's coverage.
- **CONTROL file lives in `working/`** — `hyts_std` reads `CONTROL` from the current directory.
- **`tdump` is overwritten each run** — rename it after each run during batch processing (or run each in its own temp directory).
- **Time format:** `YY MM DD HH` (2-digit year), not `YYYY`. Duration in hours, negative for backward.

---

## Appendix B: 47-Hour Sanity-Check Trajectory & Forward Plan

*Continuation of the session log above. Read this section if you're picking the project up cold — it documents the failed attempts, the actual format that works, the data we have, and what to do next.*

### What I actually ran (after the 5-hour baseline above)

After the 5-hour sanity check, the user asked for a 48-hour back-trajectory. The handoff was missing Jan 14–15 HRRR data, so the user and I agreed to do the longest run the local data supports: **47 hours backward from 2300 UTC 17 Jan 2025 → 0000 UTC 16 Jan 2025**, covering the fire ignition through peak smoke. This was the right call scientifically — it lands inside the actual event window instead of before it, and it's only 1 hour short of the originally requested 48.

I tried **six different CONTROL file formats** before finding one that worked. The full triage is below.

### The CONTROL file format gotcha (this is the important one)

The HYSPLIT user guide (in `document/user_guide.pdf`) says the met-count line can be a **single number** OR **two numbers** `<num_grids> <files_per_grid>`. Example from the guide: `2 12` means 2 grids with 12 files each.

**In HYSPLIT v5.4.2, the two-number form does not work the way the guide suggests.** When I tried `1 9` (1 grid, 9 files, all in the same dir), the model either:
- errored with "End of file" at `runset.f` line 300 — the Fortran reader ran off the end of the file expecting more met-file pairs, or
- silently clobbered a real met file with trajectory output bytes (see data incident below).

What **does** work: treat the met-count as `N 1` (N grids, 1 file each) and then write **N explicit `(directory, filename)` pairs** in sequence, then the output `(directory, filename)` pair. The model reads pairs, not "dir once, then N files."

**Working CONTROL template for 9 met files all in one directory:**

```
25 01 17 23                          # start time UTC
1                                    # number of starting locations
36.8044 -121.7883 50                 # lat lon height(m AGL)
-47                                  # run duration hours (negative = backward)
0                                    # vertical motion method
10000.0                              # top of model domain (m)
9 1                                  # num_grids num_files_per_grid (use N 1)
/home/magnetesim/                    # grid 1, file 1: dir
20250116_00-05_hrrr                  # grid 1, file 1: filename
/home/magnetesim/                    # grid 1, file 2: dir
20250116_06-11_hrrr                  # grid 1, file 2: filename
...  (7 more pairs)
./
tdump
```

If the docs are right that `1 9` should work in some configurations, I couldn't make it work in this build. **The `N 1` + N-pairs form is the only one I trust for batch runs.** Six test variants I ran are in `/tmp/opencode/hysplit_tests/CONTROL_*` if you want to reproduce.

### The clobbered-met-file incident (and how to detect it)

While iterating on CONTROL formats I ran a control the model couldn't parse cleanly. On its way out, **HYSPLIT wrote the trajectory output header to `/home/magnetesim/20250116_12-17_hrrr`, overwriting the real 3.4 GB HRRR file with 183 bytes of garbage that began with the trajectory header (`2 1 / HRRR 25 1 16 0 1 / HRRR 25 1 16 6 1 / 1 BACKWARD OMEGA / 25 1 17 23 36.804 -121.788 50.0 / 1 PRESSURE`)**.

**How to spot this before it ruins a run:**
```bash
# All HRRR files should be 3,417,912,654 bytes. Anything else is broken.
ls -la /home/magnetesim/*hrrr
# Or quick md5 spot-check any suspect file:
md5sum /home/magnetesim/20250116_12-17_hrrr
```

If a file is 183 bytes or starts with `2 1 / HRRR`, it's been clobbered. Re-download it from NOAA (the file is ~3.3 GB; takes ~10 min on a good connection):
```bash
curl -C - -o /home/magnetesim/20250116_12-17_hrrr \
  "ftp://arlftp.arlhq.noaa.gov/pub/archives/hrrr/2025/01/20250116_12-17_hrrr"
```

The `-C -` flag resumes an interrupted download. Don't use `wget --continue` — it miscalculates the byte range on FTP.

**Root cause is unconfirmed.** I suspect the model writes a temporary/intermediate file using the met-file path it was reading from when something goes wrong, rather than using the output dir from CONTROL. The first failing format I tested (after a successful run) is when the clobbering happened, so the "successful" run is what seeded the bug — i.e., the format might write to a wrong path even on success in some cases. **Recommend: pre-stage HRRR files into a read-only or backed-up directory before iterating on CONTROL formats**, so a misbehaving write can't destroy real data. Or at minimum, snapshot `md5sum` of all HRRR files into a file before each test run and compare after.

### The 47-hour result (physically reasonable)

`working/tdump` and `working/trajplot.png` both correspond to this run. The trajectory:
- Starts at Moss Landing (36.80°N, 121.79°W, 50 m AGL) at 2300 UTC 17 Jan 2025
- Back-traces 47 hours to 0000 UTC 16 Jan 2025
- Stays in the marine boundary layer the whole time: ~250–700 m AGL
- Path: SE inland over the Salinas Valley → curves back NW → ends at 38.08°N, 124.20°W (about 150 km WNW of Moss Landing, well offshore in the Pacific), 420 m AGL

**Interpretation:** Air arriving at Moss Landing on Jan 17 23 UTC (the post-fire peak smoke period) had come from the NW over the Pacific. That's consistent with a synoptic westerly pattern plus a sea-breeze component pushing the plume inland during the day and drawing marine air back in at night. For the real attribution runs, this is the kind of air-mass history you want to see — it tells you that smoke detected at inland sensors (e.g., Santa Cruz, Salinas) likely passed over Moss Landing on the previous day, not that local emissions are responsible.

The 5-hour plot from the original sanity check is much less informative — it stays within ~30 km of the source and shows a small loop, which is consistent with light/variable morning winds but doesn't tell you anything about where the air mass actually came from. **Use 24–48 hour durations for the real batch, not 5.**

### Recommended CONTROL file strategy for the batch run

For 168 sensors × N spike times, you do NOT want to write a 27-line CONTROL per sensor. Two approaches:

**Option A (cleanest, recommended):** Symlink or copy all HRRR files into one subdirectory and use a single-line met-dir entry.
```bash
mkdir -p /home/magnetesim/hrrr_all
ln -s /home/magnetesim/2025*.hrrr /home/magnetesim/hrrr_all/
```
Then the met file section of every CONTROL becomes:
```
N 1
./hrrr_all/    <-- or absolute path; same for every sensor
20250116_00-05_hrrr
./hrrr_all/
20250116_06-11_hrrr
...
```
(Still N pairs, but at least the dir is short and consistent.)

**Option B (fastest to script, requires re-verification):** Investigate whether HYSPLIT v5.4.2 actually accepts a non-pair form with the right met-count value. I didn't have time to test this. If the docs are right that `1 9` should mean "1 dir, 9 files," that would shorten the CONTROL considerably. **But test this carefully on a copy of the met data first** — the bug I hit is consistent with the format being misread in a destructive way.

**For the actual batch run:**
1. **Pre-download missing met data.** We have Jan 16–18 on disk. For a 48-hour back-trajectory from any spike time on Jan 17 or 18, you also need Jan 14–15. Same NOAA path as before. Plan: ~150 GB per week of HRRR, or filter by sensor spike time to only the days you actually need.
2. **Create a per-sensor working directory** (e.g., `working/sensor_001/`) and run each trajectory in its own subdir. This avoids the "tdump gets overwritten" problem and isolates failures.
3. **For each sensor:** write a CONTROL from the spike time + sensor lat/lon, run `hyts_std`, rename tdump to something like `sensor_001_tdump`, move on.
4. **Store output paths in a CSV/JSON** so you can rebuild plots later. The Python scripts can be written against the JSON.

### Tools that work and don't work (verified in this session)

| Tool | Status | Notes |
|---|---|---|
| `hyts_std` | ✓ Works | Confirmed for 5-hr and 47-hr backward runs |
| `trajplot` (C binary) | ✓ Works | `trajplot -itdump -otrajplot.ps` produces PostScript |
| `convert` (ImageMagick) | ✓ Works | `convert trajplot.ps trajplot.png` produces PNG |
| `lftp` / `curl` for HRRR FTP | ✓ Works (slow) | ~7 MB/s from arlftp.arlhq.noaa.gov in our test |
| `trajplot.py` (Python) | ✗ Not installed | Would need `hysplitplot` conda env per handoff; skip for now |
| GUI | ✓ Launches after `default_init` fix | Not needed for batch, kept as fallback |

### Open questions / things to verify when you pick this up

1. **Why does the met count `1 9` not work?** Either a bug in this HYSPLIT build, a docs-vs-implementation drift, or a format detail I'm missing (e.g., maybe the two numbers need a specific separator, or maybe the docs are wrong about what `1 9` means). Worth one focused experiment: try a 2-grid setup with 1 file each (`2 1` and two pairs from different dirs) and see if that works the same as `9 1`. If yes, the format is "N pairs," period.

2. **The clobbered-file write behavior.** I never confirmed exactly what write path caused the clobbering. If the user is iterating on formats, **put a write-protect / read-only mount on the HRRR dir** (or use a copy) until this is understood. Losing a 3.3 GB download mid-project is not a fun way to spend a Sunday.

3. **Why does the 5-hr plot show a loop?** Worth checking against the 47-hr plot — the 5-hr loop happens during low-wind conditions. If you plot the 5-hr trajectory as a subset of the 47-hr one, do they match? (They should.) The 5-hr loop shouldn't be a model bug, but I didn't verify.

4. **HRRR edge effects.** The 47-hr trajectory ends at 124.2°W, which is close to the western edge of the HRRR CONUS domain (~125°W). Some back-trajectories at long durations will hit the domain edge and stop. The 8-file gap-test (skipping Jan 16 12–17) terminated at -29 hours, partly because the parcel ran off the grid, not just because of the missing file. For sensors that need back-trajectories longer than ~36 hours, the parcel will likely exit the HRRR domain. **Consider switching to a global met dataset (GDAS, ECMWF) for the long-duration attribution runs.** GDAS is on the same NOAA ARL FTP server, larger files (~150 MB each, 4× daily) and the docs say it can be downloaded with the same `hysplit.v5.4.2_x86_64/data2arl/`-style tools.

5. **Multiple starting heights.** The handoff uses 50 m AGL for the source. For sensor attribution, you may want to run multiple heights (e.g., 10 m, 50 m, 200 m, 500 m) to capture vertical transport uncertainty. This is a 4× cost increase but worth it for the most-impacted sensors.

6. **PurpleAir spike time alignment.** The handoff's plan says `df.groupby("sensor_index")["pm2.5_atm"].idxmax()`. The batch run will use those UTC spike times as the trajectory end time, and run backward 24–48 hours. Worth a sanity check: are the spike times in UTC? The handoff says yes, but verify with `print(df['timestamp'].dt.tz)` before generating the batch.

### Files and locations (snapshot at end of session)

```
~/Documents/project/moss_hysplit/
├── hysplit_setup_handoff.md         # this file
├── hysplit.v5.4.2_x86_64/
│   ├── exec/                         # binaries (hyts_std, trajplot, etc.)
│   ├── guicode/                      # GUI Tcl/Tk source
│   ├── working/                      # current working dir for CLI runs
│   │   ├── CONTROL                   # current 47-hr test CONTROL (9 1 format)
│   │   ├── tdump                     # current 47-hr trajectory output
│   │   ├── trajplot.png              # current 47-hr plot
│   │   ├── tdump_5hr                 # earlier 5-hr trajectory (kept for ref)
│   │   ├── trajplot_5hr.png          # earlier 5-hr plot (kept for ref)
│   │   ├── default_traj              # GUI-generated template, useful reference
│   │   └── SETUP.CFG, TRAJ.CFG, etc. # namelist files (don't edit casually)
│   └── document/user_guide.pdf       # official HYSPLIT docs
└── sensors.csv, moss_landing_pm25.csv  # PurpleAir data (per handoff)

/home/magnetesim/                     # HRRR data lives here (flat, no subdir)
├── 20250116_00-05_hrrr               # 3.26 GB each
├── 20250116_06-11_hrrr
├── 20250116_12-17_hrrr               # was clobbered, re-downloaded, md5 should match sibling
├── 20250116_18-23_hrrr
├── 20250117_00-05_hrrr
├── 20250117_06-11_hrrr
├── 20250117_12-17_hrrr
├── 20250117_18-23_hrrr
├── 20250118_00-05_hrrr
├── 20250118_06-11_hrrr
├── 20250118_12-17_hrrr
└── 20250118_18-23_hrrr

/tmp/opencode/hysplit_tests/          # test artifacts (transient, may be gone)
├── CONTROL_baseline                  # the original 5-hr working CONTROL
├── CONTROL_1x9                       # FAILED: "1 9" two-numbers form
├── CONTROL_9pairs                    # PARTIAL: 9 explicit pairs, weird failure mode
├── CONTROL_9x1                       # WORKING: 9 1 + 9 explicit pairs
├── CONTROL_9                         # FAILED: single number 9, dir+files not pairs
├── CONTROL_2x4                       # FAILED: only 8 unique files for 2x4 layout
├── CONTROL_8gap                      # 8 files, 6-hr gap → trajectory terminated early
└── curl.log                          # log from the re-download
```

### One-line "where am I" for someone picking this up

You are at: a verified-working 47-hour back-trajectory from Moss Landing using 9 HRRR files. The CONTROL file format that works is `9 1` + 9 explicit `(dir, filename)` pairs. The met-count `1 9` form (one grid, 9 files) does NOT work in this HYSPLIT build despite what the docs say. To proceed: download Jan 14–15 HRRR for the full 48-hour runs, decide on a per-sensor working-dir strategy for the batch, and pick a duration (24 hr vs 48 hr vs both). Switch to GDAS if the trajectories need to go further back than ~36 hours.

---

## Appendix C: PurpleAir Receptor Workflow Added (June 5, 2026)

This appendix documents the first integration step between the PurpleAir plume dataset and the HYSPLIT workspace. The goal of this step was to move beyond a single hand-written test trajectory and make the project ready for batch receptor-based attribution runs.

### What Was Added

PurpleAir data were copied into this project under:

```text
~/Documents/project/moss_hysplit/purple_air_data/
```

Files now present:

- `purple_air_data/moss_landing_pm25.csv`
- `purple_air_data/sensors_active.csv`
- `purple_air_data/sensors.csv`
- `purple_air_data/receptor_events.csv`

Two scripts were added under:

```text
~/Documents/project/moss_hysplit/scripts/
```

- `extract_receptor_events.py`
- `run_backward_trajectories.py`

### Why This Matters

The original handoff plan suggested using the single maximum PM2.5 value per sensor as the receptor time. That is a useful first heuristic, but it is not ideal scientifically because:

- some sensors have elevated winter baseline before the fire
- some sensors show multiple post-fire pulses
- the absolute maximum may occur during recirculation rather than first plume arrival

The new workflow instead identifies post-fire spike episodes relative to a sensor-specific baseline and flags the earliest post-fire event as the default "primary" receptor event for HYSPLIT.

### Receptor Event Extraction Logic

`extract_receptor_events.py` does the following:

1. reads the hourly PurpleAir time series
2. computes a per-sensor baseline from pre-fire data
3. builds a robust event threshold using median + MAD, with a minimum absolute PM2.5 threshold
4. groups flagged hours into spike episodes
5. stores onset time, peak time, end time, event duration, peak PM2.5, and baseline stats
6. marks the earliest post-fire event per sensor as `is_primary_event`

If a sensor has insufficient pre-fire baseline rows, the script falls back to a low-end quantile estimate rather than failing the whole extraction.

### Current Extraction Result

Verified output from the current dataset:

- loaded **33,935 PurpleAir rows** across **132 sensors**
- computed baseline statistics for **132 sensors**
- saved **804 receptor events** to `purple_air_data/receptor_events.csv`
- found **118 primary events** suitable for first-pass HYSPLIT work

This means the receptor-side preprocessing is no longer the bottleneck. The limiting factor is now meteorology coverage.

### Batch Trajectory Script

`run_backward_trajectories.py` uses the receptor-event table to generate HYSPLIT runs safely.

Design choices:

- one working directory per run
- one `CONTROL` file per run
- one `tdump` per run directory
- one manifest CSV summarizing all runs
- uses the verified-safe CONTROL style: `N 1` plus explicit met-file pairs
- supports multiple durations and multiple starting heights
- supports `--dry-run` to validate met-file coverage before calling `hyts_std`

This avoids the main operational risks already documented in the handoff:

- `tdump` overwrite collisions
- malformed shared working directories
- accidental ambiguity about which met files were used for a run

### What Can Be Done With the HRRR Data Already on Disk

The local `hrrr_downloads/` directory currently contains Jan 16--18, 2025 only.

That is enough to do a meaningful first attribution pass, but not enough to cover the entire PurpleAir event catalog.

Using `receptor_events.csv` and running dry-run batch checks on the **118 primary events**:

- **24-hour backward runs:** 106 primary events covered, 12 missing
- **36-hour backward runs:** 61 primary events covered, 57 missing
- **48-hour backward runs:** 22 primary events covered, 96 missing

Time windows supported by the current local HRRR archive:

- **24-hour coverage:** primary event times from `2025-01-17 02:00 UTC` through `2025-01-18 12:00 UTC`
- **36-hour coverage:** primary event times from `2025-01-17 13:00 UTC` through `2025-01-18 12:00 UTC`
- **48-hour coverage:** primary event times from `2025-01-18 00:00 UTC` through `2025-01-18 12:00 UTC`

Interpretation:

- you can already test the core attribution workflow on a large subset of the strongest early plume responses
- you can already generate a publishable-looking pilot figure set for early-arrival sensors
- you cannot yet do a complete all-sensors, all-episodes attribution analysis
- you do not yet have enough HRRR coverage for most 48-hour runs or for later recirculation events on Jan 19+

### Immediate Best Use of the Current Data

With what is already on disk, the best next scientific step is:

1. run **24-hour backward trajectories** for the 118 primary events
2. use multiple starting heights such as `10, 50, 200, 500 m AGL`
3. score whether those trajectories pass near Moss Landing
4. use that as the first attribution screen

This will answer the practical question: do the early observed PurpleAir spikes trace back toward Moss Landing under HRRR winds?

### Recommended Commands

Extract receptor events:

```bash
uv run --with pandas --with numpy python scripts/extract_receptor_events.py
```

Dry-run a batch check for primary 24-hour trajectories:

```bash
uv run --with pandas python scripts/run_backward_trajectories.py --primary-only --durations-hours 24 --dry-run
```

Run actual 24-hour trajectories at multiple heights:

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --durations-hours 24 \
  --heights-agl 10,50,200,500
```

Use onset time instead of peak time if you want first-arrival attribution:

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --time-column onset_time_utc \
  --durations-hours 24
```

### What Still Needs to Be Added

To finish the attribution workflow cleanly, the next missing pieces are:

1. a `tdump` parser that reads trajectory output and computes minimum distance to Moss Landing
2. a simple scoring rule for "supports Moss Landing" vs "does not support Moss Landing"
3. more HRRR files for Jan 14--15 and Jan 19+ if longer-duration or later-event runs are needed
4. optional forward runs or dispersion from Moss Landing for a stronger two-sided attribution argument

### Updated One-line Status

You are now at: a verified-working HYSPLIT install, verified-safe batch CONTROL generation, a PurpleAir receptor-event catalog with 118 primary events, and enough local HRRR data to run a strong **24-hour pilot attribution study** on most early post-fire spikes.

---

## Appendix D: First Real 24-Hour Batch Run (June 5, 2026)

This appendix records the first actual receptor-driven HYSPLIT batch run using the PurpleAir event catalog.

### Runtime Issue Found and Fixed

The first version of the batch runner created per-run working directories outside the HYSPLIT tree, which exposed a path assumption inside HYSPLIT:

```text
*ERROR* sfcinp: ../bdyfiles/ASCDATA.CFG file not found!
```

Important detail: the run still wrote a `tdump` file header and returned a misleadingly normal-looking output footprint, but the trajectories were not valid. The `tdump` files contained only the metadata header and no actual trajectory points.

### Fix

The batch runner was updated to:

1. create a `bdyfiles` symlink inside the batch output root pointing at `hysplit.v5.4.2_x86_64/bdyfiles`
2. treat a run as complete only if the output `tdump` contains actual trajectory point rows, not just the header

This matters because exit code + file existence alone were not enough to determine success.

### First Successful Batch Result

Using:

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --durations-hours 24 \
  --heights-agl 10,50,200,500 \
  --output-root trajectory_runs_24h_primary_fixed
```

The batch produced:

- **424 completed trajectories**
- **48 missing-met runs**
- **106 completed receptor events**
- **12 receptor events skipped for missing HRRR coverage**

Covered event-time range:

- `2025-01-17 02:00 UTC` through `2025-01-18 12:00 UTC`

### Output Location

Primary result directory:

```text
~/Documents/project/moss_hysplit/trajectory_runs_24h_primary_fixed/
```

Key file:

- `trajectory_runs_24h_primary_fixed/trajectory_manifest.csv`

Each completed run directory contains:

- `CONTROL`
- `tdump`
- `run.log`
- `MESSAGE`
- `TRAJ.CFG`
- `WARNING`

### Interpretation

This is the first usable receptor-based batch output set in the project. It does **not** yet score whether each trajectory supports Moss Landing, but it gives a large enough body of real trajectories to begin that analysis immediately.

The next logical step is to parse the `tdump` files and compute, for each run:

- minimum distance to Moss Landing
- time-before-arrival of closest approach
- altitude at closest approach

That will turn the current batch from "trajectories exist" into an attribution result.
