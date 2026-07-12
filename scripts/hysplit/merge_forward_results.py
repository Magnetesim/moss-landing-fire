#!/usr/bin/env python3
"""Merge row-level HYSPLIT status files into a campaign manifest."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Defaults beside the input manifest.")
    parser.add_argument("--summary", type=Path, help="Defaults beside the merged manifest.")
    parser.add_argument("--allow-incomplete", action="store_true")
    return parser.parse_args()


def load_status(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"status": "missing"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"status": "invalid_status", "error": str(exc)}


def main() -> None:
    args = parse_args()
    manifest = pd.read_csv(args.manifest)
    output = args.output or args.manifest.with_name(args.manifest.stem + "_merged.csv")
    summary = args.summary or output.with_suffix(".summary.json")
    status_records = [load_status(Path(path)) for path in manifest["status_path"]]
    status_frame = pd.DataFrame(status_records).add_prefix("row_")
    merged = pd.concat([manifest.reset_index(drop=True), status_frame.reset_index(drop=True)], axis=1)
    output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(output, index=False)
    counts = Counter(status_frame.get("row_status", pd.Series(["missing"] * len(manifest))).fillna("missing"))
    summary_payload = {"manifest": str(args.manifest), "merged_manifest": str(output), "total_rows": len(manifest), "status_counts": dict(sorted(counts.items()))}
    summary.write_text(json.dumps(summary_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary_payload, indent=2, sort_keys=True))
    complete = counts.get("completed", 0) == len(manifest)
    if not complete and not args.allow_incomplete:
        raise SystemExit("Campaign is incomplete; pass --allow-incomplete to merge without a successful exit status.")


if __name__ == "__main__":
    main()
