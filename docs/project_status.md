# Project Status

## Project

Moss Landing battery fire analysis workspace combining:

- PurpleAir PM2.5 acquisition, cleaning, enhancement windows, and visualization
- HYSPLIT forward dispersion driven by HRRR meteorology
- HYSPLIT/PurpleAir comparison and scoring workflows
- report-writing support for the independent-study progress update

Project root:

- `~/Documents/project/moss_landing_fire`

Status date:

- `2026-06-29`

## Current Summary

The project now has two working analysis tracks:

1. PurpleAir observation processing
2. HYSPLIT forward-dispersion modeling

Those tracks are connected by a comparison/scoring workflow that ranks HYSPLIT source-term scenarios against PurpleAir 4-hour enhancement windows.

The main result so far is not a validated plume reconstruction. The stronger result is that:

- PurpleAir clearly shows spatially structured enhancement during the event
- HYSPLIT results are highly sensitive to source assumptions
- even the better HYSPLIT scenarios still differ meaningfully from the observed PurpleAir pattern

That mismatch is now documented visually and numerically.

## What Is Working

### PurpleAir

- PurpleAir API key loading from `purple_air_api.txt`
- district-wide sensor discovery for Monterey Bay Unified APCD
- active-sensor filtering
- historical data pull and CSV-based rebuilds
- precleaning for stuck sensors and obvious spikes
- per-sensor baseline construction
- enhancement dataset creation
- 4-hour enhancement window generation
- static, HTML, and GIF visualization products
- kriging/interpolation with:
  - district clipping
  - nearest-sensor distance masking
  - optional sensor exclusion
- grayscale basemap rendering for cleaner sensor readability

### HYSPLIT

- forward dispersion runs with separate:
  - simulation start
  - release start
  - sampling-window timing
- 4-hour integrated sample windows
- point and `area_grid` source definitions
- parameter sweeps with `--jobs`
- custom `cdump` rendering to PNG/CSV/JSON
- comparison-mode rendering against PurpleAir
- sweep scoring against PurpleAir windows
- top-scenario gallery generation

### Reporting / Organization

- LaTeX progress report exists
- visualization outputs are organized by product family
- phase-1 comparison gallery exists locally
- remote PC workflow was proven for larger sweeps

## Main Open Problems

- HYSPLIT concentration magnitudes are still relative/model-internal for most comparisons, not physically calibrated to an external concentration target
- source-term uncertainty remains large:
  - release height
  - emission duration
  - source footprint
  - temporal emission profile
  - potential plume-rise effects
- PurpleAir QA is better than before but still not fully production-grade
- kriging/interpolation can still be biased by sparse regions and local outliers
- cluster-scale sweep tooling has been discussed but not yet implemented
- repository portability is still being cleaned up for Git use

## Important Inputs

### Secrets / Local-only

- `purple_air_api.txt`

This file should stay out of Git.

### PurpleAir Data

- `data/purple_air/sensors.csv`
- `data/purple_air/sensors_active.csv`
- `data/purple_air/sensors_mbuapcd.csv`
- `data/purple_air/sensors_mbuapcd_active.csv`
- `data/purple_air/sensors_mbuapcd_active_cleaned.csv`
- `data/purple_air/moss_landing_pm25.csv`
- `data/purple_air/mbuapcd_pm25.csv`
- `data/purple_air/mbuapcd_pm25_cleaned.csv`
- `data/purple_air/mbuapcd_sensor_baselines.csv`
- `data/purple_air/mbuapcd_pm25_enhancement.csv`
- `data/purple_air/mbuapcd_pm25_enhancement_4h.csv`
- `data/purple_air/mbuapcd_pm25_enhancement_4h_no72253.csv`
- `data/purple_air/receptor_events.csv`
- `data/purple_air/mbuapcd_cleaning_sensor_report.csv`
- `data/purple_air/mbuapcd_cleaning_row_report.csv`
- `data/purple_air/monterey_bay_unified_apcd.geojson`

### Meteorology / HYSPLIT

- `hrrr/`
- `hysplit/`

### Reference Docs

- `docs/MLVPP-Fire-EAP_OP3-20250118.pdf`
- `docs/7.-MLVPP-Fire-EAP_OP2-20250117.pdf`
- `docs/item11_stfrpt.pdf`
- `docs/moss_landing_plume_handoff.md`

## Important Scripts

### PurpleAir

- `scripts/purple_air/discovery.py`
- `scripts/purple_air/filter_active_sensors.py`
- `scripts/purple_air/pull_data.py`
- `scripts/purple_air/preclean_dataset.py`
- `scripts/purple_air/build_enhancement_dataset.py`
- `scripts/purple_air/build_4h_enhancement_windows.py`
- `scripts/purple_air/tier1_bubble_map.py`
- `scripts/purple_air/krige_enhancement.py`
- `scripts/purple_air/krige_enhancement_html.py`
- `scripts/purple_air/animate_krige_enhancement.py`
- `scripts/purple_air/sanity_check.py`

### HYSPLIT

- `scripts/hysplit/download_hrrr.py`
- `scripts/hysplit/run_forward_dispersion.py`
- `scripts/hysplit/run_forward_sensitivity.py`
- `scripts/hysplit/run_forward_time_height_ensemble.py`
- `scripts/hysplit/run_phase1_sweep.py`
- `scripts/hysplit/plot_cdump.py`
- `scripts/hysplit/score_against_purpleair.py`
- `scripts/hysplit/build_comparison_mode_sheet.py`
- `scripts/hysplit/build_kriging_comparison_sheet.py`
- `scripts/hysplit/build_phase1_comparison_gallery.py`
- `scripts/hysplit/build_contact_sheet.py`
- `scripts/hysplit/run_backward_trajectories.py`
- `scripts/hysplit/extract_receptor_events.py`
- `scripts/hysplit/plot_trajectory_overview.py`

### Report

- `scripts/report/render_key_figures.py`

## Most Useful Outputs Right Now

### PurpleAir Raw / Enhancement

- `figures/visualization/raw/mbuapcd_bubble_map.html`
- `figures/visualization/raw/mbuapcd_bubble_map.gif`
- `figures/visualization/enhancement/mbuapcd_enhancement_4h_map.html`
- `figures/visualization/enhancement/mbuapcd_enhancement_4h_map.gif`
- `figures/visualization/enhancement/mbuapcd_enhancement_4h_window0.png`

### PurpleAir Kriging

- `figures/visualization/kriging/mbuapcd_enhancement_krige_w-6_w12_no72253_sc_watsonville.html`
- `figures/visualization/kriging/mbuapcd_enhancement_krige_w-6_w12_no72253_sc_watsonville_slow.gif`
- `figures/visualization/kriging/compare_exp8km/window1_exp8km.png`
- `figures/visualization/kriging/compare_exp8km/window4_exp8km.png`
- `figures/visualization/kriging/compare_exp8km/window7_exp8km.png`
- `figures/visualization/kriging/compare_exp8km/window10_exp8km.png`

### HYSPLIT / PurpleAir Comparison Sheets

- `figures/visualization/comparison_sheets/purpleair_vs_hysplit_comparison_mode_25m_no_window0.png`
- `figures/visualization/comparison_sheets/purpleair_vs_hysplit_comparison_mode_50m_no_window0.png`
- `figures/visualization/comparison_sheets/kriging_vs_hysplit_25m_focus_no_window0.png`
- `figures/visualization/comparison_sheets/kriging_vs_hysplit_exp8km.png`

### Phase-1 Ranked Sweep Results

- `figures/visualization/phase1_gallery_20260622/top_scenarios_gallery.png`
- `figures/visualization/phase1_gallery_20260622/top_scenarios.csv`

Top phase-1 scenarios from the current scoring run:

- `h10_dur12_area9x5_fp900x360` with mean score `0.356`
- `h10_dur24_area9x5_fp900x360` with mean score `0.345`
- `h25_dur12_area9x5_fp900x360` with mean score `0.328`
- `h100_dur12_area9x5_fp900x360` with mean score `0.325`

Interpretation:

- higher score is better
- scores are composite similarity scores, not physical validation scores
- current “best” scenarios are still only moderate matches

### Report

- `report/moss_landing_progress_report.tex`
- `report/moss_landing_progress_report.pdf`

## PurpleAir Notes

- the current workflow uses the Monterey Bay Unified APCD district boundary
- one recurrent suspect sensor has been treated specially in kriging work:
  - `72253`
- the `no72253` outputs are often the cleaner visual products
- interpolation outside well-supported sensor regions should not be over-interpreted
- raw PM2.5 and enhancement are both available, but enhancement is the more useful comparison field for the fire event

## HYSPLIT Notes

- area-source approximations behave more plausibly than the early point-source runs
- lower release heights and broader area footprints tended to rank better in the phase-1 sweep
- 4-hour windows are the right comparison unit for the current study
- custom Python rendering is preferred over native HYSPLIT PDF products for interpretation

## Typical Commands

### Rebuild PurpleAir Raw Maps

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/purple_air/tier1_bubble_map.py \
  --html --gif \
  --data-csv data/purple_air/mbuapcd_pm25.csv \
  --sensor-csv data/purple_air/sensors_mbuapcd_active.csv \
  --boundary-geojson data/purple_air/monterey_bay_unified_apcd.geojson \
  --html-out figures/visualization/raw/mbuapcd_bubble_map.html \
  --gif-out figures/visualization/raw/mbuapcd_bubble_map.gif \
  --filter-report figures/visualization/raw/mbuapcd_bubble_map_filtered_sensors.csv \
  --basemap-style gray
```

### Rebuild PurpleAir 4-hour Enhancement Maps

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/purple_air/tier1_bubble_map.py \
  --mode enhancement \
  --html --gif \
  --gif-step-hours 1 \
  --gif-fps 4 \
  --data-csv data/purple_air/mbuapcd_pm25_enhancement_4h.csv \
  --sensor-csv data/purple_air/sensors_mbuapcd_active_cleaned.csv \
  --boundary-geojson data/purple_air/monterey_bay_unified_apcd.geojson \
  --html-out figures/visualization/enhancement/mbuapcd_enhancement_4h_map.html \
  --gif-out figures/visualization/enhancement/mbuapcd_enhancement_4h_map.gif \
  --basemap-style gray
```

### Build a Kriged Enhancement Animation / HTML

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/purple_air/animate_krige_enhancement.py \
  --input-csv data/purple_air/mbuapcd_pm25_enhancement_4h.csv \
  --exclude-sensor 72253 \
  --variogram-model exponential \
  --distance-mask-km 8 \
  --gif-out figures/visualization/kriging/mbuapcd_enhancement_krige_w-6_w12_no72253_sc_watsonville_slow.gif
```

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/purple_air/krige_enhancement_html.py \
  --input-csv data/purple_air/mbuapcd_pm25_enhancement_4h.csv \
  --exclude-sensor 72253 \
  --variogram-model exponential \
  --distance-mask-km 8 \
  --output-html figures/visualization/kriging/mbuapcd_enhancement_krige_w-6_w12_no72253_sc_watsonville.html
```

### Run a Forward Dispersion Sweep

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/hysplit/run_phase1_sweep.py \
  --jobs 16 \
  --score
```

### Render a Custom HYSPLIT PNG from `cdump`

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/hysplit/plot_cdump.py \
  hysplit/runs/forward_dispersion/sweeps/page6_area_h10_eh31_er1_src5x3_t2025011623_to_2025011806_h0010_srcarea5x3/cdump \
  --basemap \
  --basemap-style satellite \
  --view plume
```

### Rebuild the Phase-1 Comparison Gallery

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/hysplit/build_phase1_comparison_gallery.py \
  --per-run-csv hysplit/runs/forward_dispersion/sweeps/scoring/phase1_matrix_20260622d_manifest_per_run_scores.csv \
  --per-scenario-csv hysplit/runs/forward_dispersion/sweeps/scoring/phase1_matrix_20260622d_manifest_scenario_scores.csv \
  --output-dir figures/visualization/phase1_gallery_20260622 \
  --top-n 4 \
  --rows 1,4,7,10
```

## Cluster / Scale-up Direction

Planned next step for larger compute:

- split sweeps into manifest-driven shards
- run shards as cluster array jobs
- merge shard manifests afterward
- score and rank in a separate postprocessing step

The project is ready for this refactor conceptually, but the cluster tooling has not been written yet.

## Recommended Next Steps

1. Add Git hygiene before publishing:
   - `.gitignore`
   - exclude secrets
   - exclude large transient outputs if desired
2. Make the sweep runner cluster-friendly:
   - manifest builder
   - shard runner
   - merge/scoring driver
3. Expand the source-term matrix:
   - footprint size
   - release duration
   - temporal emission profile
   - source rotation
4. Improve PurpleAir QA:
   - reusable blacklist file
   - stronger outlier logic
5. Keep building side-by-side visual comparison products for report/presentation use

## Bottom Line

This is now a real working research codebase rather than a loose pile of exploratory scripts.

It already supports:

- sensor discovery and preprocessing
- PurpleAir observation visualization
- kriged enhancement products
- HYSPLIT forward modeling
- scenario sweeps
- model/observation comparison
- basic scenario ranking

What it does not yet support is a final, validated plume reconstruction or a cluster-native sweep architecture. Those are the next major steps.
