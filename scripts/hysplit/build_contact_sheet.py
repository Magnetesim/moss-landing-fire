#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image
import pandas as pd

from moss_landing.paths import PROJECT_ROOT

DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "hysplit"
    / "runs"
    / "forward_dispersion"
    / "sweeps"
    / "report_height_ensemble_manifest_with_pngs.csv"
)
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "hysplit"
    / "runs"
    / "forward_dispersion"
    / "sweeps"
    / "report_height_ensemble_contact_sheet.png"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a time-by-height contact sheet from rendered HYSPLIT plume PNGs."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--thumb-width", type=int, default=240)
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--title", default="Moss Landing HYSPLIT Time-Height Ensemble")
    return parser.parse_args()


def time_label(raw: str) -> str:
    ts = pd.Timestamp(raw)
    return ts.strftime("%m-%d %H:%M UTC")


def main() -> None:
    args = parse_args()
    manifest = pd.read_csv(args.manifest)
    if manifest.empty:
        raise ValueError(f"Manifest is empty: {args.manifest}")
    if "png_path" not in manifest.columns:
        raise ValueError(f"Manifest must include a png_path column: {args.manifest}")

    manifest["sample_start_utc"] = pd.to_datetime(manifest["sample_start_utc"], utc=True)
    manifest["source_height_m"] = manifest["source_height_m"].astype(float)

    heights = sorted(manifest["source_height_m"].unique().tolist())
    windows = sorted(manifest["sample_start_utc"].dt.strftime("%Y-%m-%dT%H:%M:%S%z").unique().tolist())
    window_index = {key: idx for idx, key in enumerate(windows)}
    height_index = {value: idx for idx, value in enumerate(heights)}

    sample_path = Path(manifest.iloc[0]["png_path"])
    with Image.open(sample_path) as sample_image:
        aspect = sample_image.height / sample_image.width
    thumb_w = args.thumb_width
    thumb_h = int(round(thumb_w * aspect))

    n_rows = len(windows)
    n_cols = len(heights)
    fig_w = (n_cols * thumb_w + 260) / args.dpi
    fig_h = (n_rows * thumb_h + 220) / args.dpi

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(fig_w, fig_h),
        dpi=args.dpi,
        squeeze=False,
    )
    fig.patch.set_facecolor("white")
    fig.suptitle(args.title, fontsize=18, y=0.995)

    for row_idx, window_key in enumerate(windows):
        window_label = time_label(pd.Timestamp(window_key).isoformat())
        axes[row_idx][0].set_ylabel(window_label, fontsize=9, rotation=0, labelpad=60, va="center")

    for col_idx, height in enumerate(heights):
        axes[0][col_idx].set_title(f"{int(round(height))} m", fontsize=11, pad=10)

    for _, record in manifest.iterrows():
        window_key = record["sample_start_utc"].strftime("%Y-%m-%dT%H:%M:%S%z")
        row_idx = window_index[window_key]
        col_idx = height_index[float(record["source_height_m"])]
        ax = axes[row_idx][col_idx]
        image_path = Path(record["png_path"])
        with Image.open(image_path) as image:
            ax.imshow(image)
        ax.set_xticks([])
        ax.set_yticks([])
        ax.set_frame_on(True)

    for row_axes in axes:
        for ax in row_axes:
            if not ax.images:
                ax.axis("off")

    fig.text(0.5, 0.965, "Columns: source release height | Rows: 4-hour windows from ignition", ha="center", fontsize=10)
    plt.tight_layout(rect=[0.055, 0.035, 0.995, 0.96])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote contact sheet: {args.output}")


if __name__ == "__main__":
    main()
