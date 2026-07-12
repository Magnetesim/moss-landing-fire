#!/usr/bin/env python3
"""Summarize score and rank stability across HYSPLIT particle counts."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, spearmanr


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", action="append", required=True, metavar="NUMPAR=CSV")
    parser.add_argument("--per-run", action="append", default=[], metavar="NUMPAR=CSV")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def labelled_paths(values: list[str]) -> dict[int, Path]:
    parsed: dict[int, Path] = {}
    for value in values:
        label, separator, raw_path = value.partition("=")
        if not separator or not label.strip().isdigit() or not raw_path.strip():
            raise ValueError(f"Expected NUMPAR=CSV, got {value!r}")
        count = int(label)
        if count in parsed:
            raise ValueError(f"Duplicate particle count: {count}")
        parsed[count] = Path(raw_path)
    return dict(sorted(parsed.items()))


def finite(value: float) -> float | None:
    return float(value) if np.isfinite(value) else None


def load_scenarios(paths: dict[int, Path]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    expected: set[str] | None = None
    for count, path in paths.items():
        frame = pd.read_csv(path)
        required = {"scenario_id", "mean_total_score"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        scenarios = set(frame["scenario_id"].astype(str))
        if expected is None:
            expected = scenarios
        elif scenarios != expected:
            raise ValueError(f"Scenario set differs for numpar={count}")
        frame = frame.copy()
        frame["numpar"] = count
        frame["rank"] = frame["mean_total_score"].rank(method="min", ascending=False).astype(int)
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def scenario_stability(long: pd.DataFrame) -> pd.DataFrame:
    return (
        long.groupby("scenario_id", as_index=False)
        .agg(
            min_score=("mean_total_score", "min"),
            max_score=("mean_total_score", "max"),
            mean_score=("mean_total_score", "mean"),
            score_std=("mean_total_score", "std"),
            best_rank=("rank", "min"),
            worst_rank=("rank", "max"),
        )
        .assign(
            score_range=lambda frame: frame["max_score"] - frame["min_score"],
            rank_range=lambda frame: frame["worst_rank"] - frame["best_rank"],
        )
        .sort_values(["best_rank", "score_range", "scenario_id"])
    )


def pairwise_rank_metrics(long: pd.DataFrame, top_k: int) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    indexed = {count: frame.set_index("scenario_id") for count, frame in long.groupby("numpar")}
    for left, right in combinations(sorted(indexed), 2):
        left_frame = indexed[left].sort_index()
        right_frame = indexed[right].sort_index()
        rho = spearmanr(left_frame["mean_total_score"], right_frame["mean_total_score"]).statistic
        tau = kendalltau(left_frame["mean_total_score"], right_frame["mean_total_score"]).statistic
        left_top = set(left_frame.nsmallest(top_k, "rank").index)
        right_top = set(right_frame.nsmallest(top_k, "rank").index)
        records.append(
            {
                "left_numpar": left,
                "right_numpar": right,
                "scenario_count": len(left_frame),
                "spearman_rho": finite(float(rho)),
                "kendall_tau": finite(float(tau)),
                "top_k": top_k,
                "top_k_overlap": len(left_top & right_top),
                "top_k_jaccard": len(left_top & right_top) / len(left_top | right_top),
                "max_absolute_score_change": float(
                    np.max(np.abs(left_frame["mean_total_score"] - right_frame["mean_total_score"]))
                ),
            }
        )
    return records


def load_window_scores(paths: dict[int, Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not paths:
        return pd.DataFrame(), pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for count, path in paths.items():
        frame = pd.read_csv(path)
        required = {"scenario_id", "window_index", "total_score"}
        missing = required.difference(frame.columns)
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        frame = frame.copy()
        frame["numpar"] = count
        frames.append(frame)
    long = pd.concat(frames, ignore_index=True)
    stability = (
        long.groupby(["scenario_id", "window_index"], as_index=False)
        .agg(min_score=("total_score", "min"), max_score=("total_score", "max"), score_std=("total_score", "std"))
        .assign(score_range=lambda frame: frame["max_score"] - frame["min_score"])
        .sort_values(["score_range", "scenario_id", "window_index"], ascending=[False, True, True])
    )
    return long, stability


def main() -> None:
    args = parse_args()
    score_paths = labelled_paths(args.scores)
    if len(score_paths) < 2:
        raise ValueError("At least two --scores inputs are required")
    if args.top_k < 1:
        raise ValueError("--top-k must be positive")
    run_paths = labelled_paths(args.per_run)
    if run_paths and set(run_paths) != set(score_paths):
        raise ValueError("--per-run particle counts must match --scores")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    long = load_scenarios(score_paths)
    stability = scenario_stability(long)
    pairs = pairwise_rank_metrics(long, min(args.top_k, long["scenario_id"].nunique()))
    long.to_csv(args.output_dir / "scenario_scores_by_numpar.csv", index=False)
    stability.to_csv(args.output_dir / "scenario_stability.csv", index=False)

    window_long, window_stability = load_window_scores(run_paths)
    if not window_long.empty:
        window_long.to_csv(args.output_dir / "window_scores_by_numpar.csv", index=False)
        window_stability.to_csv(args.output_dir / "window_stability.csv", index=False)

    payload = {
        "particle_counts": sorted(score_paths),
        "scenario_count": int(long["scenario_id"].nunique()),
        "window_comparisons": int(len(window_long)),
        "pairwise_rank_metrics": pairs,
        "maximum_scenario_score_range": float(stability["score_range"].max()),
        "maximum_scenario_rank_range": int(stability["rank_range"].max()),
    }
    output = args.output_dir / "summary.json"
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"Wrote convergence products to {args.output_dir}")


if __name__ == "__main__":
    main()
