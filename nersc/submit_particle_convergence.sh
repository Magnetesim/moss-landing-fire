#!/usr/bin/env bash
# Submit a compact combined-only particle-count and ranking-stability campaign.

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
ROOT="${CONVERGENCE_ROOT:-$MOSS_ROOT/work/particle-convergence}"
QOS="${CONVERGENCE_QOS:-regular}"
SETUPS="point|300,120|1,1;area_grid|900,360|9,5"
mkdir -p "$ROOT"

run_jobs=()
score_jobs=()
for count in 500 2000 10000; do
    case_root="$ROOT/n${count}"
    manifest="$case_root/manifest.csv"
    "$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/build_forward_manifest.py" \
        --manifest "$manifest" --runs-root "$case_root/rows" \
        --hrrr-dir "$HRRR_DIR" --hysplit-root "$HYSPLIT_ROOT" \
        --source-heights-m 10,25 --release-durations-h 12,24 \
        --source-setups "$SETUPS" --window-indices 1,4,7,10 \
        --execution-shape combined --numpar "$count" --maxpar 50000 \
        --krand 2 --seed 0 --run-tag-prefix "convergence_n${count}"
    run_job="$(sbatch --parsable --qos="$QOS" --time=01:00:00 --cpus-per-task=16 \
        --export="ALL,MANIFEST=$manifest,MOSS_JOBS=16" \
        "$MOSS_REPO/nersc/run_forward_packed.slurm")"
    score_job="$(sbatch --parsable --qos="$QOS" --dependency="afterok:$run_job" \
        --export="ALL,SCORING_MANIFEST=$case_root/manifest_merged.csv,SCORING_OUTPUT_DIR=$case_root/scoring" \
        "$MOSS_REPO/nersc/score_forward.slurm")"
    run_jobs+=("$count:$run_job")
    score_jobs+=("$count:$score_job")
done

# Build the dependency explicitly because each array item also contains its particle-count label.
dependencies=""
for item in "${score_jobs[@]}"; do
    job_id="${item##*:}"
    dependencies="${dependencies:+$dependencies:}$job_id"
done
summary_job="$(sbatch --parsable --qos="$QOS" --dependency="afterok:$dependencies" \
    --export="ALL,CONVERGENCE_ROOT=$ROOT" \
    "$MOSS_REPO/nersc/summarize_particle_convergence.slurm")"

printf 'run=%s\n' "${run_jobs[@]}"
printf 'score=%s\n' "${score_jobs[@]}"
printf 'summary=%s\n' "$summary_job"
