# Moss HYSPLIT + PurpleAir Attribution Handoff

**Date:** June 5, 2026  
**Machine:** Ubuntu 24.04 LTS laptop  
**Project root:** `~/Documents/project/moss_hysplit/`

---

## What This Project Is Doing

This workspace is now set up to test whether PM2.5 spikes observed by PurpleAir sensors can be traced back to the Moss Landing battery fire using HYSPLIT backward trajectories driven by HRRR meteorology.

The current workflow is:

1. take hourly PurpleAir PM2.5 data
2. identify fire-related receptor spike events
3. run 24-hour backward trajectories from those sensor locations and event times
4. inspect or score whether those trajectories trace back toward Moss Landing

The project is no longer just at the single-test-trajectory stage. There is now a working batch pipeline and a first full 24-hour pilot batch has already been run.

---

## High-Level Status

### Working now

- HYSPLIT CLI works on this machine
- HRRR files in ARL format are readable by HYSPLIT
- PurpleAir data are copied into this workspace
- receptor events can be extracted from the PurpleAir time series
- batch backward trajectory generation works
- quick-look trajectory figures can be generated

### Current limitation

- local HRRR coverage is only Jan 16--18, 2025
- that is enough for a strong 24-hour pilot analysis on early post-fire spikes
- it is not enough for a full 48-hour or full-window attribution study

---

## Key Directories and Files

### Root-level docs

- `hysplit_setup_handoff.md`
  - original setup and troubleshooting handoff
- `moss_hysplit_current_handoff.md`
  - this current-state consolidated handoff

### HYSPLIT install

- `hysplit.v5.4.2_x86_64/`
  - installed HYSPLIT distribution
- `hysplit.v5.4.2_x86_64/exec/hyts_std`
  - trajectory model executable
- `hysplit.v5.4.2_x86_64/bdyfiles/`
  - HYSPLIT boundary/static files
- `hysplit.v5.4.2_x86_64/working/`
  - earlier manual test run directory

### Meteorology

- `hrrr_downloads/`
  - local HRRR ARL-format met files currently available

Currently present:

- `20250116_00-05_hrrr`
- `20250116_06-11_hrrr`
- `20250116_12-17_hrrr`
- `20250116_18-23_hrrr`
- `20250117_00-05_hrrr`
- `20250117_06-11_hrrr`
- `20250117_12-17_hrrr`
- `20250117_18-23_hrrr`
- `20250118_00-05_hrrr`
- `20250118_06-11_hrrr`
- `20250118_12-17_hrrr`
- `20250118_18-23_hrrr`

### PurpleAir data

- `purple_air_data/moss_landing_pm25.csv`
  - hourly PurpleAir PM2.5 history
- `purple_air_data/sensors_active.csv`
  - active historical sensors used for the plume dataset
- `purple_air_data/sensors.csv`
  - raw wider sensor metadata
- `purple_air_data/receptor_events.csv`
  - extracted receptor spike events for HYSPLIT

### Scripts added in this session

- `scripts/extract_receptor_events.py`
  - extracts post-fire receptor episodes from PurpleAir time series
- `scripts/run_backward_trajectories.py`
  - builds and runs batch HYSPLIT backward trajectories safely
- `scripts/plot_trajectory_overview.py`
  - makes simple trajectory overview PNGs from `tdump` outputs

### Main batch outputs

- `trajectory_runs_24h_primary_fixed/`
  - successful first-pass 24-hour batch output
- `trajectory_runs_24h_primary_fixed/trajectory_manifest.csv`
  - manifest of all completed and missing-met runs

### Figures

- `figures/trajectory_overview/all_trajectories_spaghetti.png`
- `figures/trajectory_overview/trajectories_by_height.png`
- `figures/trajectory_overview/representative_trajectories_50m.png`

---

## PurpleAir Receptor Event Workflow

### Inputs

- `purple_air_data/moss_landing_pm25.csv`
- `purple_air_data/sensors_active.csv`

### What the extraction script does

`scripts/extract_receptor_events.py`:

1. reads hourly PM2.5 data
2. computes a per-sensor pre-fire baseline
3. computes a robust threshold using median + MAD with a minimum absolute threshold
4. identifies post-fire exceedance periods
5. groups them into episodes
6. records onset, peak, end, duration, and event intensity stats
7. labels the earliest post-fire event per sensor as `is_primary_event`

### Important design choice

This is better than simply using the absolute max per sensor because:

- some sensors have non-fire baseline pollution
- some sensors have multiple post-fire pulses
- the first major post-fire arrival is often the better receptor time for attribution

### Current extraction result

Verified current result:

- `33,935` PurpleAir rows
- `132` sensors
- `804` receptor events
- `118` primary events

---

## HYSPLIT Batch Workflow

### Script

- `scripts/run_backward_trajectories.py`

### What it does

For each selected receptor event, it:

1. selects the event timestamp, usually `peak_time_utc` or optionally `onset_time_utc`
2. computes which HRRR files are required for the requested backward duration
3. creates a unique run directory
4. writes a HYSPLIT `CONTROL` file using the known-good explicit met-file-pair format
5. runs `hyts_std`
6. records the outcome in a manifest CSV

### Important HYSPLIT-specific gotcha

The safe `CONTROL` style in this build is:

- `N 1`
- then `N` explicit `(directory, filename)` pairs

The shorter `1 9` style from the docs was previously found to be unreliable in this install and should not be trusted for batch work.

### Another important fix

When batch runs were first executed outside the HYSPLIT tree, HYSPLIT looked for:

```text
../bdyfiles/ASCDATA.CFG
```

That caused false-success runs that only wrote `tdump` headers.

The script now fixes this by:

- creating a `bdyfiles` symlink at the batch root pointing to the real HYSPLIT `bdyfiles`
- checking that `tdump` contains actual trajectory rows before calling a run complete

This fix is already in place.

---

## First Real Batch Run

### Command used

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --durations-hours 24 \
  --heights-agl 10,50,200,500 \
  --output-root trajectory_runs_24h_primary_fixed
```

### Result

- `424` completed trajectories
- `48` missing-met runs
- `106` completed receptor events
- `12` receptor events skipped due to missing meteorology

### Covered event-time range

- `2025-01-17 02:00 UTC` to `2025-01-18 12:00 UTC`

### What one completed run directory contains

Example:

- `trajectory_runs_24h_primary_fixed/sensor_5488_event_001_episode_001_t2025011708_d24_h0050/`

Files inside:

- `CONTROL`
- `tdump`
- `run.log`
- `MESSAGE`
- `TRAJ.CFG`
- `WARNING`

`run.log` for valid runs ends with `Complete Hysplit`.

---

## What the Current HRRR Archive Supports

Using the 118 primary receptor events and dry-run coverage checks:

### 24-hour backward runs

- `106` covered
- `12` missing

### 36-hour backward runs

- `61` covered
- `57` missing

### 48-hour backward runs

- `22` covered
- `96` missing

### Interpretation

This means you can already do a meaningful first-pass attribution analysis for the main early plume response, especially at 24 hours.

It also means:

- later recirculation events are not yet covered well
- most 48-hour runs need more met data
- a complete all-event analysis still requires additional HRRR downloads or a switch to a larger-domain met product like GDAS

---

## Figures Available Right Now

These are quick-look figures, not polished publication graphics.

### 1. All trajectories spaghetti plot

- `figures/trajectory_overview/all_trajectories_spaghetti.png`

Shows all completed 24-hour back-trajectories overlaid on a basemap, colored by starting height.

### 2. By-height panel

- `figures/trajectory_overview/trajectories_by_height.png`

Shows four panels split by:

- `10 m AGL`
- `50 m AGL`
- `200 m AGL`
- `500 m AGL`

### 3. Representative subset

- `figures/trajectory_overview/representative_trajectories_50m.png`

Shows a smaller set of 50 m AGL runs for higher-PM2.5 sensors so the paths are easier to read individually.

### Figure generation command

```bash
uv run --with pandas --with matplotlib --with contextily python scripts/plot_trajectory_overview.py
```

If `contextily` is not available, the script can still fall back to a plain background.

---

## Recommended Commands

### Rebuild receptor events

```bash
uv run --with pandas --with numpy python scripts/extract_receptor_events.py
```

### Dry-run coverage check

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --durations-hours 24 \
  --dry-run
```

### Run real 24-hour trajectories

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --durations-hours 24 \
  --heights-agl 10,50,200,500 \
  --output-root trajectory_runs_24h_primary_fixed
```

### Run using onset time instead of peak time

```bash
uv run --with pandas python scripts/run_backward_trajectories.py \
  --primary-only \
  --time-column onset_time_utc \
  --durations-hours 24
```

### Rebuild overview figures with basemap

```bash
uv run --with pandas --with matplotlib --with contextily python scripts/plot_trajectory_overview.py
```

---

## What Has Not Been Done Yet

The batch trajectories exist, but the source-attribution scoring layer is still missing.

Specifically, there is not yet a script that:

1. parses all `tdump` files
2. computes minimum distance to Moss Landing
3. records the time-before-arrival of closest approach
4. records the altitude at closest approach
5. classifies each run as strong, moderate, or weak support for Moss Landing attribution

That is the most important next analytical step.

---

## Best Next Steps

### Immediate next step

Write a `tdump` scoring/parser script.

This should produce a table with one row per run containing at least:

- sensor index
- event time
- height
- duration
- minimum distance to Moss Landing
- age hour at minimum distance
- altitude at minimum distance
- a simple source-support classification

### After that

1. summarize the fraction of runs that pass near Moss Landing
2. compare results across heights
3. compare peak-time vs onset-time trajectories
4. expand HRRR coverage to Jan 14--15 and Jan 19+
5. consider forward trajectories or dispersion from Moss Landing as a second line of evidence

### Longer-term

If the trajectories need to extend much farther back in time, consider switching to GDAS because HRRR edge effects and local coverage limits will become more important.

---

## Practical Bottom Line

You now have:

- a working HYSPLIT install
- PurpleAir receptor-event extraction
- a functioning batch backward-trajectory pipeline
- a completed first-pass 24-hour run for most early primary events
- simple overview figures with basemaps

You do **not** yet have the final attribution metric, but the project is now in a state where that can be added directly on top of real batch outputs instead of starting from scratch.
