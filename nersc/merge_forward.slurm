#!/usr/bin/env bash
# Submit this after all packed/chunk tasks are successful, optionally with --dependency=afterok.
#SBATCH --job-name=moss-forward-merge
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=00:15:00
#SBATCH --output=moss-forward-merge-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
MANIFEST="${MANIFEST:-$MOSS_MANIFEST_DIR/phase1.csv}"
"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/merge_forward_results.py" --manifest "$MANIFEST"
