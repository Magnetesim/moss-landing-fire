#!/usr/bin/env bash
# Submit deterministic-repeat, seed-variation, KRAND, and particle-count diagnostics.

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
ROOT="${EXTENDED_VALIDATION_ROOT:-$MOSS_ROOT/work/extended-validation}"
QOS="${EXTENDED_VALIDATION_QOS:-regular}"
SETUPS="point|300,120|1,1;area_grid|900,360|9,5"
mkdir -p "$ROOT"

build_manifest="$MOSS_REPO/scripts/hysplit/build_forward_manifest.py"
packed="$MOSS_REPO/nersc/run_forward_packed.slurm"

# Exact-repeat test: three independent executions with identical KRAND and SEED.
determinism_manifest="$ROOT/determinism/manifest.csv"
"$MOSS_PYTHON" "$build_manifest" \
    --manifest "$determinism_manifest" --runs-root "$ROOT/determinism/rows" \
    --hrrr-dir "$HRRR_DIR" --hysplit-root "$HYSPLIT_ROOT" \
    --source-heights-m 10 --release-durations-h 12 --source-setups "$SETUPS" \
    --window-indices 10 --execution-shape separate --numpar 500 --krand 2 --seed 0 \
    --replicates 3 --run-tag-prefix deterministic
determinism_job="$(sbatch --parsable --qos="$QOS" --time=00:40:00 --cpus-per-task=6 \
    --export="ALL,MANIFEST=$determinism_manifest,MOSS_JOBS=6" "$packed")"
determinism_check="$(sbatch --parsable --qos="$QOS" --dependency="afterok:$determinism_job" \
    --export="ALL,MANIFEST=$determinism_manifest,REPLICATE_OUTPUT=$ROOT/determinism/comparison.json,GROUP_BY_SEED=1" \
    "$MOSS_REPO/nersc/compare_replicates.slurm")"

# Seed-variation test: same rows, but SEED increments for each replicate.
seed_manifest="$ROOT/seed-variation/manifest.csv"
"$MOSS_PYTHON" "$build_manifest" \
    --manifest "$seed_manifest" --runs-root "$ROOT/seed-variation/rows" \
    --hrrr-dir "$HRRR_DIR" --hysplit-root "$HYSPLIT_ROOT" \
    --source-heights-m 10 --release-durations-h 12 --source-setups "$SETUPS" \
    --window-indices 10 --execution-shape separate --numpar 500 --krand 2 --seed 0 \
    --replicates 3 --vary-seed-by-replicate --run-tag-prefix seed_variation
seed_job="$(sbatch --parsable --qos="$QOS" --time=00:40:00 --cpus-per-task=6 \
    --export="ALL,MANIFEST=$seed_manifest,MOSS_JOBS=6" "$packed")"
seed_check="$(sbatch --parsable --qos="$QOS" --dependency="afterok:$seed_job" \
    --export="ALL,MANIFEST=$seed_manifest,REPLICATE_OUTPUT=$ROOT/seed-variation/comparison.json,GROUP_BY_SEED=0" \
    "$MOSS_REPO/nersc/compare_replicates.slurm")"

labels=(krand3 n500 n2000 n10000)
counts=(500 500 2000 10000)
krands=(3 2 2 2)
limits=(00:45:00 00:45:00 03:00:00 12:00:00)
pair_jobs=()
for index in "${!labels[@]}"; do
    label="${labels[$index]}"
    count="${counts[$index]}"
    krand="${krands[$index]}"
    limit="${limits[$index]}"
    case_root="$ROOT/$label"
    combined_manifest="$case_root/combined/manifest.csv"
    separate_manifest="$case_root/separate/manifest.csv"
    common=(
        --hrrr-dir "$HRRR_DIR" --hysplit-root "$HYSPLIT_ROOT"
        --source-heights-m 10 --release-durations-h 12 --source-setups "$SETUPS"
        --window-indices 1,4,7,10 --numpar "$count" --maxpar 50000 --krand "$krand" --seed 0
    )
    "$MOSS_PYTHON" "$build_manifest" \
        --manifest "$combined_manifest" --runs-root "$case_root/combined/rows" \
        --execution-shape combined --run-tag-prefix "${label}_combined" "${common[@]}"
    "$MOSS_PYTHON" "$build_manifest" \
        --manifest "$separate_manifest" --runs-root "$case_root/separate/rows" \
        --execution-shape separate --run-tag-prefix "${label}_separate" "${common[@]}"
    combined_job="$(sbatch --parsable --qos="$QOS" --time="$limit" --cpus-per-task=2 \
        --export="ALL,MANIFEST=$combined_manifest,MOSS_JOBS=2" "$packed")"
    separate_job="$(sbatch --parsable --qos="$QOS" --time="$limit" --cpus-per-task=8 \
        --export="ALL,MANIFEST=$separate_manifest,MOSS_JOBS=8" "$packed")"
    compare_job="$(sbatch --parsable --qos="$QOS" --dependency="afterok:$combined_job:$separate_job" \
        --export="ALL,COMBINED_MANIFEST=$combined_manifest,SEPARATE_MANIFEST=$separate_manifest,VALIDATION_OUTPUT=$case_root/comparison.json" \
        "$MOSS_REPO/nersc/validate_combined.slurm")"
    pair_jobs+=("$label:$combined_job:$separate_job:$compare_job")
done

printf 'determinism=%s:%s\nseed_variation=%s:%s\n' \
    "$determinism_job" "$determinism_check" "$seed_job" "$seed_check"
printf 'pair=%s\n' "${pair_jobs[@]}"
