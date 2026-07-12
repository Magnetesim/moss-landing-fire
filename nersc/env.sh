#!/usr/bin/env bash
# Shared Perlmutter environment for the Moss Landing HYSPLIT workflow.

set -euo pipefail

: "${SCRATCH:?NERSC SCRATCH must be defined before sourcing nersc/env.sh}"

export MOSS_ROOT="${MOSS_ROOT:-$SCRATCH/moss-landing-fire}"
export MOSS_REPO="${MOSS_REPO:-$MOSS_ROOT/repo/moss-landing-fire}"
export HYSPLIT_ROOT="${HYSPLIT_ROOT:-$MOSS_ROOT/hysplit/install/hysplit.v5.4.2_x86_64}"
export HRRR_DIR="${HRRR_DIR:-$MOSS_ROOT/hrrr}"
export MOSS_RUN_ROOT="${MOSS_RUN_ROOT:-$MOSS_ROOT/work/forward}"
export MOSS_MANIFEST_DIR="${MOSS_MANIFEST_DIR:-$MOSS_ROOT/work/manifests}"
export MOSS_CONDA_ENV="${MOSS_CONDA_ENV:-$MOSS_ROOT/conda/moss-py312}"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$MOSS_ROOT/work/matplotlib}"
export PYTHONNOUSERSITE=1

if [[ "${MOSS_ACTIVATE_ENV:-1}" == "1" ]]; then
    module load conda
    # shellcheck disable=SC1090
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$MOSS_CONDA_ENV"
fi

export MOSS_PYTHON="${MOSS_PYTHON:-$MOSS_REPO/.venv/bin/python}"
if [[ ! -x "$MOSS_PYTHON" ]]; then
    echo "Missing project Python at $MOSS_PYTHON. Run nersc/bootstrap_env.sh first." >&2
    return 1 2>/dev/null || exit 1
fi

mkdir -p "$MOSS_RUN_ROOT" "$MOSS_MANIFEST_DIR" "$MPLCONFIGDIR"
