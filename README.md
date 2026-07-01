# Moss Landing Fire

Research workspace for analyzing the January 2025 Moss Landing battery fire with:

- PurpleAir PM2.5 observations
- HYSPLIT forward dispersion driven by HRRR meteorology
- comparison workflows that score modeled plume scenarios against observed 4-hour PurpleAir enhancement patterns

This is not a polished package. It is a working research repo with reproducible scripts, intermediate datasets, visualization outputs, and a progress report.

## Main Folders

- `scripts/purple_air/` PurpleAir discovery, pulls, cleaning, enhancement windows, kriging, and visualization
- `scripts/hysplit/` forward dispersion, custom `cdump` rendering, sweeps, and scoring
- `data/purple_air/` local PurpleAir datasets and district boundary data
- `figures/visualization/` generated maps, animations, comparison sheets, and galleries
- `docs/` handoff notes, references, and status docs
- `report/` LaTeX progress report

## Environment

- Python `3.12`
- dependencies are defined in [pyproject.toml](/home/magnetesim/Documents/project/moss_landing_fire/pyproject.toml)
- local API secret lives in `purple_air_api.txt`
- HRRR meteorology should live in `hrrr/`

Example setup:

```bash
uv sync
cp purple_air_api.txt.example purple_air_api.txt
```

To download the required HRRR archive blocks for a simulation window:

```bash
./.venv/bin/python scripts/hysplit/download_hrrr.py \
  --start-utc 2025-01-16T23:00:00Z \
  --end-utc 2025-01-18T06:00:00Z
```

## Quick Start

Rebuild a PurpleAir raw map:

```bash
./.venv/bin/python scripts/purple_air/tier1_bubble_map.py --html --gif --basemap-style gray
```

Run the default scored HYSPLIT phase-1 sweep:

```bash
./.venv/bin/python scripts/hysplit/run_phase1_sweep.py --jobs 16 --score
```

Build the top-scenario comparison gallery:

```bash
./.venv/bin/python scripts/hysplit/build_phase1_comparison_gallery.py --top-n 4
```

Regenerate the main report images:

```bash
./.venv/bin/python scripts/report/render_key_figures.py
```

## Current State

The PurpleAir and HYSPLIT pipelines are both working. The current research question is how closely HYSPLIT can reproduce the observed PurpleAir enhancement pattern, and how sensitive that answer is to source assumptions like release height, duration, and source geometry.

For a fuller status snapshot, see [docs/project_status.md](/home/magnetesim/Documents/project/moss_landing_fire/docs/project_status.md).
