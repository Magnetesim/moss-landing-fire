#!/usr/bin/env bash
# Submit serially dependent 1/4/8/16-way packed-run benchmarks.

set -euo pipefail

source "${MOSS_REPO:-$SCRATCH/moss-landing-fire/repo/moss-landing-fire}/nersc/env.sh"
BENCH_ROOT="${BENCH_ROOT:-$MOSS_ROOT/work/packing-benchmark}"
BENCH_NUMPAR="${BENCH_NUMPAR:-500}"
BENCH_SETUPS="${BENCH_SETUPS:-point|300,120|1,1;area_grid|300,120|5,3;area_grid|600,240|7,3;area_grid|900,360|9,5}"
PACKING_LEVELS="${PACKING_LEVELS:-1 4 8 16}"
PACKING_PREVIOUS_JOB="${PACKING_PREVIOUS_JOB:-}"
PACKING_SUBMIT_SUMMARY="${PACKING_SUBMIT_SUMMARY:-1}"
BENCH_QOS="${BENCH_QOS:-regular}"
mkdir -p "$BENCH_ROOT"

previous_job="$PACKING_PREVIOUS_JOB"
job_ids=()
for jobs in $PACKING_LEVELS; do
    case "$jobs" in
        1)
            # One deliberately expensive case establishes single-process runtime and memory.
            heights="100"
            durations="24"
            setups="area_grid|900,360|9,5"
            time_limit="00:30:00"
            ;;
        4)
            # Four geometries at the same height/duration fill one four-process wave.
            heights="100"
            durations="24"
            setups="$BENCH_SETUPS"
            time_limit="00:30:00"
            ;;
        8)
            # Two heights times four geometries fill one eight-process wave.
            heights="10,100"
            durations="24"
            setups="$BENCH_SETUPS"
            time_limit="00:35:00"
            ;;
        16)
            # Two heights times two durations times four geometries fill one 16-process wave.
            heights="10,100"
            durations="4,24"
            setups="$BENCH_SETUPS"
            time_limit="00:40:00"
            ;;
        *)
            echo "Unsupported packing level: $jobs (use 1, 4, 8, or 16)" >&2
            exit 2
            ;;
    esac
    case_root="$BENCH_ROOT/jobs-$jobs"
    manifest="$case_root/manifest.csv"
    "$MOSS_PYTHON" "$MOSS_REPO/scripts/hysplit/build_forward_manifest.py" \
        --manifest "$manifest" \
        --runs-root "$case_root/rows" \
        --hrrr-dir "$HRRR_DIR" \
        --hysplit-root "$HYSPLIT_ROOT" \
        --source-heights-m "$heights" \
        --release-durations-h "$durations" \
        --source-setups "$setups" \
        --window-indices 1,4,7,10 \
        --execution-shape combined \
        --numpar "$BENCH_NUMPAR" \
        --run-tag-prefix "packing_j$jobs"
    dependency=()
    if [[ -n "$previous_job" ]]; then dependency=(--dependency="afterok:$previous_job"); fi
    job_id="$(sbatch --parsable --qos="$BENCH_QOS" --time="$time_limit" --cpus-per-task="$jobs" \
        "${dependency[@]}" \
        --export="ALL,MANIFEST=$manifest,MOSS_JOBS=$jobs" \
        "$MOSS_REPO/nersc/run_forward_packed.slurm")"
    job_ids+=("$job_id")
    previous_job="$job_id"
    echo "Submitted jobs=$jobs as $job_id"
done

summary_id=""
if [[ "$PACKING_SUBMIT_SUMMARY" == "1" ]]; then
    summary_id="$(sbatch --parsable --qos="$BENCH_QOS" --time=00:05:00 --dependency="afterok:$previous_job" \
        --export="ALL,BENCH_ROOT=$BENCH_ROOT" \
        "$MOSS_REPO/nersc/summarize_packing_benchmark.slurm")"
fi
printf 'packing_jobs=%s\nsummary_job=%s\n' "${job_ids[*]}" "$summary_id"
