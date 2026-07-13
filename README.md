# Moss Landing Fire

Research workspace for analyzing the January 2025 Moss Landing battery fire with:

- PurpleAir PM2.5 observations
- HYSPLIT forward dispersion driven by HRRR meteorology
- comparison workflows that score modeled plume scenarios against observed 4-hour PurpleAir enhancement patterns

This is not a polished package. It is a working research repo with reproducible scripts, intermediate datasets, visualization outputs, and a progress report.

## Main Folders

- `moss_landing/` shared Python package: paths, event constants, PurpleAir HTTP helpers, HYSPLIT import glue, kriging helpers
- `scripts/purple_air/` PurpleAir discovery, pulls, cleaning, enhancement windows, kriging, and visualization
- `scripts/hysplit/` forward dispersion, custom `cdump` rendering, sweeps, and scoring
- `data/purple_air/` local PurpleAir datasets and district boundary data
- `figures/visualization/` generated maps, animations, comparison sheets, and galleries
- `docs/` canonical project status, local-data setup, and source references
- `report/` LaTeX progress report

## Environment

- Python `3.12`
- dependencies are defined in [pyproject.toml](pyproject.toml)
- local API secret lives in `purple_air_api.txt`
- HRRR meteorology should live in `hrrr/`

Example setup:

```bash
uv sync
cp purple_air_api.txt.example purple_air_api.txt
```

`uv sync` also installs the repository's `moss_landing` package in editable mode; the scripts import it, so re-run `uv sync` after pulling on an existing clone. Commands below use `uv run`, which works the same on Linux, Windows, and NERSC (replace with `./.venv/bin/python` or `.venv\Scripts\python.exe` if you prefer calling the venv directly).

To download the required HRRR archive blocks for a simulation window:

```bash
uv run python scripts/hysplit/download_hrrr.py \
  --start-utc 2025-01-16T23:00:00Z \
  --end-utc 2025-01-18T06:00:00Z
```

For the exact HRRR source path and file list used by this project, see [docs/local_data.md](docs/local_data.md).

## Quick Start

Rebuild a PurpleAir raw map:

```bash
uv run python scripts/purple_air/tier1_bubble_map.py --html --gif --basemap-style gray
```

Run the default scored HYSPLIT phase-1 sweep:

```bash
uv run python scripts/hysplit/run_phase1_sweep.py --jobs 16 --score
```

The default `combined` execution shape runs each source scenario once and writes successive 4-hour concentration periods for scoring. Use `--execution-shape separate` to reproduce the legacy one-HYSPLIT-execution-per-window workflow for validation.

## Perlmutter / NERSC

The cluster workflow uses one deterministic manifest row per physical HYSPLIT execution, with a unique output root and atomic per-row status file. This avoids shared-run-directory races and makes incomplete campaigns resumable.

After staging the repository, static HYSPLIT bundle, and required HRRR blocks under `$SCRATCH/moss-landing-fire`, bootstrap the Python 3.12 environment once:

```bash
bash nersc/bootstrap_env.sh
```

The current Perlmutter source tree was transferred rather than cloned with Git. To deploy a repository update, synchronize the complete source tree into a new versioned directory, then set `MOSS_REPO` while bootstrapping it. Smoke-test that directory before using it for campaign submissions:

```bash
MOSS_REPO="$SCRATCH/moss-landing-fire/repo/moss-landing-fire-YYYYMMDD" \
  bash nersc/bootstrap_env.sh
```

Keep the HYSPLIT distribution, HRRR input, secrets, and generated runs outside the repository source directory.

Build the default 96-physical-run combined phase-1 manifest and submit a packed CPU-node job:

```bash
source nersc/env.sh
"$MOSS_PYTHON" scripts/hysplit/build_forward_manifest.py \
  --manifest "$MOSS_MANIFEST_DIR/phase1.csv" \
  --runs-root "$MOSS_RUN_ROOT/phase1" \
  --hrrr-dir "$HRRR_DIR" \
  --hysplit-root "$HYSPLIT_ROOT"

MANIFEST="$MOSS_MANIFEST_DIR/phase1.csv" MOSS_JOBS=8 \
  sbatch nersc/run_forward_packed.slurm
```

Use `nersc/run_forward_chunks.slurm` when one node is not enough. Benchmark safe values of `MOSS_JOBS` with representative rows before a full campaign; the score is sensitive to particle count and stochastic variation.

Build the top-scenario comparison gallery:

```bash
uv run python scripts/hysplit/build_phase1_comparison_gallery.py --top-n 4
```

Regenerate the main report images:

```bash
uv run python scripts/report/render_key_figures.py
```

## Current State

The PurpleAir and HYSPLIT pipelines are both working. The current research question is how closely HYSPLIT can reproduce the observed PurpleAir enhancement pattern, and how sensitive that answer is to source assumptions like release height, duration, and source geometry.

For a fuller status snapshot, see [docs/project_status.md](docs/project_status.md).
