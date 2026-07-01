#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

try:
    import contextily as cx
except ImportError:
    cx = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_MANIFEST = PROJECT_ROOT / "hysplit" / "runs" / "trajectory_runs_24h_primary_fixed" / "trajectory_manifest.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "figures" / "hysplit" / "trajectory_overview"
MOSS_LANDING_LAT = 36.8044
MOSS_LANDING_LON = -121.7883
HEIGHT_COLORS = {
    10: "#1f77b4",
    50: "#2ca02c",
    200: "#ff7f0e",
    500: "#d62728",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render quick-look figures from HYSPLIT tdump outputs.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--sample-count",
        type=int,
        default=12,
        help="Number of representative trajectories to show in the sample panel.",
    )
    return parser.parse_args()


def parse_tdump(tdump_path: Path) -> pd.DataFrame:
    lines = tdump_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines:
        return pd.DataFrame(columns=["age_hours", "latitude", "longitude", "height_m_agl"])

    met_count = int(lines[0].split()[0])
    data_start_idx = met_count + 4
    rows: list[dict[str, float]] = []
    for raw_line in lines[data_start_idx:]:
        parts = raw_line.split()
        if len(parts) < 12:
            continue
        rows.append(
            {
                "age_hours": float(parts[8]),
                "latitude": float(parts[9]),
                "longitude": float(parts[10]),
                "height_m_agl": float(parts[11]),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values("age_hours").reset_index(drop=True)


def load_manifest(manifest_path: Path) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_path)
    manifest = manifest[manifest["status"] == "completed"].copy()
    manifest["event_time_utc"] = pd.to_datetime(manifest["event_time_utc"], utc=True)
    return manifest


def attach_trajectories(manifest: pd.DataFrame) -> list[dict[str, object]]:
    trajectories: list[dict[str, object]] = []
    for row in manifest.itertuples(index=False):
        tdump_path = Path(row.tdump_path)
        data = parse_tdump(tdump_path)
        if data.empty:
            continue
        trajectories.append(
            {
                "sensor_index": row.sensor_index,
                "name": row.name,
                "height_agl_m": row.height_agl_m,
                "peak_pm25_atm": row.peak_pm25_atm,
                "event_time_utc": row.event_time_utc,
                "trajectory": data,
            }
        )
    return trajectories


def compute_bounds(trajectories: list[dict[str, object]]) -> tuple[float, float, float, float]:
    min_lon = min(traj["trajectory"]["longitude"].min() for traj in trajectories)
    max_lon = max(traj["trajectory"]["longitude"].max() for traj in trajectories)
    min_lat = min(traj["trajectory"]["latitude"].min() for traj in trajectories)
    max_lat = max(traj["trajectory"]["latitude"].max() for traj in trajectories)
    lon_pad = 0.25
    lat_pad = 0.2
    return min_lon - lon_pad, max_lon + lon_pad, min_lat - lat_pad, max_lat + lat_pad


def style_axis(ax: plt.Axes, bounds: tuple[float, float, float, float], title: str) -> None:
    min_lon, max_lon, min_lat, max_lat = bounds
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_aspect("equal", adjustable="box")
    ax.set_facecolor("#dfeaf2")
    if cx is not None:
        cx.add_basemap(
            ax,
            crs="EPSG:4326",
            source=cx.providers.CartoDB.Positron,
            attribution=False,
            zoom=9,
        )
    ax.grid(alpha=0.15, linewidth=0.5, color="#5a7184")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.scatter(
        [MOSS_LANDING_LON],
        [MOSS_LANDING_LAT],
        marker="*",
        s=140,
        color="black",
        zorder=5,
        label="Moss Landing",
    )


def plot_all_spaghetti(trajectories: list[dict[str, object]], output_path: Path, bounds: tuple[float, float, float, float]) -> None:
    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=150)
    style_axis(ax, bounds, "24-hour backward trajectories from PurpleAir primary events")

    used_labels: set[int] = set()
    for item in trajectories:
        traj = item["trajectory"]
        height = int(item["height_agl_m"])
        label = f"{height} m AGL" if height not in used_labels else None
        used_labels.add(height)
        ax.plot(
            traj["longitude"],
            traj["latitude"],
            color=HEIGHT_COLORS.get(height, "#555555"),
            alpha=0.11,
            linewidth=0.8,
            label=label,
        )

    ax.legend(loc="upper right", framealpha=0.9)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def plot_by_height(trajectories: list[dict[str, object]], output_path: Path, bounds: tuple[float, float, float, float]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(12, 10), dpi=150, sharex=True, sharey=True)
    for ax, height in zip(axes.flat, sorted(HEIGHT_COLORS)):
        style_axis(ax, bounds, f"{height} m AGL")
        subset = [item for item in trajectories if int(item["height_agl_m"]) == height]
        for item in subset:
            traj = item["trajectory"]
            ax.plot(traj["longitude"], traj["latitude"], color=HEIGHT_COLORS[height], alpha=0.2, linewidth=0.9)
        ax.scatter(
            [item["trajectory"].iloc[-1]["longitude"] for item in subset],
            [item["trajectory"].iloc[-1]["latitude"] for item in subset],
            s=8,
            color=HEIGHT_COLORS[height],
            alpha=0.35,
        )

    fig.suptitle("24-hour backward trajectories grouped by starting height", y=0.98)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def plot_representative(
    trajectories: list[dict[str, object]],
    output_path: Path,
    bounds: tuple[float, float, float, float],
    sample_count: int,
) -> None:
    height_50 = [item for item in trajectories if int(item["height_agl_m"]) == 50]
    selected = sorted(height_50, key=lambda item: float(item["peak_pm25_atm"]), reverse=True)[:sample_count]

    fig, ax = plt.subplots(figsize=(11, 8.5), dpi=150)
    style_axis(ax, bounds, f"Representative 24-hour trajectories (top {len(selected)} sensors by peak PM2.5, 50 m AGL)")

    cmap = plt.get_cmap("tab20")
    for idx, item in enumerate(selected):
        traj = item["trajectory"]
        color = cmap(idx % 20)
        label = f"{int(item['sensor_index'])} | {item['peak_pm25_atm']:.0f} ug/m3"
        ax.plot(traj["longitude"], traj["latitude"], color=color, linewidth=1.8, alpha=0.95, label=label)
        ax.scatter([traj.iloc[-1]["longitude"]], [traj.iloc[-1]["latitude"]], color=color, s=18)

    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8, framealpha=0.95)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    manifest = load_manifest(args.manifest)
    trajectories = attach_trajectories(manifest)
    if not trajectories:
        raise ValueError("No valid completed trajectories found in the manifest")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    bounds = compute_bounds(trajectories)

    plot_all_spaghetti(trajectories, args.output_dir / "all_trajectories_spaghetti.png", bounds)
    plot_by_height(trajectories, args.output_dir / "trajectories_by_height.png", bounds)
    plot_representative(
        trajectories,
        args.output_dir / "representative_trajectories_50m.png",
        bounds,
        args.sample_count,
    )

    print(f"Loaded {len(trajectories):,} completed trajectories")
    print(f"Saved figures to {args.output_dir}")


if __name__ == "__main__":
    main()
