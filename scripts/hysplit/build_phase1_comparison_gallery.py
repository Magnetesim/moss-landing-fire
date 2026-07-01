#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from PIL import Image
from pykrige.ok import OrdinaryKriging
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

try:
    import contextily as cx
    import xyzservices.providers as xyz
except ImportError:
    cx = None
    xyz = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
DEFAULT_PER_RUN = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "sweeps" / "scoring" / "phase1_matrix_20260622d_manifest_per_run_scores.csv"
DEFAULT_PER_SCENARIO = PROJECT_ROOT / "hysplit" / "runs" / "forward_dispersion" / "sweeps" / "scoring" / "phase1_matrix_20260622d_manifest_scenario_scores.csv"
DEFAULT_PURPLEAIR_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
DEFAULT_BOUNDARY = DATA_DIR / "monterey_bay_unified_apcd.geojson"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "figures" / "visualization" / "phase1_gallery"

HYSPLITDATA_ROOT = PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64" / "python" / "hysplitdata"
if str(HYSPLITDATA_ROOT) not in sys.path:
    sys.path.insert(0, str(HYSPLITDATA_ROOT))
import hysplitdata  # noqa: E402


MOSS_LANDING_LAT = 36.8044
MOSS_LANDING_LON = -121.7883
ENHANCEMENT_BOUNDS = np.array([0.0, 1.0, 5.0, 12.0, 35.0, 80.0], dtype=float)
CLASS_COLORS = ["#2c7bb6", "#00a6ca", "#00cc66", "#f9d057", "#d7191c"]
CLASS_LABELS = ["0-1", "1-5", "5-12", "12-35", "35+"]
AGREEMENT_COLORS = ["#2166ac", "#67a9cf", "#f7f7f7", "#f4a582", "#b2182b"]
AGREEMENT_LABELS = [
    "HYSPLIT << PurpleAir",
    "HYSPLIT < PurpleAir",
    "Near match",
    "HYSPLIT > PurpleAir",
    "HYSPLIT >> PurpleAir",
]
BINARY_COLORS = ["#d9d9d9", "#1a9850", "#fdae61", "#7b3294"]
BINARY_LABELS = ["Neither high", "Both high", "PurpleAir only", "HYSPLIT only"]

WINDOW_LABELS = {
    1: "+4 h to +8 h",
    4: "+16 h to +20 h",
    7: "+28 h to +32 h",
    10: "+40 h to +44 h",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render top-scoring phase-1 PurpleAir vs HYSPLIT comparison sheets and a gallery."
    )
    parser.add_argument("--per-run-csv", type=Path, default=DEFAULT_PER_RUN)
    parser.add_argument("--per-scenario-csv", type=Path, default=DEFAULT_PER_SCENARIO)
    parser.add_argument("--purpleair-csv", type=Path, default=DEFAULT_PURPLEAIR_CSV)
    parser.add_argument("--boundary-geojson", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--top-n", type=int, default=4)
    parser.add_argument("--rows", default="1,4,7,10")
    parser.add_argument("--grid-size", type=int, default=320)
    parser.add_argument("--distance-mask-km", type=float, default=8.0)
    parser.add_argument(
        "--exclude-sensor",
        action="append",
        default=["72253"],
        help="Sensor index to exclude from interpolation. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--variogram-model",
        choices=("linear", "power", "gaussian", "spherical", "exponential"),
        default="exponential",
    )
    parser.add_argument("--purpleair-threshold", type=float, default=12.0)
    parser.add_argument("--hysplit-binary-class", type=int, default=3)
    parser.add_argument("--xlim", default="-122.08,-121.67")
    parser.add_argument("--ylim", default="36.48,37.18")
    parser.add_argument(
        "--basemap-style",
        choices=("gray", "light", "dark", "none"),
        default="none",
    )
    parser.add_argument("--dpi", type=int, default=180)
    return parser.parse_args()


def parse_rows(raw: str) -> list[int]:
    rows = [int(token.strip()) for token in raw.split(",") if token.strip()]
    if not rows:
        raise ValueError("No rows selected")
    return rows


def parse_sensor_exclusions(values: list[str]) -> set[int]:
    excluded: set[int] = set()
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if item:
                excluded.add(int(item))
    return excluded


def parse_range_arg(value: str, label: str) -> tuple[float, float]:
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"{label} must be formatted as min,max")
    low, high = (float(parts[0]), float(parts[1]))
    if low >= high:
        raise ValueError(f"{label} must have min < max")
    return low, high


def load_boundary(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    geometries = [shape(feature["geometry"]) for feature in payload.get("features", [])]
    if not geometries:
        raise ValueError(f"No geometries found in {path}")
    return unary_union(geometries)


def build_grid(boundary, grid_size: int) -> tuple[np.ndarray, np.ndarray]:
    min_lon, min_lat, max_lon, max_lat = boundary.bounds
    span_lon = max_lon - min_lon
    span_lat = max_lat - min_lat
    if span_lon >= span_lat:
        nx = grid_size
        ny = max(60, int(round(grid_size * span_lat / span_lon)))
    else:
        ny = grid_size
        nx = max(60, int(round(grid_size * span_lon / span_lat)))
    lon_vals = np.linspace(min_lon, max_lon, nx)
    lat_vals = np.linspace(min_lat, max_lat, ny)
    return np.meshgrid(lon_vals, lat_vals)


def lonlat_to_km(lons: np.ndarray, lats: np.ndarray, lon0: float, lat0: float) -> tuple[np.ndarray, np.ndarray]:
    x = (lons - lon0) * 111.320 * np.cos(np.deg2rad(lat0))
    y = (lats - lat0) * 110.574
    return x, y


def build_mask(
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    boundary,
    sensor_lons: np.ndarray,
    sensor_lats: np.ndarray,
    distance_mask_km: float,
) -> tuple[np.ndarray, np.ndarray]:
    prepared = prep(boundary)
    flat_lon = lon_grid.ravel()
    flat_lat = lat_grid.ravel()
    inside = np.array([prepared.contains(Point(lon, lat)) for lon, lat in zip(flat_lon, flat_lat)], dtype=bool)

    lon0 = float(np.mean(sensor_lons))
    lat0 = float(np.mean(sensor_lats))
    sensor_x, sensor_y = lonlat_to_km(sensor_lons, sensor_lats, lon0, lat0)
    grid_x, grid_y = lonlat_to_km(flat_lon, flat_lat, lon0, lat0)
    tree = cKDTree(np.column_stack([sensor_x, sensor_y]))
    nearest_km, _ = tree.query(np.column_stack([grid_x, grid_y]), k=1)
    valid = inside & (nearest_km <= distance_mask_km)
    return valid.reshape(lon_grid.shape), nearest_km.reshape(lon_grid.shape)


def pick_window(df: pd.DataFrame, window_index: int, excluded_sensors: set[int]) -> pd.DataFrame:
    frame = df.loc[df["window_index"] == window_index].copy()
    if frame.empty:
        raise ValueError(f"No PurpleAir rows found for window_index={window_index}")
    frame = frame.loc[frame["baseline_ok"].fillna(False)].copy()
    if excluded_sensors:
        frame = frame.loc[~frame["sensor_index"].isin(excluded_sensors)].copy()
    frame["enhancement_pos_mean"] = frame["enhancement_pos_mean"].fillna(0.0).clip(lower=0.0)
    frame = frame.dropna(subset=["longitude", "latitude"])
    if len(frame) < 8:
        raise ValueError(f"Need at least 8 sensors for kriging; found {len(frame)}")
    return frame


def krige_window(
    frame: pd.DataFrame,
    boundary,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    variogram_model: str,
    distance_mask_km: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    valid_mask, nearest_km = build_mask(
        lon_grid,
        lat_grid,
        boundary,
        frame["longitude"].to_numpy(),
        frame["latitude"].to_numpy(),
        distance_mask_km,
    )
    ok = OrdinaryKriging(
        frame["longitude"].to_numpy(),
        frame["latitude"].to_numpy(),
        frame["enhancement_pos_mean"].to_numpy(),
        variogram_model=variogram_model,
        coordinates_type="geographic",
        enable_plotting=False,
        verbose=False,
    )
    z_grid, variance_grid = ok.execute("grid", lon_grid[0, :], lat_grid[:, 0])
    z_grid = np.asarray(z_grid, dtype=float)
    variance_grid = np.asarray(variance_grid, dtype=float)
    z_grid = np.clip(z_grid, 0.0, ENHANCEMENT_BOUNDS[-1])
    z_masked = np.where(valid_mask, z_grid, np.nan)
    variance_masked = np.where(valid_mask, variance_grid, np.nan)
    return z_masked, variance_masked, nearest_km


def enhancement_to_class(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, -1, dtype=int)
    finite = np.isfinite(values)
    clipped = np.clip(values[finite], ENHANCEMENT_BOUNDS[0], ENHANCEMENT_BOUNDS[-1] - 1e-9)
    out[finite] = np.digitize(clipped, ENHANCEMENT_BOUNDS[1:-1], right=False)
    return out


def load_hysplit_conc(cdump_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cdump = hysplitdata.read_cdump(str(cdump_path))
    time_indices = sorted({grid.time_index for grid in cdump.grids})
    if not time_indices:
        raise ValueError(f"No grids found in cdump: {cdump_path}")
    time_index = time_indices[-1]
    pollutant = cdump.pollutants[0]
    level = next(grid.vert_level for grid in cdump.grids if grid.time_index == time_index and grid.pollutant == pollutant)
    grids = [grid for grid in cdump.grids if grid.time_index == time_index and grid.pollutant == pollutant and grid.vert_level == level]
    conc = np.sum([grid.conc for grid in grids], axis=0)
    return np.asarray(cdump.longitudes), np.asarray(cdump.latitudes), np.asarray(conc, dtype=float)


def interpolate_field_to_points(
    source_lons: np.ndarray,
    source_lats: np.ndarray,
    source_values: np.ndarray,
    target_lons: np.ndarray,
    target_lats: np.ndarray,
) -> np.ndarray:
    interpolator = RegularGridInterpolator(
        (source_lats, source_lons),
        source_values,
        method="linear",
        bounds_error=False,
        fill_value=0.0,
    )
    target_shape = np.shape(target_lons)
    points = np.column_stack([np.asarray(target_lats).ravel(), np.asarray(target_lons).ravel()])
    values = np.asarray(interpolator(points), dtype=float)
    return values.reshape(target_shape)


def hysplit_to_relative_class(values: np.ndarray, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out = np.full(values.shape, -1, dtype=int)
    positive = values[np.isfinite(values) & valid_mask & (values > 0)]
    if positive.size == 0:
        return out, np.array([0.0, 0.0, 0.0, 0.0], dtype=float)
    quantiles = np.quantile(positive, [0.40, 0.70, 0.88, 0.97])
    finite = np.isfinite(values) & valid_mask
    positive_finite = finite & (values > 0)
    out[finite] = 0
    out[positive_finite] = 1
    out[finite & (values >= quantiles[0])] = 2
    out[finite & (values >= quantiles[1])] = 3
    out[finite & (values >= quantiles[2])] = 4
    return out, quantiles


def build_agreement_map(purple_class: np.ndarray, hysplit_class: np.ndarray) -> np.ndarray:
    out = np.full(purple_class.shape, -1, dtype=int)
    valid = (purple_class >= 0) & (hysplit_class >= 0)
    valid &= ~((purple_class == 0) & (hysplit_class == 0))
    diff = hysplit_class - purple_class
    out[valid] = 2
    out[valid & (diff <= -2)] = 0
    out[valid & (diff == -1)] = 1
    out[valid & (diff == 1)] = 3
    out[valid & (diff >= 2)] = 4
    return out


def build_binary_map(
    purple_values: np.ndarray,
    hysplit_class: np.ndarray,
    purple_threshold: float,
    hysplit_binary_class: int,
) -> np.ndarray:
    out = np.full(purple_values.shape, -1, dtype=int)
    valid = np.isfinite(purple_values) & (hysplit_class >= 0)
    purple_hit = purple_values >= purple_threshold
    hysplit_hit = hysplit_class >= hysplit_binary_class
    out[valid] = 0
    out[valid & purple_hit & hysplit_hit] = 1
    out[valid & purple_hit & ~hysplit_hit] = 2
    out[valid & ~purple_hit & hysplit_hit] = 3
    return out


def resolve_basemap_provider(style: str):
    if xyz is None:
        return None
    providers = {
        "gray": xyz.Esri.WorldGrayCanvas,
        "light": xyz.CartoDB.Positron,
        "dark": xyz.CartoDB.DarkMatter,
    }
    return providers.get(style)


def add_basemap_if_available(ax: plt.Axes, style: str) -> None:
    if cx is None or style == "none":
        return
    provider = resolve_basemap_provider(style)
    if provider is None:
        return
    try:
        cx.add_basemap(ax, crs="EPSG:4326", source=provider, attribution=False, zoom="auto")
    except Exception:
        return


def plot_panel(
    ax: plt.Axes,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    raster: np.ndarray,
    cmap: ListedColormap,
    norm: BoundaryNorm,
    boundary,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    basemap_style: str,
    sensors: pd.DataFrame | None = None,
    sensor_classes: np.ndarray | None = None,
) -> None:
    ax.set_facecolor("#eef4f8")
    add_basemap_if_available(ax, basemap_style)
    masked = np.ma.masked_where(~np.isfinite(raster), raster)
    ax.pcolormesh(lon_grid, lat_grid, masked, cmap=cmap, norm=norm, shading="auto", alpha=0.72, zorder=1)
    bx, by = boundary.exterior.xy
    ax.plot(bx, by, color="#13d8ff", linewidth=1.25, alpha=0.95, zorder=3)
    if sensors is not None and sensor_classes is not None:
        sensor_colors = [CLASS_COLORS[idx] for idx in sensor_classes]
        ax.scatter(
            sensors["longitude"],
            sensors["latitude"],
            s=13,
            c=sensor_colors,
            edgecolors="#1c1c1c",
            linewidths=0.3,
            alpha=0.95,
            zorder=4,
        )
    ax.scatter([MOSS_LANDING_LON], [MOSS_LANDING_LAT], marker="x", s=42, c="black", linewidths=1.6, zorder=5)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])


def slugify_scenario_id(value: str) -> str:
    return value.replace("scenario_tag=", "").replace("|", "__").replace("=", "-").replace(",", "x")


def select_scenarios(per_scenario: pd.DataFrame, requested: list[str], top_n: int) -> list[str]:
    if requested:
        return requested
    return per_scenario.sort_values("mean_total_score", ascending=False)["scenario_id"].head(top_n).tolist()


def render_sheet(
    scenario_id: str,
    scenario_summary: pd.Series,
    scenario_runs: pd.DataFrame,
    purple_windows: dict[int, dict[str, object]],
    boundary,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    xlim: tuple[float, float],
    ylim: tuple[float, float],
    args: argparse.Namespace,
    output_path: Path,
) -> None:
    class_cmap = ListedColormap(CLASS_COLORS)
    class_norm = BoundaryNorm(np.arange(-0.5, 5.5, 1.0), class_cmap.N)
    agreement_cmap = ListedColormap(AGREEMENT_COLORS)
    agreement_norm = BoundaryNorm(np.arange(-0.5, 5.5, 1.0), agreement_cmap.N)
    binary_cmap = ListedColormap(BINARY_COLORS)
    binary_norm = BoundaryNorm(np.arange(-0.5, 4.5, 1.0), binary_cmap.N)

    rows = scenario_runs["window_index"].tolist()
    fig, axes = plt.subplots(
        len(rows),
        4,
        figsize=(16.5, 4.4 * len(rows) + 1.25),
        dpi=args.dpi,
        squeeze=False,
    )
    fig.patch.set_facecolor("white")
    title = (
        f"{scenario_id.replace('scenario_tag=', '')} | "
        f"score {float(scenario_summary['mean_total_score']):.3f} | "
        f"F1 {float(scenario_summary['mean_sensor_f1']):.3f} | "
        f"IoU {float(scenario_summary['mean_grid_iou']):.3f} | "
        f"class {float(scenario_summary['mean_class_score']):.3f}"
    )
    fig.suptitle(title, fontsize=16, y=0.988)
    fig.text(
        0.5,
        0.968,
        "Rows: 4-hour windows | PurpleAir: kriged enhancement classes | HYSPLIT: relative plume classes within each window",
        ha="center",
        fontsize=10,
    )

    for row_idx, (_, run) in enumerate(scenario_runs.iterrows()):
        window_index = int(run["window_index"])
        window_data = purple_windows[window_index]
        frame = window_data["frame"]
        purple_class = window_data["class"]
        sensor_class = window_data["sensor_class"]
        variance_masked = window_data["variance"]
        nearest_km = window_data["nearest_km"]
        valid_mask = window_data["valid_mask"]

        cdump_path = Path(run["run_dir"]) / "cdump"
        h_lons, h_lats, h_conc = load_hysplit_conc(cdump_path)
        h_grid = interpolate_field_to_points(h_lons, h_lats, h_conc, lon_grid, lat_grid)
        h_grid = np.where(valid_mask, h_grid, np.nan)
        h_class, h_quantiles = hysplit_to_relative_class(h_grid, valid_mask)
        agreement = build_agreement_map(purple_class, h_class)
        binary = build_binary_map(window_data["kriged"], h_class, args.purpleair_threshold, args.hysplit_binary_class)

        axes[row_idx][0].set_ylabel(
            f"Window {window_index}\n{WINDOW_LABELS.get(window_index, '')}",
            fontsize=10.5,
            rotation=0,
            labelpad=58,
            va="center",
        )
        plot_panel(axes[row_idx][0], lon_grid, lat_grid, np.where(purple_class >= 0, purple_class, np.nan), class_cmap, class_norm, boundary, xlim, ylim, args.basemap_style, sensors=frame, sensor_classes=sensor_class)
        plot_panel(axes[row_idx][1], lon_grid, lat_grid, np.where(h_class >= 0, h_class, np.nan), class_cmap, class_norm, boundary, xlim, ylim, args.basemap_style)
        plot_panel(axes[row_idx][2], lon_grid, lat_grid, np.where(agreement >= 0, agreement, np.nan), agreement_cmap, agreement_norm, boundary, xlim, ylim, args.basemap_style)
        plot_panel(axes[row_idx][3], lon_grid, lat_grid, np.where(binary >= 0, binary, np.nan), binary_cmap, binary_norm, boundary, xlim, ylim, args.basemap_style)

        if row_idx == 0:
            axes[row_idx][0].set_title("PurpleAir enhancement class", fontsize=11, pad=8)
            axes[row_idx][1].set_title("HYSPLIT relative class", fontsize=11, pad=8)
            axes[row_idx][2].set_title("Class agreement", fontsize=11, pad=8)
            axes[row_idx][3].set_title("Binary impact comparison", fontsize=11, pad=8)

        local_label = str(frame["window_label_local"].iloc[0])
        variance_p90 = float(np.nanpercentile(variance_masked, 90)) if np.isfinite(variance_masked).any() else np.nan
        kept_fraction = float(np.isfinite(window_data["kriged"]).mean())
        note = (
            f"{local_label}\n"
            f"run score {float(run['total_score']):.3f} | sensor F1 {float(run['sensor_f1']):.3f}\n"
            f"IoU {float(run['grid_iou']):.3f} | class {float(run['class_score']):.3f} | d {float(run['mean_distance_km']):.1f} km\n"
            f"grid kept {kept_fraction:.1%} | var p90 {variance_p90:.2f} | mask p90 {float(np.nanpercentile(nearest_km[np.isfinite(window_data['kriged'])], 90)):.1f} km"
        )
        axes[row_idx][0].text(
            0.01,
            0.99,
            note,
            transform=axes[row_idx][0].transAxes,
            ha="left",
            va="top",
            fontsize=7.0,
            color="#24323d",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.84, "edgecolor": "#c5ced6"},
            zorder=6,
        )
        axes[row_idx][1].text(
            0.99,
            0.99,
            f"q40 {h_quantiles[0]:.1e}\nq70 {h_quantiles[1]:.1e}\nq88 {h_quantiles[2]:.1e}\nq97 {h_quantiles[3]:.1e}",
            transform=axes[row_idx][1].transAxes,
            ha="right",
            va="top",
            fontsize=7.2,
            color="#24323d",
            bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "alpha": 0.84, "edgecolor": "#c5ced6"},
            zorder=6,
        )

    class_handles = [
        Line2D([0], [0], marker="s", linestyle="None", markersize=9, markerfacecolor=color, markeredgecolor="none", label=label)
        for color, label in zip(CLASS_COLORS, CLASS_LABELS)
    ]
    agreement_handles = [
        Line2D([0], [0], marker="s", linestyle="None", markersize=9, markerfacecolor=color, markeredgecolor="none", label=label)
        for color, label in zip(AGREEMENT_COLORS, AGREEMENT_LABELS)
    ]
    binary_handles = [
        Line2D([0], [0], marker="s", linestyle="None", markersize=9, markerfacecolor=color, markeredgecolor="none", label=label)
        for color, label in zip(BINARY_COLORS, BINARY_LABELS)
    ]
    fig.legend(handles=class_handles, loc="lower center", bbox_to_anchor=(0.5, 0.035), ncol=5, frameon=False, title="Shared class palette", fontsize=9, title_fontsize=9.5)
    fig.legend(handles=agreement_handles, loc="lower center", bbox_to_anchor=(0.5, 0.018), ncol=5, frameon=False, title="Agreement panel", fontsize=9, title_fontsize=9.5)
    fig.legend(handles=binary_handles, loc="lower center", bbox_to_anchor=(0.5, 0.001), ncol=4, frameon=False, title="Binary impact panel", fontsize=9, title_fontsize=9.5)

    plt.tight_layout(rect=[0.04, 0.10, 0.995, 0.94])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_gallery(sheet_paths: list[Path], per_scenario: pd.DataFrame, output_path: Path) -> None:
    if not sheet_paths:
        return
    images = [Image.open(path).convert("RGB") for path in sheet_paths]
    try:
        thumb_w = 1050
        thumbs = []
        labels = []
        for path, image in zip(sheet_paths, images):
            scale = thumb_w / image.width
            thumb_h = int(round(image.height * scale))
            thumbs.append(image.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS))
            scenario_id = path.stem.replace("sheet_", "")
            row = per_scenario.loc[per_scenario["scenario_id_slug"] == scenario_id].iloc[0]
            labels.append(
                f"{row['scenario_id'].replace('scenario_tag=', '')}\n"
                f"score {float(row['mean_total_score']):.3f} | F1 {float(row['mean_sensor_f1']):.3f} | IoU {float(row['mean_grid_iou']):.3f}"
            )

        cols = 2 if len(thumbs) > 1 else 1
        rows = int(math.ceil(len(thumbs) / cols))
        pad = 32
        label_h = 70
        cell_w = thumb_w
        cell_h = max(img.height for img in thumbs) + label_h
        canvas = Image.new("RGB", (cols * cell_w + (cols + 1) * pad, rows * cell_h + (rows + 1) * pad), "white")

        fig = plt.figure(figsize=(canvas.width / 180, canvas.height / 180), dpi=180)
        plt.axis("off")
        plt.close(fig)

        # Use matplotlib text rendering onto a temporary sheet for consistent typography.
        gallery_fig, gallery_axes = plt.subplots(rows, cols, figsize=(canvas.width / 180, canvas.height / 180), dpi=180, squeeze=False)
        gallery_fig.patch.set_facecolor("white")
        gallery_fig.suptitle("Top phase-1 scenarios", fontsize=18, y=0.995)
        for ax in gallery_axes.ravel():
            ax.axis("off")
        for idx, (thumb, label) in enumerate(zip(thumbs, labels)):
            r = idx // cols
            c = idx % cols
            gallery_axes[r][c].imshow(thumb)
            gallery_axes[r][c].set_title(label, fontsize=10, pad=8)
        plt.tight_layout(rect=[0.01, 0.01, 0.99, 0.97])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        gallery_fig.savefig(output_path, bbox_inches="tight", facecolor="white")
        plt.close(gallery_fig)
    finally:
        for image in images:
            image.close()


def main() -> None:
    args = parse_args()
    rows = parse_rows(args.rows)
    excluded_sensors = parse_sensor_exclusions(args.exclude_sensor)
    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")

    per_run = pd.read_csv(args.per_run_csv)
    per_scenario = pd.read_csv(args.per_scenario_csv)
    purpleair = pd.read_csv(args.purpleair_csv)
    boundary = load_boundary(args.boundary_geojson)
    lon_grid, lat_grid = build_grid(boundary, args.grid_size)
    grid_view = (
        (lon_grid >= xlim[0]) & (lon_grid <= xlim[1]) &
        (lat_grid >= ylim[0]) & (lat_grid <= ylim[1])
    )

    purple_windows: dict[int, dict[str, object]] = {}
    for window_index in rows:
        frame = pick_window(purpleair, window_index, excluded_sensors)
        kriged, variance_masked, nearest_km = krige_window(
            frame,
            boundary,
            lon_grid,
            lat_grid,
            variogram_model=args.variogram_model,
            distance_mask_km=args.distance_mask_km,
        )
        kriged = np.where(grid_view, kriged, np.nan)
        variance_masked = np.where(grid_view, variance_masked, np.nan)
        valid_mask = np.isfinite(kriged)
        purple_windows[window_index] = {
            "frame": frame,
            "kriged": kriged,
            "variance": variance_masked,
            "nearest_km": nearest_km,
            "valid_mask": valid_mask,
            "class": enhancement_to_class(kriged),
            "sensor_class": enhancement_to_class(frame["enhancement_pos_mean"].to_numpy()),
        }

    selected = select_scenarios(per_scenario, args.scenario_id, args.top_n)
    per_scenario["scenario_id_slug"] = per_scenario["scenario_id"].map(slugify_scenario_id)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered_paths: list[Path] = []
    for scenario_id in selected:
        scenario_runs = per_run.loc[per_run["scenario_id"] == scenario_id].copy()
        scenario_runs = scenario_runs.loc[scenario_runs["window_index"].isin(rows)].sort_values("window_index")
        if scenario_runs.empty:
            continue
        summary = per_scenario.loc[per_scenario["scenario_id"] == scenario_id]
        if summary.empty:
            continue
        output_path = output_dir / f"sheet_{slugify_scenario_id(scenario_id)}.png"
        render_sheet(scenario_id, summary.iloc[0], scenario_runs, purple_windows, boundary, lon_grid, lat_grid, xlim, ylim, args, output_path)
        rendered_paths.append(output_path)
        print(f"Wrote sheet: {output_path}")

    ranking_path = output_dir / "top_scenarios.csv"
    per_scenario.sort_values("mean_total_score", ascending=False).head(max(args.top_n, len(rendered_paths))).to_csv(ranking_path, index=False)
    print(f"Wrote ranking table: {ranking_path}")

    gallery_path = output_dir / "top_scenarios_gallery.png"
    build_gallery(rendered_paths, per_scenario, gallery_path)
    if rendered_paths:
        print(f"Wrote gallery: {gallery_path}")


if __name__ == "__main__":
    main()
