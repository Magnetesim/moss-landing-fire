# Project Status

## Project

Moss Landing battery fire analysis workspace combining:

- PurpleAir PM2.5 acquisition, cleaning, enhancement windows, and visualization
- HYSPLIT forward dispersion driven by HRRR meteorology
- HYSPLIT/PurpleAir comparison and scoring workflows
- report-writing support for the independent-study progress update

Current Windows project root:

- `C:\Users\myles\Documents\Codex\2026-07-10\c\moss-landing-fire`

Status date:

- `2026-07-13`

## Current Summary

The project now has two working analysis tracks:

1. PurpleAir observation processing
2. HYSPLIT forward-dispersion modeling

Those tracks are connected by a comparison/scoring workflow that ranks HYSPLIT source-term scenarios against PurpleAir 4-hour enhancement windows.

The HYSPLIT runtime, HRRR inputs, project environment, packed Slurm workflow, and dependent scoring pipeline are staged and validated on NERSC Perlmutter. Combined multi-period execution has been validated when compared with runs that share the same concentration-grid activation time.

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
- combined multi-period phase-1 sweeps with one HYSPLIT execution per source scenario
- custom `cdump` rendering to PNG/CSV/JSON
- comparison-mode rendering against PurpleAir
- timestamp-aware sweep scoring against PurpleAir windows
- top-scenario gallery generation
- backward receptor trajectories with per-run isolation, meteorology coverage checks, and nonempty-trajectory validation
- deterministic cluster manifests, resumable row runners, dependent scoring, and convergence summaries on Perlmutter

### Reporting / Organization

- LaTeX progress report exists
- visualization outputs are organized by product family
- phase-1 comparison gallery exists locally
- remote PC workflow was proven for larger sweeps
- NERSC login and SSH key-based access have been verified
- NERSC project/account for Slurm submissions has been identified as `m4007`
- GitHub repository is initialized and pushed to `git@github.com:Magnetesim/moss-landing-fire.git`
- generated figures, HYSPLIT binaries/runs, HRRR files, and local secrets are excluded from Git

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
- the 96-row combined phase-1 campaign has not yet been submitted
- rankings across point and area sources are not numerically converged through `numpar=10000`; sensitive cases should be extended to 20,000 and 50,000 particles
- broad-area screening appears substantially more stable than point-source ranking, but the production particle strategy still needs to be selected
- the current relative-quantile score cannot identify or calibrate emission magnitude
- native Windows support has not been implemented yet

## Important Inputs

### Secrets / Local-only

- `purple_air_api.txt`

This file should stay out of Git.

### Git-tracked / portable

- code and scripts
- cleaned PurpleAir CSVs
- selected public/reference documents
- LaTeX report source
- Python dependency metadata
- setup notes for local-only HYSPLIT and HRRR requirements

### Local-only / regenerated

- `hrrr/`
- `hysplit/install/`
- `hysplit/runs/`
- `figures/`
- `report/images/`
- `report/moss_landing_progress_report.pdf`

### NERSC / Perlmutter Runtime Inputs

The active NERSC scratch workspace is:

- `/pscratch/sd/m/mthallet/moss-landing-fire`

The repository, Python 3.12 environment, static HYSPLIT 5.4.2 distribution, and nine required HRRR blocks are staged there and have completed real CPU-node runs.

Perlmutter scratch is the correct place for active HRRR inputs and HYSPLIT run products, but it is not permanent storage. Files that have not been accessed within the NERSC purge window can be removed. Reproducibility-critical manifests, merged scores, logs needed for provenance, and selected final outputs should be copied to project CFS, HPSS, or another durable location after each campaign. Do not attempt to defeat the scratch purge policy by artificially touching files.

Runtime assets staged on NERSC include:

- HYSPLIT install tree:
  - `hysplit/install/hysplit.v5.4.2_x86_64/exec/`
  - `hysplit/install/hysplit.v5.4.2_x86_64/bdyfiles/`
  - `hysplit/install/hysplit.v5.4.2_x86_64/graphics/`
- HRRR ARL meteorology files under `hrrr/`
- generated run/output directories under `hysplit/runs/`

The HYSPLIT executable bundle is small enough to transfer from the laptop. HRRR files are large enough that transfer method matters; preferred options are:

1. Globus to the `NERSC DTN` endpoint for robust large transfers into Perlmutter scratch.
2. `rsync -avP` to `dtn.nersc.gov` if Globus is more friction than it is worth.
3. NOAA ARL FTP redownload only for missing or corrupt HRRR files.

Do not push HYSPLIT binaries, HRRR files, or generated run products into Git.

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

These are local-only runtime inputs/outputs. The repository only includes `hysplit/README.md`; HYSPLIT binaries must be downloaded separately through the NOAA HYSPLIT distribution/registration process.

The exact HRRR archive source and file list are documented in `docs/local_data.md`.

### Reference Docs

- `docs/MLVPP-Fire-EAP_OP3-20250118.pdf`
- `docs/7.-MLVPP-Fire-EAP_OP2-20250117.pdf`
- `docs/item11_stfrpt.pdf`

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
- current "best" scenarios are still only moderate matches

### Report

- `report/moss_landing_progress_report.tex`
- `report/moss_landing_progress_report.pdf`

## PurpleAir Notes

- the current workflow uses the Monterey Bay Unified APCD district boundary
- the original discovery bounding box was longitude -122.10 to -121.50 and latitude 36.55 to 37.05
- discovery found 168 outdoor sensors; 132 returned history for Jan. 14-25, 2025
- the hourly pull contains 33,935 rows spanning 2025-01-14 00:00 UTC through 2025-01-24 23:00 UTC, including `pm2.5_atm`, `pm2.5_cf_1`, and humidity
- `pm2.5_atm` is the ambient/smoke-oriented field used by the project; timestamps remain UTC internally and are converted to Pacific time for display
- event maxima around 1,678-2,183 micrograms per cubic meter may reflect sensor saturation and should not be interpreted quantitatively without further QA
- one recurrent suspect sensor has been treated specially in kriging work:
  - `72253`
- the `no72253` outputs are often the cleaner visual products
- interpolation outside well-supported sensor regions should not be over-interpreted
- raw PM2.5 and enhancement are both available, but enhancement is the more useful comparison field for the fire event
- AQI-category colors are intentional because extreme event values make a continuous scale unreadable; marker-size clipping is display-only and does not change source data
- interactive HTML is the exploratory product and GIF is the communication product; GIF basemaps remain optional
- the map fire origin is 36.8044 N, -121.7883 W. The Jan. 16, 2025 5:35 PM Pacific fire-start time is a project/narrative assumption that needs an authoritative citation before formal use
- the animated growing ring is symbolic and is not a modeled fire, blast, or plume radius

## HYSPLIT Notes

- area-source approximations behave more plausibly than the early point-source runs
- lower release heights and broader area footprints tended to rank better in the phase-1 sweep
- 4-hour windows are the right comparison unit for the current study
- custom Python rendering is preferred over native HYSPLIT PDF products for interpretation
- current HYSPLIT automation is Linux/Unix-oriented and assumes the local NOAA binary bundle under `hysplit/install/hysplit.v5.4.2_x86_64/`
- receptor-event extraction uses per-sensor pre-fire median/MAD thresholds, groups episodes, and records onset, peak, end, duration, and intensity; the historical extraction produced 804 events with 118 marked primary
- the first real 24-hour backward batch completed 424 trajectories across 10, 50, 200, and 500 m, covered 106 receptor events, skipped 12 for coverage, and had 48 missing-meteorology configurations
- historical event coverage was 106/118 for 24-hour, 61/118 for 36-hour, and 22/118 for 48-hour trajectories
- this HYSPLIT build is driven with one meteorology entry per `N 1` block followed by explicit directory/filename pairs; malformed CONTROL experiments previously overwrote an HRRR input, so meteorology inputs should remain checksum-verified and read-only where practical
- backward runs create isolated directories, link `bdyfiles`, and require actual `tdump` trajectory rows before reporting completion; exit code or file existence alone is insufficient because a missing `ASCDATA.CFG` can yield a header-only output
- the county EAP reference map integrates 2025-01-18 02:00-06:00 UTC and shows 1, 4, and 40 ppm contours, but its emission rate, release duration/height, pollutant/unit assumptions, and any post-scaling are unknown; matching its magnitude is not physical validation

## NERSC / Perlmutter Notes

NERSC access, staging, smoke testing, packed execution, scoring, and convergence analysis are working.

Verified account/access facts:

- NERSC username: `mthallet`
- Perlmutter SSH target: `perlmutter.nersc.gov`
- Slurm project/account: `m4007`
- Home directory: `/global/homes/m/mthallet`
- Scratch directory: `/pscratch/sd/m/mthallet`
- CFS root: `/global/cfs/cdirs`
- SSH key workflow: NERSC `sshproxy`
- Codex/Windows SSH alias `perlmutter` works when the sandbox is allowed to read the Windows SSH config and key

The short-lived `sshproxy` certificate had expired during a connectivity check on `2026-07-10`, which produced a public-key authentication failure. It was refreshed and passwordless access was verified again on `2026-07-11`; the remote account reports membership in `m4007` and `$SCRATCH=/pscratch/sd/m/mthallet`.

The supplied static `hycs_std` from `hysplit.v5.4.2_x86_64.tar.gz` was copied to:

```text
/pscratch/sd/m/mthallet/moss-landing-fire/work/binary-smoke/hycs_std
```

Both WSL and Perlmutter identify it as an x86-64 statically linked Linux executable with no dynamic-library dependencies. A real model execution still requires the HYSPLIT boundary files and HRRR meteorology.

The `sshproxy` Windows client was installed and used successfully. It creates short-lived keys under:

```text
C:\Users\myles\.ssh\nersc
C:\Users\myles\.ssh\nersc.pub
C:\Users\myles\.ssh\nersc-cert.pub
```

The Windows SSH config alias can use:

```sshconfig
Host perlmutter
    HostName perlmutter.nersc.gov
    User mthallet
    IdentityFile C:\Users\myles\.ssh\nersc
    IdentitiesOnly yes
    ForwardAgent yes
```

Verified from Codex:

```bash
ssh perlmutter hostname
```

returned a Perlmutter login node such as `login08` or `login32`.

### NERSC Python Environment

The default bare `python` on Perlmutter was Python 2.7.18.

After:

```bash
module load python
```

Perlmutter loaded the NERSC Python module:

```text
/global/common/software/nersc/pe/conda-envs/26.1.0/python-3.13/nersc-python/bin/python
Python 3.13.11
```

This is good for basic smoke tests but does not match this project exactly because `pyproject.toml` currently requires:

```text
>=3.12,<3.13
```

Recommended NERSC environment approach:

1. use Conda to create a Python 3.12 interpreter environment on scratch
2. install/use `uv` inside that environment for project dependency syncing

Example:

```bash
module load conda
conda create -p "$SCRATCH/conda-envs/moss-py312" python=3.12 -y
conda activate "$SCRATCH/conda-envs/moss-py312"
python --version
pip install uv
```

Then from the staged project root:

```bash
uv sync --frozen
```

This keeps the local/laptop workflow aligned with `uv` while using Conda only for the interpreter version that NERSC's default Python module does not provide.

### NERSC Slurm Direction

The current HYSPLIT scripts can run local multi-case batches with `--jobs`, but that is not ideal for Slurm.

The earlier idea of submitting one Slurm array task per HYSPLIT run should not be the default. These are expected to be small, independent, serial jobs. On Perlmutter, reserving a CPU node for each run would waste most of the node, while submitting hundreds or thousands of tiny scheduler jobs can reduce throughput. NERSC specifically recommends considering GNU Parallel for this workload shape.

The preferred architecture is therefore:

1. build a deterministic manifest with one row per logical HYSPLIT run
2. benchmark the wall time, memory, CPU use, and I/O of representative runs
3. choose a safe number of concurrent HYSPLIT processes per CPU node
4. pack many manifest rows into each node allocation, initially with GNU Parallel
5. use a Slurm array only when the campaign needs multiple node-sized chunks
6. write one unique run directory and one atomic result/status file per row
7. merge and validate the per-row results after all compute jobs complete
8. run scoring/postprocessing as a dependent Slurm job

The manifest remains the unit of reproducibility and restart, but it does not have to be the unit of Slurm scheduling.

This is especially natural for backward receptor trajectories because each run is:

```text
receptor event x duration x starting height
```

Forward dispersion scenario sweeps can use the same shape:

```text
source scenario x sample window
```

However, the current phase-1 workflow repeats the same scenario from ignition for four separate sample windows. The default matrix contains:

```text
6 release heights x 4 durations x 4 source setups x 4 sample windows = 384 executions
```

For one scenario, the four selected windows require runs ending at approximately 8, 20, 32, and 44 hours after ignition, or 104 total simulated hours. If HYSPLIT can write successive 4-hour concentration periods from one simulation, one 44-hour run per scenario could reduce the matrix to 96 executions and avoid about 58% of the repeated simulated time.

Combined execution and timestamp-aware selection are now implemented. `run_phase1_sweep.py` defaults to `--execution-shape combined`, while `--execution-shape separate` preserves the legacy behavior for validation. `score_against_purpleair.py` expands a combined physical-run manifest row into the requested logical PurpleAir windows and selects each concentration period by its exact start/stop timestamps. The phase-1 gallery uses the same timestamp fields rather than defaulting to the last `cdump` period.

The code path has been tested with the actual Moss Landing HRRR inputs. Combined output is bit-for-bit identical to cumulative separate runs that activate sampling at the same initial time. Legacy late-start separate runs are a different HYSPLIT integration configuration and should not be used as the equivalence reference.

### Cluster-safe Runner Implementation

The cluster refactor now provides three explicit Python entry points:

- `scripts/hysplit/build_forward_manifest.py`
- `scripts/hysplit/run_forward_manifest_row.py`
- `scripts/hysplit/merge_forward_results.py`

Each manifest row should contain the full configuration needed to reproduce the run, including timestamps, source parameters, concentration grid, particle settings, HYSPLIT and HRRR paths, output path, and a stable configuration hash. A row runner should not depend on mutable defaults from another script.

Each row runner should:

- write only inside its unique run directory
- write status/result metadata to a temporary file and atomically rename it on completion
- verify that `cdump` exists and is nonempty before reporting success
- record elapsed time, return code, executable version/path, and relevant Slurm identifiers
- skip an already-valid matching result unless `--force` is supplied
- preserve logs for failed rows so the campaign can be resumed selectively

The row runner gives each configuration hash its own `row_output_root`. This isolates the legacy `bdyfiles` and `latest` convenience pointers inside one physical run, so they cannot race with another row. It also means an interrupted row can be resumed without mutating another row's files.

The hard-coded HYSPLIT Python-module path in the scoring and rendering scripts should also become a command-line option or an environment-derived path such as `HYSPLIT_ROOT`.

Implemented cluster-helper directory:

```text
nersc/
```

Suggested files:

- `nersc/env.sh`
- `nersc/smoke.slurm`
- `nersc/run_forward_packed.slurm`
- `nersc/run_forward_chunks.slurm`
- `nersc/merge_forward.slurm`
- `nersc/bootstrap_env.sh`

Initial Slurm smoke-test shape:

```bash
#!/bin/bash
#SBATCH --job-name=moss-smoke
#SBATCH --account=m4007
#SBATCH --qos=debug
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=00:05:00
#SBATCH --output=moss-smoke-%j.out

set -euxo pipefail

module load python

hostname
date
pwd
echo "USER=$USER"
echo "SCRATCH=$SCRATCH"
echo "CFS=$CFS"
which python
python --version
```

Initial packed smoke-test shape once manifest runners exist:

```bash
#SBATCH --nodes=1
#SBATCH --constraint=cpu
#SBATCH --qos=debug
#SBATCH --time=00:30:00

parallel --jobs 4 --joblog hysplit/runs/smoke/parallel-joblog.tsv \
  "python scripts/hysplit/run_forward_manifest_row.py \
    --manifest hysplit/runs/smoke/manifest.csv --row-index {}" ::: 0 1 2 3
```

The first benchmark should compare 1, 4, 8, 16, and possibly 32 concurrent processes. Production packing should be chosen from measured memory and throughput rather than the node's core count alone. If arrays are later used for multiple packed chunks, the array size must be generated from the manifest row count and chunk size, not hard-coded.

## Windows Support Notes

Native Windows support is possible but not implemented yet.

Windows should already be reasonable for:

- Git clone/push workflow
- Python-based PurpleAir processing
- kriging and visualization scripts, subject to Python package installation
- LaTeX report editing/building if TeX Live is installed

The main unresolved Windows issue is HYSPLIT execution. NOAA does provide Windows binaries, but the current scripts still assume:

- Unix-like paths
- Linux-style HYSPLIT install layout
- executable names without `.exe`
- symlink support for `bdyfiles`
- Unix helper tools for some workflows

Future Windows support should test a minimal forward-dispersion dry run first, then add platform handling for executable names, install paths, symlink/copy behavior, and generated helper scripts.

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

The NERSC runtime is now staged at `/pscratch/sd/m/mthallet/moss-landing-fire`:

- `hrrr/` contains the nine required Jan. 16–18 HRRR ARL blocks; Globus reported checksum-verified success on 2026-07-11
- `hysplit/install/hysplit.v5.4.2_x86_64/` contains the static HYSPLIT 5.4.2 distribution and `hycs_std` passed an initialization check
- `repo/moss-landing-fire/` contains the project code and PurpleAir inputs
- `conda/moss-py312/` plus the repository `.venv/` provide Python 3.12 and the locked project dependencies

The replacement smoke job completed successfully: Slurm job `55803610` exited `0`, and the runner recorded a nonempty `cdump` (25,044 bytes) on a Perlmutter CPU node.

The packing benchmark also completed successfully at every tested shape. The 1-, 4-, 8-, and 16-process jobs (`55805200`, `55805207`, `55805208`, and `55805209`) finished in 14:45, 14:37, 14:46, and 14:41 respectively. Peak node memory rose from 13.7 GB at one process to 21.5 GB at 16 processes. All 29 physical rows completed without failure. At `numpar=500`, 16 concurrent processes are therefore a safe initial one-node packing shape and produced about 9.2 times the serial row throughput in this benchmark.

The first actual-HRRR combined-versus-separate comparison (`55804730`, `55804732`, comparator `55804734`) found that the first requested window was bit-for-bit identical, but later windows were not. Later-window correlations ranged from approximately -0.03 to 0.86 and normalized total variation ranged from 0.245 to 0.929. Combined execution must not yet be used as a transparent replacement for the separate-window calculation.

The leading explanation is a HYSPLIT configuration effect: a separate late-window run activates its concentration sampling grid only at that late window, while the combined run keeps a grid active from the first selected window onward. HYSPLIT documents that inactive grids are removed from time-step computations, so different grid activation histories can alter the particle calculation. Explicit `KRAND` and `SEED` controls, replicate-aware manifests, and a cumulative execution shape have been added to test this explanation.

The following extended validation jobs were submitted on 2026-07-11:

- identical-seed determinism: run `55809910`, comparison `55809911`
- varying-seed sensitivity: run `55809912`, comparison `55809913`
- no-turbulence `KRAND=3` combined/separate pair: `55809914`, `55809915`, comparison `55809916`
- explicit `KRAND=2`, `numpar=500`: `55809917`, `55809918`, comparison `55809919`
- explicit `KRAND=2`, `numpar=2000`: `55809920`, `55809921`, comparison `55809922`
- explicit `KRAND=2`, `numpar=10000`: `55809923`, `55809925`, comparison `55809926`
- cumulative aligned-sampling-start test: run `55809979`, comparison `55809980`

The cumulative test is decisive for the current hypothesis: each target window is generated by a separate HYSPLIT run that begins concentration sampling at the same time as the combined run, but stops at the target window. Agreement with the combined output would show that sampling-grid history, rather than random particle noise alone, caused the earlier divergence.

All extended-validation compute jobs completed successfully. The results confirm the sampling-grid-history explanation:

- three identical executions for both source geometries were binary-identical
- changing `SEED` from 0 to 1 or 2 under the tested `KRAND=2` configuration also produced binary-identical `cdump` files
- `KRAND=3` still diverged between combined and legacy late-start separate runs after the first window, so turbulent random motion was not the cause
- increasing `numpar` from 500 through 2,000 to 10,000 improved some comparisons but did not make the legacy late-start runs equivalent to the combined run
- all eight cumulative aligned-start comparisons were exact: correlation 1.0 (within floating-point display), normalized total variation 0, relative L1 error 0, concentration-sum ratio 1, and maximum absolute difference 0

The original cumulative comparator job `55809980` failed because it treated the cumulative sampling envelope as a single output period. This was an analyzer bookkeeping bug, not a HYSPLIT failure. `compare_combined_to_separate.py` now derives the target four-hour period from the logical window index; a regression test covers the cumulative case. Replacement debug-QOS analyzer `55816728` completed successfully.

The combined multi-period optimization can therefore be used for the production sweep, provided all compared scenarios use the same sampling start and interval. It should not be expected to reproduce a legacy run whose concentration grid begins only at a later target window; that is a physically different HYSPLIT integration configuration, not merely a different output request.

A combined-only particle-convergence and ranking-stability campaign was submitted on 2026-07-12. It contains eight representative scenarios formed from heights 10 and 25 m, release durations 12 and 24 hours, and point versus 900 x 360 m area sources. Each scenario is run at `numpar=500`, 2,000, and 10,000 with the same four concentration windows, for 24 physical HYSPLIT runs and 96 logical scored windows.

- 500-particle compute/scoring: `55817145` / `55817146`
- 2,000-particle compute/scoring: `55817148` / `55817149`
- 10,000-particle compute/scoring: `55817150` / `55817152`
- dependent convergence summary: `55817153`

The summary reports pairwise Spearman and Kendall rank agreement, top-three overlap, maximum score changes, per-scenario rank ranges, and per-window score ranges. Outputs will be written beneath `/pscratch/sd/m/mthallet/moss-landing-fire/work/particle-convergence/summary`.

The NERSC scoring path was hardened before submission: the scorer now recognizes combined `logical_window_indices`, normalizes `row_status` and `row_run_dir` from merged cluster manifests, and includes release duration in its default scenario grouping. The convergence jobs explicitly group by `scenario_tag` to prevent accidental merging of distinct source configurations.

The particle-convergence campaign completed successfully. All seven Slurm jobs exited 0; each eight-row packed HYSPLIT campaign took approximately 14.5 minutes and each scoring job took less than 25 seconds.

The ranking was stable between 500 and 2,000 particles but not between either lower setting and 10,000:

- 500 versus 2,000: Spearman 0.929, Kendall 0.857, all three top scenarios retained
- 500 versus 10,000: Spearman 0.405, Kendall 0.286, two of three top scenarios retained
- 2,000 versus 10,000: Spearman 0.405, Kendall 0.286, two of three top scenarios retained
- maximum mean-score range across particle settings: 0.181
- maximum rank movement: five positions

Broad-area sources were substantially more stable than point sources. The 10 m / 12 h and 25 m / 12 h area cases changed mean score by only 0.021 and 0.030 respectively and remained in the top three. Both 24-hour area cases produced binary-identical `cdump` files at all three particle settings. In contrast, the 25 m / 12 h point case moved from ranks 7 and 8 at the lower settings to rank 3 at 10,000, with a mean-score range of 0.181. Point-source window 7 was the most sensitive; the largest per-window score range was 0.397.

The practical conclusion is that 500-particle broad-area screening may be adequate for cheaply locating promising regions, but the complete ranking is not numerically converged. Before interpreting point-versus-area ordering or launching a final sweep at one particle setting, extend the convergence test above 10,000 particles (for example 20,000 and 50,000) with emphasis on the sensitive point scenarios. The existing 50,000 `maxpar` setting can accommodate those tests, and the measured node wall times suggest the extension is affordable.

## Recommended Next Steps

1. Extend the particle-convergence test to 20,000 and 50,000 particles:
   - prioritize the sensitive point-source cases
   - retain representative broad-area cases as stable controls
   - compare score/rank changes against the existing 10,000-particle results
2. Select a two-tier production strategy from those results:
   - use a cheaper particle count for coarse broad-area screening if stability holds
   - rerun finalists and sensitive point sources at the converged higher count
3. Submit the 96-row combined phase-1 campaign with the validated packed runner and dependent scoring jobs.
4. Run a coarse-to-fine source-term sweep over:
   - footprint size
   - release duration
   - temporal emission profile
   - source rotation
   - retain a diverse set of good scenarios, then refine around them
5. Test ranking robustness against analysis choices:
   - sensor exclusions and blacklist choices
   - kriging distance mask and variogram settings
   - PurpleAir and HYSPLIT class thresholds
   - composite-score weights
6. Improve PurpleAir QA:
   - reusable blacklist file
   - stronger outlier logic
   - investigate possible saturation during extreme event concentrations
7. Add an attribution layer for backward trajectories using minimum distance to Moss Landing, timing, and altitude.
8. Add wind-vector context and CARB regulatory-monitor cross-validation if they materially improve interpretation.
9. Keep building side-by-side visual comparison products for report and presentation use.

### Scientific Interpretation of Large Sweeps

The current score is primarily a plume-shape and timing score. HYSPLIT concentrations are converted to relative classes using quantiles computed separately for each run. Multiplying a run's emission rate therefore generally does not change its relative class pattern, so emission magnitude is not identifiable from this score.

The analysis should be described and implemented as two stages:

1. fit plume transport, timing, and spatial shape using the current relative metrics
2. calibrate source strength separately using an explicit emissions model and absolute concentration targets

A wide sweep should not be interpreted until numerical convergence and ranking robustness have been assessed. Otherwise, small score differences may reflect particle noise, sensor choices, interpolation assumptions, or arbitrary metric weights rather than meaningful source physics.

### NERSC References for Implementation

- Perlmutter scratch usage and purge behavior: <https://docs.nersc.gov/filesystems/perlmutter-scratch/>
- Slurm examples, arrays, and job dependencies: <https://docs.nersc.gov/jobs/examples/>
- GNU Parallel workflow guidance: <https://docs.nersc.gov/jobs/workflow/gnuparallel/>
- Python environments on Perlmutter: <https://docs.nersc.gov/development/languages/python/using-python-perlmutter/>
- Globus transfers and the NERSC DTN endpoint: <https://docs.nersc.gov/services/globus/>

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

What it does not yet support is a final, physically calibrated plume reconstruction. The immediate technical question is particle-count convergence for sensitive point sources; the immediate scientific question is whether the remaining model/observation mismatch can be reduced without overfitting uncertain source assumptions.

## Codebase Review Status (2026-07-13)

The shared-package refactor has been reviewed and retained. The repository now installs an editable `moss_landing` package containing paths, event constants, PurpleAir HTTP helpers, HYSPLIT import glue, filesystem helpers, and common kriging utilities. The refactor preserves the existing kriging result for the checked project window and removes a substantial amount of script-level duplication.

Review cleanup completed after the refactor:

- HYSPLIT analysis commands import NOAA's registered `hysplitdata` module only when a cdump is actually read, so `--help` works without a local HYSPLIT install
- direct tests now cover the shared path, filesystem, HYSPLIT-import, PurpleAir HTTP, and kriging helpers
- subprocess regression tests cover the four HYSPLIT analysis CLIs that previously failed during argument-only use
- README paths and commands are platform-neutral
- PurpleAir requests have explicit timeouts, status checking, retry/backoff, and lazy API-key loading
- Windows systems without symlink privileges fall back to copying convenience outputs

The extraction is intentionally pragmatic rather than total. Some scientific workflows still contain specialized kriging and data-selection logic. Consolidate those only alongside representative-output tests; forcing every variant through one abstraction would make scientific behavior harder to audit.

### Deploying the Refactor to NERSC

The currently staged Perlmutter source directory is a transferred working tree, not a Git clone. Do **not** run `git pull` there. Its pre-refactor scripts and environment remain usable until an explicit source refresh.

For the next deployment:

1. transfer or synchronize the complete repository source into a new versioned directory under `$SCRATCH/moss-landing-fire/repo/`
2. keep `hysplit/`, `hrrr/`, run products, and secrets outside the Git repository
3. bootstrap against the new source with `MOSS_REPO=/path/to/new/source bash nersc/bootstrap_env.sh`; this runs `uv sync --frozen --no-managed-python`
4. run CLI, manifest, and one-row HYSPLIT smoke tests against that versioned source
5. only then point campaign submissions at the new `MOSS_REPO`

A local Git clone can instead be updated normally and followed by `uv sync --frozen`.

### Open Engineering Work

These items remain useful, but none blocks the existing staged NERSC workflow:

- decide and document whether the default HYSPLIT release time should remain `2025-01-16T23:00:00Z` or align with the observation-side fire start at `2025-01-17T01:35:00Z`
- replace the Unix-only `lftp` HRRR downloader dependency with a portable Python transport
- add pytest/ruff configuration and GitHub Actions once the desired CI policy is chosen
- add representative-output tests before further consolidating scientific transformations
- move a growing observation archive to Git LFS or a reproducible external-data workflow if Git history becomes unwieldy
- replace repeated sensor exclusions with a versioned sensor-quality/blacklist file
- add executable-name handling before attempting native Windows HYSPLIT runs
