#!/usr/bin/env bash
#SBATCH --job-name=moss-forward
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --cpus-per-task=16
#SBATCH --time=02:00:00
#SBATCH --output=moss-forward-%j.out

# Set MANIFEST when submitting, for example:
#   MANIFEST=$MOSS_MANIFEST_DIR/phase1.csv sbatch nersc/run_forward_packed.slurm
# Tune MOSS_JOBS only after representative timing and memory benchmarks.

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
MANIFEST="${MANIFEST:-$MOSS_MANIFEST_DIR/phase1.csv}"
MOSS_JOBS="${MOSS_JOBS:-8}"
test -f "$MANIFEST"

rows="$($MOSS_PYTHON -c 'import pandas as pd, sys; print(len(pd.read_csv(sys.argv[1])))' "$MANIFEST")"
if [[ "$rows" -eq 0 ]]; then
    echo "Manifest has no rows: $MANIFEST" >&2
    exit 2
fi

runner="$MOSS_REPO/scripts/hysplit/run_forward_manifest_row.py"
if command -v parallel >/dev/null 2>&1; then
    seq 0 "$((rows - 1))" | parallel --jobs "$MOSS_JOBS" --halt soon,fail=1 \
        "$MOSS_PYTHON" "$runner" --manifest "$MANIFEST" --row-index {}
else
    seq 0 "$((rows - 1))" | xargs -n 1 -P "$MOSS_JOBS" -I {} \
        "$MOSS_PYTHON" "$runner" --manifest "$MANIFEST" --row-index {}
fi

"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/merge_forward_results.py" --manifest "$MANIFEST"
