#!/usr/bin/env bash
#SBATCH --job-name=moss-repeat-check
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=00:15:00
#SBATCH --output=moss-repeat-check-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
: "${MANIFEST:?Set MANIFEST when submitting}"
: "${REPLICATE_OUTPUT:?Set REPLICATE_OUTPUT when submitting}"
extra=()
if [[ "${GROUP_BY_SEED:-0}" == "1" ]]; then extra+=(--group-by-seed); fi
"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/compare_manifest_replicates.py" \
    --manifest "$MANIFEST" \
    --output-json "$REPLICATE_OUTPUT" \
    "${extra[@]}"
