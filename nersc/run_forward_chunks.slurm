#!/usr/bin/env bash
# A six-way array covers the default 96-row combined phase-1 manifest in 16-row chunks.
# Change --array and MOSS_ROWS_PER_ARRAY_TASK together for a different manifest size.
#SBATCH --job-name=moss-forward-chunk
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --array=0-5
#SBATCH --time=02:00:00
#SBATCH --output=moss-forward-%A_%a.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
MANIFEST="${MANIFEST:-$MOSS_MANIFEST_DIR/phase1.csv}"
MOSS_JOBS="${MOSS_JOBS:-8}"
MOSS_ROWS_PER_ARRAY_TASK="${MOSS_ROWS_PER_ARRAY_TASK:-16}"
test -f "$MANIFEST"

rows="$($MOSS_PYTHON -c 'import pandas as pd, sys; print(len(pd.read_csv(sys.argv[1])))' "$MANIFEST")"
start="$((SLURM_ARRAY_TASK_ID * MOSS_ROWS_PER_ARRAY_TASK))"
stop="$((start + MOSS_ROWS_PER_ARRAY_TASK - 1))"
if [[ "$start" -ge "$rows" ]]; then
    echo "No rows assigned to array task $SLURM_ARRAY_TASK_ID"
    exit 0
fi
if [[ "$stop" -ge "$rows" ]]; then stop="$((rows - 1))"; fi

runner="$MOSS_REPO/scripts/hysplit/run_forward_manifest_row.py"
if command -v parallel >/dev/null 2>&1; then
    seq "$start" "$stop" | parallel --jobs "$MOSS_JOBS" --halt soon,fail=1 \
        "$MOSS_PYTHON" "$runner" --manifest "$MANIFEST" --row-index {}
else
    seq "$start" "$stop" | xargs -n 1 -P "$MOSS_JOBS" -I {} \
        "$MOSS_PYTHON" "$runner" --manifest "$MANIFEST" --row-index {}
fi
