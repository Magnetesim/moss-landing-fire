#!/usr/bin/env bash
#SBATCH --job-name=moss-particle-summary
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=1
#SBATCH --time=00:15:00
#SBATCH --output=moss-particle-summary-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
ROOT="${CONVERGENCE_ROOT:-$MOSS_ROOT/work/particle-convergence}"
args=()
for count in 500 2000 10000; do
    score_root="$ROOT/n${count}/scoring/manifest_merged"
    args+=(--scores "$count=${score_root}_scenario_scores.csv")
    args+=(--per-run "$count=${score_root}_per_run_scores.csv")
done

"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/summarize_particle_convergence.py" \
    "${args[@]}" --top-k 3 --output-dir "$ROOT/summary"
