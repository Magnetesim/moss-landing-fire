#!/usr/bin/env bash
# Run once on a Perlmutter login node after staging the repository.

set -euo pipefail

: "${SCRATCH:?Run this on NERSC with SCRATCH defined.}"
MOSS_ROOT="${MOSS_ROOT:-$SCRATCH/moss-landing-fire}"
MOSS_REPO="${MOSS_REPO:-$MOSS_ROOT/repo/moss-landing-fire}"
MOSS_CONDA_ENV="${MOSS_CONDA_ENV:-$MOSS_ROOT/conda/moss-py312}"

module load conda
# shellcheck disable=SC1090
source "$(conda info --base)/etc/profile.d/conda.sh"
if [[ ! -d "$MOSS_CONDA_ENV" ]]; then
    conda create -y -p "$MOSS_CONDA_ENV" python=3.12
fi
conda activate "$MOSS_CONDA_ENV"
python -m pip install --upgrade pip uv
cd "$MOSS_REPO"
uv sync --frozen --no-managed-python
"$MOSS_REPO/.venv/bin/python" --version
