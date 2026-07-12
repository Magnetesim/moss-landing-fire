#!/usr/bin/env bash
# Submit combined-versus-separate validation with actual staged HRRR data.

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
VALIDATION_ROOT="${VALIDATION_ROOT:-$MOSS_ROOT/work/combined-validation}"
VALIDATION_NUMPAR="${VALIDATION_NUMPAR:-500}"
VALIDATION_QOS="${VALIDATION_QOS:-regular}"
SETUPS="point|300,120|1,1;area_grid|900,360|9,5"
mkdir -p "$VALIDATION_ROOT"

common=(
    --hrrr-dir "$HRRR_DIR"
    --hysplit-root "$HYSPLIT_ROOT"
    --source-heights-m 10,100
    --release-durations-h 12
    --source-setups "$SETUPS"
    --window-indices 1,4,7,10
    --numpar "$VALIDATION_NUMPAR"
)
combined_manifest="$VALIDATION_ROOT/combined/manifest.csv"
separate_manifest="$VALIDATION_ROOT/separate/manifest.csv"
"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/build_forward_manifest.py" \
    --manifest "$combined_manifest" --runs-root "$VALIDATION_ROOT/combined/rows" \
    --execution-shape combined --run-tag-prefix validate_combined "${common[@]}"
"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/build_forward_manifest.py" \
    --manifest "$separate_manifest" --runs-root "$VALIDATION_ROOT/separate/rows" \
    --execution-shape separate --run-tag-prefix validate_separate "${common[@]}"

combined_job="$(sbatch --parsable --qos="$VALIDATION_QOS" --time=00:25:00 --cpus-per-task=4 \
    --export="ALL,MANIFEST=$combined_manifest,MOSS_JOBS=4" \
    "$MOSS_REPO/nersc/run_forward_packed.slurm")"
separate_job="$(sbatch --parsable --qos="$VALIDATION_QOS" --time=00:25:00 --cpus-per-task=4 \
    --dependency="afterok:$combined_job" \
    --export="ALL,MANIFEST=$separate_manifest,MOSS_JOBS=4" \
    "$MOSS_REPO/nersc/run_forward_packed.slurm")"
comparison_job="$(sbatch --parsable --qos="$VALIDATION_QOS" --time=00:10:00 --dependency="afterok:$separate_job" \
    --export="ALL,COMBINED_MANIFEST=$combined_manifest,SEPARATE_MANIFEST=$separate_manifest,VALIDATION_OUTPUT=$VALIDATION_ROOT/comparison.json" \
    "$MOSS_REPO/nersc/validate_combined.slurm")"
printf 'combined_job=%s\nseparate_job=%s\ncomparison_job=%s\n' "$combined_job" "$separate_job" "$comparison_job"
