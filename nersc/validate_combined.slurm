#!/usr/bin/env bash
#SBATCH --job-name=moss-combined-check
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=00:10:00
#SBATCH --output=moss-combined-check-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
: "${COMBINED_MANIFEST:?Set COMBINED_MANIFEST when submitting}"
: "${SEPARATE_MANIFEST:?Set SEPARATE_MANIFEST when submitting}"
VALIDATION_OUTPUT="${VALIDATION_OUTPUT:-$MOSS_ROOT/work/combined-validation.json}"
"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/compare_combined_to_separate.py" \
    --combined-manifest "$COMBINED_MANIFEST" \
    --separate-manifest "$SEPARATE_MANIFEST" \
    --output-json "$VALIDATION_OUTPUT"
