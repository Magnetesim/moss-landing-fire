#!/usr/bin/env bash
# Test whether matching the combined run's sampling start removes later-window divergence.

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
ROOT="${CUMULATIVE_VALIDATION_ROOT:-$MOSS_ROOT/work/extended-validation/cumulative500}"
COMBINED_MANIFEST="${COMBINED_MANIFEST:-$MOSS_ROOT/work/extended-validation/n500/combined/manifest.csv}"
COMBINED_JOB="${COMBINED_JOB:-55809917}"
QOS="${CUMULATIVE_VALIDATION_QOS:-regular}"
SETUPS="point|300,120|1,1;area_grid|900,360|9,5"
MANIFEST="$ROOT/manifest.csv"
mkdir -p "$ROOT"

"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/build_forward_manifest.py" \
    --manifest "$MANIFEST" --runs-root "$ROOT/rows" \
    --hrrr-dir "$HRRR_DIR" --hysplit-root "$HYSPLIT_ROOT" \
    --source-heights-m 10 --release-durations-h 12 --source-setups "$SETUPS" \
    --window-indices 1,4,7,10 --execution-shape cumulative \
    --numpar 500 --maxpar 50000 --krand 2 --seed 0 \
    --run-tag-prefix cumulative500

run_job="$(sbatch --parsable --qos="$QOS" --time=00:45:00 --cpus-per-task=8 \
    --export="ALL,MANIFEST=$MANIFEST,MOSS_JOBS=8" \
    "$MOSS_REPO/nersc/run_forward_packed.slurm")"
compare_job="$(sbatch --parsable --qos="$QOS" \
    --dependency="afterok:$COMBINED_JOB:$run_job" \
    --export="ALL,COMBINED_MANIFEST=$COMBINED_MANIFEST,SEPARATE_MANIFEST=$MANIFEST,VALIDATION_OUTPUT=$ROOT/comparison.json" \
    "$MOSS_REPO/nersc/validate_combined.slurm")"

printf 'cumulative=%s\ncomparison=%s\n' "$run_job" "$compare_job"
