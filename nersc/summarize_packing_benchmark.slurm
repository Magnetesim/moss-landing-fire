#!/usr/bin/env bash
#SBATCH --job-name=moss-pack-summary
#SBATCH --account=m4007
#SBATCH --qos=regular
#SBATCH --constraint=cpu
#SBATCH --nodes=1
#SBATCH --time=00:05:00
#SBATCH --output=moss-pack-summary-%j.out

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
BENCH_ROOT="${BENCH_ROOT:-$MOSS_ROOT/work/packing-benchmark}"
mapfile -t manifests < <(find "$BENCH_ROOT" -mindepth 2 -maxdepth 2 -name manifest.csv | sort)
if [[ "${#manifests[@]}" -eq 0 ]]; then
    echo "No benchmark manifests found below $BENCH_ROOT" >&2
    exit 2
fi
args=()
for manifest in "${manifests[@]}"; do args+=(--manifest "$manifest"); done
"$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/summarize_packing_benchmark.py" \
    "${args[@]}" \
    --output-csv "$BENCH_ROOT/packing_summary.csv" \
    --output-json "$BENCH_ROOT/packing_summary.json"
