#!/usr/bin/env python3
"""Execute exactly one forward-HYSPLIT manifest row with restart-safe metadata."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--row-index", type=int, required=True)
    parser.add_argument("--force", action="store_true", help="Re-run even when a valid completed status exists.")
    return parser.parse_args()


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_row(manifest_path: Path, row_index: int) -> pd.Series:
    frame = pd.read_csv(manifest_path)
    matches = frame.loc[frame["row_index"] == row_index]
    if len(matches) != 1:
        raise ValueError(f"Expected one row_index={row_index} in {manifest_path}, found {len(matches)}")
    return matches.iloc[0]


def valid_cdump(run_dir: Path) -> bool:
    cdump = run_dir / "cdump"
    return cdump.is_file() and cdump.stat().st_size > 0


def completed_status(status_path: Path, run_dir: Path) -> bool:
    if not status_path.is_file() or not valid_cdump(run_dir):
        return False
    try:
        return json.loads(status_path.read_text(encoding="utf-8")).get("status") == "completed"
    except json.JSONDecodeError:
        return False


def text(row: pd.Series, field: str) -> str:
    value = row[field]
    if pd.isna(value):
        raise ValueError(f"Manifest field {field!r} is empty")
    return str(value)


def build_command(row: pd.Series) -> list[str]:
    return [
        sys.executable,
        text(row, "forward_script"),
        "--start-utc", text(row, "simulation_start_utc"),
        "--end-utc", text(row, "simulation_end_utc"),
        "--release-start-utc", text(row, "release_start_utc"),
        "--sample-start-utc", text(row, "sample_start_utc"),
        "--sample-stop-utc", text(row, "sample_stop_utc"),
        "--source-lat", text(row, "source_lat"),
        "--source-lon", text(row, "source_lon"),
        "--source-height-m", text(row, "source_height_m"),
        "--source-geometry", text(row, "source_geometry"),
        "--source-footprint-m", text(row, "source_footprint_m"),
        "--source-grid-shape", text(row, "source_grid_shape"),
        "--source-rotation-deg", text(row, "source_rotation_deg"),
        "--emission-rate", text(row, "emission_rate"),
        "--emission-hours", text(row, "emission_hours"),
        "--concentration-level-m", text(row, "concentration_level_m"),
        "--grid-center-lat", text(row, "grid_center_lat"),
        "--grid-center-lon", text(row, "grid_center_lon"),
        "--grid-spacing-deg", text(row, "grid_spacing_deg"),
        "--grid-span-deg", text(row, "grid_span_deg"),
        "--sampling-interval-hours", text(row, "sampling_interval_hours"),
        "--numpar", text(row, "numpar"),
        "--maxpar", text(row, "maxpar"),
        "--krand", text(row, "krand"),
        "--seed", text(row, "seed"),
        "--plot-styles", text(row, "plot_styles"),
        "--hrrr-dir", text(row, "hrrr_dir"),
        "--hysplit-root", text(row, "hysplit_root"),
        "--output-root", text(row, "row_output_root"),
        "--run-tag", text(row, "run_tag"),
    ]


def main() -> None:
    args = parse_args()
    row = read_row(args.manifest, args.row_index)
    output_root = Path(text(row, "row_output_root"))
    run_dir = Path(text(row, "expected_run_dir"))
    status_path = Path(text(row, "status_path"))
    if not args.force and completed_status(status_path, run_dir):
        print(f"row_index={args.row_index} already completed: {run_dir}")
        return

    output_root.mkdir(parents=True, exist_ok=True)
    run_log = output_root / "row_runner.log"
    started = timestamp()
    base_status: dict[str, object] = {
        "status": "running",
        "row_index": args.row_index,
        "config_hash": text(row, "config_hash"),
        "started_at_utc": started,
        "manifest": str(args.manifest.resolve()),
        "run_dir": str(run_dir),
        "hysplit_executable": str(Path(text(row, "hysplit_root")) / "exec" / "hycs_std"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
        "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "hostname": os.environ.get("HOSTNAME"),
    }
    write_json_atomic(status_path, base_status)
    command = build_command(row)
    elapsed_start = time.monotonic()
    try:
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        run_log.write_text(proc.stdout, encoding="utf-8")
        succeeded = proc.returncode == 0 and valid_cdump(run_dir)
        final_status = {
            **base_status,
            "status": "completed" if succeeded else "failed",
            "finished_at_utc": timestamp(),
            "elapsed_seconds": round(time.monotonic() - elapsed_start, 3),
            "return_code": proc.returncode,
            "runner_log": str(run_log),
            "cdump": str(run_dir / "cdump"),
            "cdump_bytes": (run_dir / "cdump").stat().st_size if valid_cdump(run_dir) else 0,
        }
        write_json_atomic(status_path, final_status)
        if not succeeded:
            raise SystemExit(f"row_index={args.row_index} failed; inspect {run_log} and {status_path}")
    except BaseException as exc:
        failure_status = {
            **base_status,
            "status": "failed",
            "finished_at_utc": timestamp(),
            "elapsed_seconds": round(time.monotonic() - elapsed_start, 3),
            "error": str(exc),
            "runner_log": str(run_log),
        }
        write_json_atomic(status_path, failure_status)
        raise
    print(f"row_index={args.row_index} completed: {run_dir}")


if __name__ == "__main__":
    main()
