#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_KRIGING_DIR = PROJECT_ROOT / "figures" / "visualization" / "kriging" / "compare_exp8km"
DEFAULT_HYSPLIT_DIR = PROJECT_ROOT / "figures" / "visualization" / "hysplit_compare"
DEFAULT_OUTPUT = PROJECT_ROOT / "figures" / "visualization" / "comparison_sheets" / "kriging_vs_hysplit_exp8km.png"

ROW_SPECS = [
    ("Window 0", "Ignition to +4 h", "window0_exp8km.png", "w16_2300_to_0300"),
    ("Window 1", "+4 h to +8 h", "window1_exp8km.png", "w17_0300_to_0700"),
    ("Window 4", "+16 h to +20 h", "window4_exp8km.png", "w17_1500_to_1900"),
    ("Window 7", "+28 h to +32 h", "window7_exp8km.png", "w18_0300_to_0700"),
    ("Window 10", "+40 h to +44 h", "window10_exp8km.png", "w18_1500_to_1900"),
]
HEIGHTS = [10, 25, 50]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a comparison sheet with kriged enhancement and matching HYSPLIT panels."
    )
    parser.add_argument("--kriging-dir", type=Path, default=DEFAULT_KRIGING_DIR)
    parser.add_argument("--hysplit-dir", type=Path, default=DEFAULT_HYSPLIT_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--hysplit-height-m", type=int, choices=HEIGHTS)
    parser.add_argument(
        "--rows",
        default="0,1,4,7,10",
        help="Comma-separated window numbers to include, e.g. 1,4,7,10",
    )
    parser.add_argument("--dpi", type=int, default=180)
    parser.add_argument("--title", default="PurpleAir Enhancement vs HYSPLIT 4-Hour Windows")
    return parser.parse_args()


def load_image(path: Path) -> Image.Image:
    if not path.exists():
        raise FileNotFoundError(path)
    with Image.open(path) as image:
        return image.copy()


def select_rows(rows_arg: str) -> list[tuple[str, str, str, str]]:
    requested = []
    for token in rows_arg.split(","):
        token = token.strip()
        if not token:
            continue
        requested.append(int(token))
    selected = []
    for spec in ROW_SPECS:
        window_num = int(spec[0].split()[1])
        if window_num in requested:
            selected.append(spec)
    if not selected:
        raise ValueError(f"No rows selected from --rows={rows_arg}")
    return selected


def main() -> None:
    args = parse_args()
    row_specs = select_rows(args.rows)

    if args.hysplit_height_m is None:
        column_titles = [
            "PurpleAir kriging\nexp variogram, 8 km mask",
            "HYSPLIT 10 m",
            "HYSPLIT 25 m",
            "HYSPLIT 50 m",
        ]
    else:
        column_titles = [
            "PurpleAir kriging\nexp variogram, 8 km mask",
            f"HYSPLIT {args.hysplit_height_m} m",
        ]

    kriging_sample = load_image(args.kriging_dir / row_specs[0][2])
    sample_height = args.hysplit_height_m or HEIGHTS[0]
    hysplit_sample = load_image(args.hysplit_dir / f"{row_specs[0][3]}_h{sample_height:03d}.png")
    row_height = 3.7
    kriging_width = row_height * (kriging_sample.width / kriging_sample.height)
    hysplit_width = row_height * (hysplit_sample.width / hysplit_sample.height)

    n_rows = len(row_specs)
    n_cols = len(column_titles)
    if args.hysplit_height_m is None:
        width_ratios = [kriging_width, hysplit_width, hysplit_width, hysplit_width]
    else:
        width_ratios = [kriging_width, hysplit_width]
    fig_w = sum(width_ratios) + 1.9
    fig_h = n_rows * row_height + 1.9

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(fig_w, fig_h),
        dpi=args.dpi,
        squeeze=False,
        gridspec_kw={"width_ratios": width_ratios},
    )
    fig.patch.set_facecolor("white")
    fig.suptitle(args.title, fontsize=18, y=0.992)
    fig.text(
        0.5,
        0.972,
        "Rows: matching 4-hour windows after ignition | Columns: kriged enhancement and HYSPLIT release heights",
        ha="center",
        fontsize=10,
    )

    for col_idx, title in enumerate(column_titles):
        axes[0][col_idx].set_title(title, fontsize=11, pad=10)

    for row_idx, (row_name, row_span, kriging_name, hysplit_prefix) in enumerate(row_specs):
        row_label = f"{row_name}\n{row_span}"
        axes[row_idx][0].set_ylabel(row_label, fontsize=10, rotation=0, labelpad=68, va="center")

        kriging_image = load_image(args.kriging_dir / kriging_name)
        axes[row_idx][0].imshow(kriging_image)

        if args.hysplit_height_m is None:
            for col_offset, height in enumerate(HEIGHTS, start=1):
                image = load_image(args.hysplit_dir / f"{hysplit_prefix}_h{height:03d}.png")
                axes[row_idx][col_offset].imshow(image)
        else:
            image = load_image(args.hysplit_dir / f"{hysplit_prefix}_h{args.hysplit_height_m:03d}.png")
            axes[row_idx][1].imshow(image)

    for row_axes in axes:
        for ax in row_axes:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.set_frame_on(True)

    plt.tight_layout(rect=[0.07, 0.035, 0.995, 0.955])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote comparison sheet: {args.output}")


if __name__ == "__main__":
    main()
