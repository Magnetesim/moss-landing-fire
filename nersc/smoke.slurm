#!/usr/bin/env bash
#SBATCH --job-name=moss-smoke
#SBATCH --account=m4007
#SBATCH --qos=debug
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=00:05:00
#SBATCH --output=moss-smoke-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"

hostname
date -u
echo "HYSPLIT_ROOT=$HYSPLIT_ROOT"
echo "HRRR_DIR=$HRRR_DIR"
test -x "$HYSPLIT_ROOT/exec/hycs_std"
test -d "$HYSPLIT_ROOT/bdyfiles"
test -d "$HRRR_DIR"
"$MOSS_PYTHON" --version
"$HYSPLIT_ROOT/exec/hycs_std" -h 2>&1 | head -n 2
