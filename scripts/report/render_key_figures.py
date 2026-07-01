#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = PROJECT_ROOT / "report" / "images"
DEFAULT_ENSEMBLE_MANIFEST = (
    PROJECT_ROOT
    / "hysplit"
    / "runs"
    / "forward_dispersion"
    / "sweeps"
    / "report_height_ensemble_manifest.csv"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate a small set of key report figures from local PurpleAir and HYSPLIT outputs."
    )
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--ensemble-manifest", type=Path, default=DEFAULT_ENSEMBLE_MANIFEST)
    parser.add_argument(
        "--purpleair-window-index",
        type=int,
        default=0,
        help="4-hour PurpleAir enhancement window to render for report/images/purple_air_frame.png.",
    )
    parser.add_argument(
        "--hysplit-window-index",
        type=int,
        default=4,
        help="Window index from the report height ensemble manifest used for the HYSPLIT height comparison figures.",
    )
    parser.add_argument(
        "--hysplit-heights-m",
        default="10,50,250",
        help="Comma-separated source heights to render into the report image placeholders.",
    )
    parser.add_argument(
        "--basemap-style",
        choices=("satellite", "light", "dark"),
        default="satellite",
        help="Basemap style for HYSPLIT custom renderings.",
    )
    parser.add_argument(
        "--purpleair-basemap-style",
        choices=("gray", "light", "dark", "satellite"),
        default="gray",
        help="Basemap style for the PurpleAir report frame.",
    )
    parser.add_argument(
        "--skip-purpleair",
        action="store_true",
        help="Skip rebuilding the PurpleAir report image.",
    )
    parser.add_argument(
        "--skip-hysplit",
        action="store_true",
        help="Skip rebuilding the HYSPLIT height comparison images.",
    )
    return parser.parse_args()


def parse_heights(raw: str) -> list[int]:
    heights = [int(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not heights:
        raise ValueError("Expected at least one height")
    return heights


def run_command(cmd: list[str]) -> None:
    env = dict(os.environ)
    env.setdefault("MPLCONFIGDIR", "/tmp/mplconfig")
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True, env=env)


def render_purpleair(args: argparse.Namespace) -> None:
    output_path = args.report_dir / "purple_air_frame.png"
    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "purple_air" / "tier1_bubble_map.py"),
        "--mode",
        "enhancement",
        "--png",
        "--window-index",
        str(args.purpleair_window_index),
        "--data-csv",
        str(PROJECT_ROOT / "data" / "purple_air" / "mbuapcd_pm25_enhancement_4h.csv"),
        "--sensor-csv",
        str(PROJECT_ROOT / "data" / "purple_air" / "sensors_mbuapcd_active_cleaned.csv"),
        "--boundary-geojson",
        str(PROJECT_ROOT / "data" / "purple_air" / "monterey_bay_unified_apcd.geojson"),
        "--png-out",
        str(output_path),
        "--basemap-style",
        args.purpleair_basemap_style,
    ]
    run_command(cmd)


def load_manifest(path: Path) -> pd.DataFrame:
    manifest = pd.read_csv(path)
    if "source_height_m" not in manifest.columns or "run_dir" not in manifest.columns:
        raise ValueError(f"Manifest missing required columns: {path}")
    manifest["source_height_m"] = manifest["source_height_m"].astype(float)
    manifest["sample_start_utc"] = pd.to_datetime(manifest["sample_start_utc"], utc=True)
    manifest["window_index"] = (
        (manifest["sample_start_utc"] - pd.Timestamp("2025-01-16T23:00:00Z"))
        .dt.total_seconds()
        .div(3600 * 4)
        .round()
        .astype(int)
    )
    return manifest


def select_run(manifest: pd.DataFrame, height_m: int, window_index: int) -> Path:
    matches = manifest.loc[
        (manifest["source_height_m"].round().astype(int) == int(height_m))
        & (manifest["window_index"] == int(window_index))
        & (manifest["status"] == "completed")
    ]
    if matches.empty:
        raise FileNotFoundError(
            f"No completed ensemble run found for height {height_m} m and window {window_index}"
        )
    return Path(matches.iloc[0]["run_dir"]) / "cdump"


def render_hysplit(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.ensemble_manifest)
    for height_m in parse_heights(args.hysplit_heights_m):
        cdump_path = select_run(manifest, height_m, args.hysplit_window_index)
        output_path = args.report_dir / f"hysplit_height_{height_m}m_placeholder.png"
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "hysplit" / "plot_cdump.py"),
            str(cdump_path),
            "--output-png",
            str(output_path),
            "--view",
            "plume",
            "--basemap",
            "--basemap-style",
            args.basemap_style,
            "--title",
            f"HYSPLIT | {height_m} m release | window {args.hysplit_window_index}",
        ]
        run_command(cmd)


def main() -> None:
    args = parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_purpleair:
        render_purpleair(args)
    if not args.skip_hysplit:
        render_hysplit(args)

    print(f"Updated report figures in {args.report_dir}")


if __name__ == "__main__":
    main()
