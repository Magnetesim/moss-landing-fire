#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from moss_landing.paths import set_mpl_cache

set_mpl_cache()

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
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


from moss_landing.constants import MOSS_LANDING_LAT, MOSS_LANDING_LON  # noqa: E402
from moss_landing.hysplit import get_hysplitdata  # noqa: E402
from moss_landing.paths import DATA_DIR, FIGURES_DIR  # noqa: E402

COMPARISON_DIR = FIGURES_DIR / "comparison_sheets"
HYSPLIT_COMPARE_DIR = FIGURES_DIR / "hysplit_compare"

DEFAULT_INPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
DEFAULT_BOUNDARY = DATA_DIR / "monterey_bay_unified_apcd.geojson"
DEFAULT_OUTPUT = COMPARISON_DIR / "purpleair_vs_hysplit_comparison_mode_25m.png"

WINDOW_SPECS = {
    0: {"label": "Window 0\nIgnition to +4 h", "hysplit_prefix": "w16_2300_to_0300"},
    1: {"label": "Window 1\n+4 h to +8 h", "hysplit_prefix": "w17_0300_to_0700"},
    4: {"label": "Window 4\n+16 h to +20 h", "hysplit_prefix": "w17_1500_to_1900"},
    7: {"label": "Window 7\n+28 h to +32 h", "hysplit_prefix": "w18_0300_to_0700"},
    10: {"label": "Window 10\n+40 h to +44 h", "hysplit_prefix": "w18_1500_to_1900"},
}

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a comparison-mode sheet for PurpleAir kriging vs HYSPLIT."
    )
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--boundary-geojson", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--hysplit-dir", type=Path, default=HYSPLIT_COMPARE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--rows", default="1,4,7,10")
    parser.add_argument("--hysplit-height-m", type=int, default=25, choices=(10, 25, 50))
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
    parser.add_argument(
        "--basemap-style",
        choices=("gray", "light", "dark", "none"),
        default="light",
    )
    parser.add_argument("--xlim", default="-122.08,-121.67")
    parser.add_argument("--ylim", default="36.48,37.18")
    parser.add_argument(
        "--purpleair-threshold",
        type=float,
        default=12.0,
        help="Enhancement threshold for the binary impact panel.",
    )
    parser.add_argument(
        "--hysplit-binary-class",
        type=int,
        default=3,
        help="Relative HYSPLIT class threshold for the binary impact panel.",
    )
    parser.add_argument("--dpi", type=int, default=180)
    return parser.parse_args()


def parse_range_arg(value: str | None, label: str) -> tuple[float, float] | None:
    if value is None:
        return None
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"{label} must be formatted as min,max")
    low, high = (float(parts[0]), float(parts[1]))
    if low >= high:
        raise ValueError(f"{label} must have min < max")
    return low, high


def parse_sensor_exclusions(values: list[str]) -> set[int]:
    excluded: set[int] = set()
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if item:
                excluded.add(int(item))
    return excluded


def parse_rows(rows_arg: str) -> list[int]:
    rows = []
    for token in rows_arg.split(","):
        token = token.strip()
        if token:
            rows.append(int(token))
    if not rows:
        raise ValueError("No rows selected.")
    for row in rows:
        if row not in WINDOW_SPECS:
            raise ValueError(f"Unsupported window row: {row}")
    return rows


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
        raise ValueError(f"No rows found for window_index={window_index}")
    frame = frame.loc[frame["baseline_ok"].fillna(False)].copy()
    if excluded_sensors:
        frame = frame.loc[~frame["sensor_index"].isin(excluded_sensors)].copy()
    frame["enhancement_pos_mean"] = frame["enhancement_pos_mean"].fillna(0.0).clip(lower=0.0)
    frame = frame.dropna(subset=["longitude", "latitude"])
    if len(frame) < 8:
        raise ValueError(f"Need at least 8 sensors for kriging; found {len(frame)}")
    return frame


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
    return z_masked, variance_masked, valid_mask


def enhancement_to_class(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, -1, dtype=int)
    finite = np.isfinite(values)
    bins = np.digitize(np.clip(values[finite], ENHANCEMENT_BOUNDS[0], ENHANCEMENT_BOUNDS[-1] - 1e-9), ENHANCEMENT_BOUNDS[1:-1], right=False)
    out[finite] = bins
    return out


def load_hysplit_grid(json_path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, object]]:
    metadata = json.loads(json_path.read_text(encoding="utf-8"))
    cdump_path = Path(metadata["cdump_path"])
    cdump = get_hysplitdata().read_cdump(str(cdump_path))
    grids = [grid for grid in cdump.grids if grid.time_index == int(metadata["time_index"]) and grid.vert_level == int(metadata["level_m_agl"])]
    pollutant = metadata["pollutant"]
    grids = [grid for grid in grids if grid.pollutant == pollutant]
    if not grids:
        raise ValueError(f"No grids found in {cdump_path} matching comparison metadata.")
    combined = np.sum([grid.conc for grid in grids], axis=0)
    return np.asarray(cdump.longitudes), np.asarray(cdump.latitudes), combined, metadata


def interpolate_hysplit_to_grid(
    source_lons: np.ndarray,
    source_lats: np.ndarray,
    source_conc: np.ndarray,
    target_lon_grid: np.ndarray,
    target_lat_grid: np.ndarray,
) -> np.ndarray:
    interpolator = RegularGridInterpolator(
        (source_lats, source_lons),
        source_conc,
        method="linear",
        bounds_error=False,
        fill_value=0.0,
    )
    points = np.column_stack([target_lat_grid.ravel(), target_lon_grid.ravel()])
    values = interpolator(points).reshape(target_lon_grid.shape)
    return np.asarray(values, dtype=float)


def hysplit_to_relative_class(values: np.ndarray, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    out = np.full(values.shape, -1, dtype=int)
    positive = values[np.isfinite(values) & valid_mask & (values > 0)]
    if positive.size == 0:
        return out, np.array([0, 0, 0, 0, 0], dtype=float)
    quantiles = np.quantile(positive, [0.40, 0.70, 0.88, 0.97])
    finite = np.isfinite(values) & valid_mask
    out[finite] = 0
    positive_finite = finite & (values > 0)
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
    out[valid & (np.abs(diff) <= 0)] = 2
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
    title: str,
    source_marker: bool = True,
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
    if source_marker:
        ax.scatter([MOSS_LANDING_LON], [MOSS_LANDING_LAT], marker="x", s=42, c="black", linewidths=1.6, zorder=5)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title(title, fontsize=10, pad=4)


def main() -> None:
    args = parse_args()
    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")
    if xlim is None or ylim is None:
        raise ValueError("Comparison-mode sheet requires explicit --xlim and --ylim.")

    rows = parse_rows(args.rows)
    excluded_sensors = parse_sensor_exclusions(args.exclude_sensor)
    df = pd.read_csv(args.input_csv)
    boundary = load_boundary(args.boundary_geojson)
    lon_grid, lat_grid = build_grid(boundary, args.grid_size)

    class_cmap = ListedColormap(CLASS_COLORS)
    class_norm = BoundaryNorm(np.arange(-0.5, 5.5, 1.0), class_cmap.N)
    agreement_cmap = ListedColormap(AGREEMENT_COLORS)
    agreement_norm = BoundaryNorm(np.arange(-0.5, 5.5, 1.0), agreement_cmap.N)
    binary_cmap = ListedColormap(BINARY_COLORS)
    binary_norm = BoundaryNorm(np.arange(-0.5, 4.5, 1.0), binary_cmap.N)

    fig, axes = plt.subplots(
        len(rows),
        4,
        figsize=(16.5, 4.4 * len(rows) + 1.0),
        dpi=args.dpi,
        squeeze=False,
    )
    fig.patch.set_facecolor("white")
    fig.suptitle("PurpleAir vs HYSPLIT Comparison Mode", fontsize=18, y=0.988)
    fig.text(
        0.5,
        0.969,
        "Rows: 4-hour windows | PurpleAir: kriged enhancement classes | HYSPLIT: relative plume classes within each window",
        ha="center",
        fontsize=10,
    )
    fig.text(
        0.5,
        0.952,
        f"Binary impact threshold: PurpleAir >= {args.purpleair_threshold:g} ug/m3 | HYSPLIT >= relative class {args.hysplit_binary_class}",
        ha="center",
        fontsize=9.5,
    )

    for row_idx, window_index in enumerate(rows):
        frame = pick_window(df, window_index, excluded_sensors)
        kriged, variance_masked, valid_mask = krige_window(
            frame,
            boundary,
            lon_grid,
            lat_grid,
            variogram_model=args.variogram_model,
            distance_mask_km=args.distance_mask_km,
        )
        purple_class = enhancement_to_class(kriged)
        sensor_class = enhancement_to_class(frame["enhancement_pos_mean"].to_numpy())

        prefix = WINDOW_SPECS[window_index]["hysplit_prefix"]
        json_path = args.hysplit_dir / f"{prefix}_h{args.hysplit_height_m:03d}.json"
        h_lons, h_lats, h_conc, metadata = load_hysplit_grid(json_path)
        h_interp = interpolate_hysplit_to_grid(h_lons, h_lats, h_conc, lon_grid, lat_grid)
        h_interp = np.where(valid_mask, h_interp, np.nan)
        h_class, h_quantiles = hysplit_to_relative_class(h_interp, valid_mask)

        agreement = build_agreement_map(purple_class, h_class)
        binary = build_binary_map(kriged, h_class, args.purpleair_threshold, args.hysplit_binary_class)

        label = WINDOW_SPECS[window_index]["label"]
        axes[row_idx][0].set_ylabel(label, fontsize=10.5, rotation=0, labelpad=58, va="center")

        plot_panel(
            axes[row_idx][0],
            lon_grid,
            lat_grid,
            np.where(purple_class >= 0, purple_class, np.nan),
            class_cmap,
            class_norm,
            boundary,
            xlim,
            ylim,
            args.basemap_style,
            title="",
            sensors=frame,
            sensor_classes=sensor_class,
        )
        if row_idx == 0:
            axes[row_idx][0].set_title("PurpleAir enhancement class", fontsize=11, pad=8)
        plot_panel(
            axes[row_idx][1],
            lon_grid,
            lat_grid,
            np.where(h_class >= 0, h_class, np.nan),
            class_cmap,
            class_norm,
            boundary,
            xlim,
            ylim,
            args.basemap_style,
            title="",
        )
        if row_idx == 0:
            axes[row_idx][1].set_title(f"HYSPLIT {args.hysplit_height_m} m relative class", fontsize=11, pad=8)
        plot_panel(
            axes[row_idx][2],
            lon_grid,
            lat_grid,
            np.where(agreement >= 0, agreement, np.nan),
            agreement_cmap,
            agreement_norm,
            boundary,
            xlim,
            ylim,
            args.basemap_style,
            title="",
        )
        if row_idx == 0:
            axes[row_idx][2].set_title("Class agreement", fontsize=11, pad=8)
        plot_panel(
            axes[row_idx][3],
            lon_grid,
            lat_grid,
            np.where(binary >= 0, binary, np.nan),
            binary_cmap,
            binary_norm,
            boundary,
            xlim,
            ylim,
            args.basemap_style,
            title="",
        )
        if row_idx == 0:
            axes[row_idx][3].set_title("Binary impact comparison", fontsize=11, pad=8)

        local_label = str(frame["window_label_local"].iloc[0])
        hysplit_label = pd.Timestamp(metadata["sample_start_utc"]).tz_convert("US/Pacific").strftime("%b %d %I:%M %p PT")
        variance_p90 = float(np.nanpercentile(variance_masked, 90)) if np.isfinite(variance_masked).any() else np.nan
        note = (
            f"{local_label}\n"
            f"HYSPLIT q50/q75/q90/q97: "
            f"{h_quantiles[0]:.1e}, {h_quantiles[1]:.1e}, {h_quantiles[2]:.1e}, {h_quantiles[3]:.1e}\n"
            f"Grid kept {float(np.isfinite(kriged).mean()):.1%} | Var p90 {variance_p90:.1f}"
        )
        axes[row_idx][0].text(
            0.01,
            0.99,
            note,
            transform=axes[row_idx][0].transAxes,
            ha="left",
            va="top",
            fontsize=7.2,
            color="#24323d",
            bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.82, "edgecolor": "#c5ced6"},
            zorder=6,
        )
        axes[row_idx][1].text(
            0.99,
            0.99,
            hysplit_label,
            transform=axes[row_idx][1].transAxes,
            ha="right",
            va="top",
            fontsize=7.6,
            color="#24323d",
            bbox={"boxstyle": "round,pad=0.22", "facecolor": "white", "alpha": 0.82, "edgecolor": "#c5ced6"},
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

    fig.legend(
        handles=class_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.035),
        ncol=5,
        frameon=False,
        title="Shared class palette",
        fontsize=9,
        title_fontsize=9.5,
    )
    fig.legend(
        handles=agreement_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.018),
        ncol=5,
        frameon=False,
        title="Agreement panel",
        fontsize=9,
        title_fontsize=9.5,
    )
    fig.legend(
        handles=binary_handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.001),
        ncol=4,
        frameon=False,
        title="Binary impact panel",
        fontsize=9,
        title_fontsize=9.5,
    )

    plt.tight_layout(rect=[0.04, 0.10, 0.995, 0.94])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Wrote comparison-mode sheet: {args.output}")


if __name__ == "__main__":
    main()
