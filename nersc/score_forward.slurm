#!/usr/bin/env bash
#SBATCH --job-name=moss-forward-score
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=2
#SBATCH --time=00:30:00
#SBATCH --output=moss-forward-score-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
: "${SCORING_MANIFEST:?Set SCORING_MANIFEST to a completed merged manifest}"
SCORING_OUTPUT_DIR="${SCORING_OUTPUT_DIR:-$(dirname "$SCORING_MANIFEST")/scoring}"

"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/score_against_purpleair.py" \
    --manifest "$SCORING_MANIFEST" \
    --scenario-columns scenario_tag \
    --output-dir "$SCORING_OUTPUT_DIR"
