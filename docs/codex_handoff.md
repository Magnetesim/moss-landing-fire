# Codex Handoff

## Project Root

- `~/Documents/project/moss_landing_fire`

## Current Structure

- `data/purple_air/`
  - PurpleAir inputs and derived event tables
- `docs/`
  - prior handoffs, EAP PDF, and this file
- `figures/hysplit/`
  - trajectory overview figures
- `figures/visualization/`
  - PurpleAir visualization outputs
- `hrrr/`
  - local HRRR ARL-format meteorology
- `hysplit/install/hysplit.v5.4.2_x86_64/`
  - HYSPLIT install
- `hysplit/runs/`
  - backward trajectories, coverage runs, and forward dispersion runs
- `scripts/hysplit/`
  - HYSPLIT workflow scripts
- `scripts/purple_air/`
  - PurpleAir data pull and visualization scripts

## Important Files

- `purple_air_api.txt`
  - PurpleAir API key, now read by the PurpleAir scripts
- `docs/MLVPP-Fire-EAP_OP3-20250118.pdf`
  - county EAP containing the target plume-style map
- `scripts/hysplit/run_forward_dispersion.py`
  - new forward HYSPLIT concentration runner for recreating the PDF map

## Existing HYSPLIT Work

- Backward trajectory workflow still works under the new layout.
- Paths in the HYSPLIT scripts were updated to use the shared project root.
- Default trajectory-related data paths now point into:
  - `data/purple_air/`
  - `hrrr/`
  - `hysplit/install/...`
  - `hysplit/runs/...`

## New Forward Dispersion Script

Script:

- `scripts/hysplit/run_forward_dispersion.py`

What it does:

- writes `CONTROL` and `SETUP.CFG` for a forward concentration run
- uses `hycs_std`
- defaults to the PDF map time window:
  - `2025-01-18 02:00 UTC` to `2025-01-18 06:00 UTC`
  - equivalent to `2025-01-17 18:00 PST` to `2025-01-17 22:00 PST`
- writes a helper plot script using HYSPLIT `concplot`
- uses PDF contour thresholds from the county map:
  - `1`
  - `4`
  - `40`

## Verified Test Run

Run directory:

- `hysplit/runs/forward_dispersion/pdf_window_t2025011802_to_2025011806_h0010/`

Key outputs:

- `cdump`
- `plume_map.ps`
- `plume_map.pdf`
- `plot_concentration.sh`
- `run.log`

Status:

- forward HYSPLIT run is working
- HYSPLIT `concplot` rendering is working through the compiled binary
- the current plume image is valid but tiny because the run still uses a unit-release source term

## What The County PDF Revealed

From the map page:

- integration window:
  - `1800 PST Jan 17 2025` to `2200 PST Jan 17 2025`
- contour thresholds:
  - `USER-1 > 1.0 ppm`
  - `USER-2 > 4.0 ppm`
  - `USER-3 > 40.0 ppm`

Still unknown:

- real source emission rate
- release duration
- release height
- exact pollutant/unit assumptions
- whether post-scaling was applied

## Current Limitation

The workflow is now operational, but the plume does not yet match the county map because the source term is not calibrated.

This means:

- geometry workflow: working
- map generation: working
- concentration scaling to county legend: not yet solved

## Recommended Next Steps

1. Add source-term tuning options and run sensitivity tests on:
   - emission rate
   - emission duration
   - source height
2. Compare plume direction and extent with the county PDF.
3. Decide whether to keep HYSPLIT native plotting or build a custom Python renderer from `cdump` for a more Leaflet-like map.

## Useful Commands

Run the default forward plume:

```bash
cd ~/Documents/project/moss_landing_fire
./.venv/bin/python scripts/hysplit/run_forward_dispersion.py
```

Rebuild the HYSPLIT plot from an existing completed run:

```bash
cd ~/Documents/project/moss_landing_fire/hysplit/runs/forward_dispersion/pdf_window_t2025011802_to_2025011806_h0010
bash plot_concentration.sh
```

## How To Resume In A New Session

Start the next agent session from:

```bash
cd ~/Documents/project/moss_landing_fire
```

Then tell the agent to read:

- `docs/codex_handoff.md`
- `docs/moss_hysplit_current_handoff.md`

and continue from there.
