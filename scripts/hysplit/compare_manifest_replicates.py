#!/usr/bin/env python3
"""Compare repeated HYSPLIT manifest rows using exact hashes and concentration metrics."""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from compare_combined_to_separate import import_hysplitdata, metrics, read_period


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument(
        "--group-by-seed",
        action="store_true",
        help="Compare only rows sharing a seed; useful for exact-repeat determinism checks.",
    )
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    args = parse_args()
    hysplitdata = import_hysplitdata()
    manifest = pd.read_csv(args.manifest)
    group_columns = ["scenario_tag", "logical_window_indices"]
    if args.group_by_seed:
        group_columns.append("seed")
    comparisons: list[dict[str, object]] = []
    for keys, group in manifest.groupby(group_columns, dropna=False):
        if len(group) < 2:
            continue
        if not isinstance(keys, tuple):
            keys = (keys,)
        group_info = dict(zip(group_columns, keys))
        for (_, left), (_, right) in combinations(group.iterrows(), 2):
            left_cdump = Path(left["expected_run_dir"]) / "cdump"
            right_cdump = Path(right["expected_run_dir"]) / "cdump"
            lon_a, lat_a, conc_a = read_period(left_cdump, left["sample_start_utc"], left["sample_stop_utc"], hysplitdata)
            lon_b, lat_b, conc_b = read_period(right_cdump, right["sample_start_utc"], right["sample_stop_utc"], hysplitdata)
            if conc_a.shape != conc_b.shape or not np.allclose(lon_a, lon_b) or not np.allclose(lat_a, lat_b):
                raise ValueError(f"Grid mismatch between {left_cdump} and {right_cdump}")
            left_hash = sha256(left_cdump)
            right_hash = sha256(right_cdump)
            comparisons.append(
                {
                    **group_info,
                    "left_replicate_index": int(left["replicate_index"]),
                    "right_replicate_index": int(right["replicate_index"]),
                    "left_seed": int(left["seed"]),
                    "right_seed": int(right["seed"]),
                    "left_cdump": str(left_cdump),
                    "right_cdump": str(right_cdump),
                    "binary_sha256_equal": left_hash == right_hash,
                    **metrics(conc_a, conc_b),
                }
            )
    if not comparisons:
        raise ValueError("Manifest did not contain any comparable replicate pairs")
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    payload = {"manifest": str(args.manifest), "group_by_seed": args.group_by_seed, "comparisons": comparisons}
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    exact = sum(bool(item["binary_sha256_equal"]) for item in comparisons)
    print(f"Compared {len(comparisons)} replicate pairs; exact binary matches: {exact}")
    print(f"Wrote {args.output_json}")


if __name__ == "__main__":
    main()
