#!/usr/bin/env python3
"""Summarize completed manifest rows from one or more packing benchmark manifests."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def read_status(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "missing"}
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    rows: list[dict[str, object]] = []
    for manifest_path in args.manifest:
        manifest = pd.read_csv(manifest_path)
        statuses = [read_status(Path(path)) for path in manifest["status_path"]]
        completed = [status for status in statuses if status.get("status") == "completed"]
        elapsed = [float(status["elapsed_seconds"]) for status in completed if status.get("elapsed_seconds") is not None]
        label = manifest_path.parent.name
        rows.append(
            {
                "benchmark": label,
                "manifest": str(manifest_path),
                "rows": len(manifest),
                "completed_rows": len(completed),
                "failed_or_missing_rows": len(manifest) - len(completed),
                "sum_row_seconds": sum(elapsed),
                "mean_row_seconds": (sum(elapsed) / len(elapsed)) if elapsed else None,
                "max_row_seconds": max(elapsed) if elapsed else None,
                "slurm_job_ids": ",".join(sorted({str(status.get("slurm_job_id")) for status in completed if status.get("slurm_job_id")})),
            }
        )
    frame = pd.DataFrame(rows)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_csv, index=False)
    payload = {"benchmarks": rows, "output_csv": str(args.output_csv)}
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
