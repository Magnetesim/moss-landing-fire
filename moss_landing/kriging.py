"""Shared kriging, masking, and map-view helpers for enhancement products.

Extracted from scripts/purple_air/krige_enhancement.py and
animate_krige_enhancement.py, which previously copy-pasted these between
themselves and the HYSPLIT comparison scripts.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from pykrige.ok import OrdinaryKriging
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

from moss_landing.constants import ENHANCEMENT_BOUNDS

try:
    import contextily as cx
    import xyzservices.providers as xyz
except ImportError:
    cx = None
    xyz = None


def parse_sensor_exclusions(values: list[str]) -> set[int]:
    excluded: set[int] = set()
    for value in values:
        for part in value.split(","):
            item = part.strip()
            if item:
                excluded.add(int(item))
    return excluded


def resolve_basemap_provider(style: str):
    if xyz is None:
        return None
    providers = {
        "satellite": xyz.Esri.WorldImagery,
        "gray": xyz.Esri.WorldGrayCanvas,
        "light": xyz.CartoDB.Positron,
        "dark": xyz.CartoDB.DarkMatter,
    }
    return providers.get(style)


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


def adjust_view_bounds(
    xlim: tuple[float, float] | None,
    ylim: tuple[float, float] | None,
    fallback_bounds: tuple[float, float, float, float],
    figure_size: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = fallback_bounds
    x0, x1 = xlim if xlim is not None else (min_lon, max_lon)
    y0, y1 = ylim if ylim is not None else (min_lat, max_lat)

    center_lon = 0.5 * (x0 + x1)
    center_lat = 0.5 * (y0 + y1)
    lon_span = x1 - x0
    lat_span = y1 - y0

    # Preserve approximate local map geometry in lon/lat space by comparing
    # physical width and height at the view center latitude.
    cos_lat = max(0.2, float(np.cos(np.deg2rad(center_lat))))
    width_km = lon_span * 111.320 * cos_lat
    height_km = lat_span * 110.574
    target_ratio = figure_size[0] / figure_size[1]
    current_ratio = width_km / height_km if height_km > 0 else target_ratio

    if current_ratio > target_ratio:
        needed_height_km = width_km / target_ratio
        lat_span = needed_height_km / 110.574
    else:
        needed_width_km = height_km * target_ratio
        lon_span = needed_width_km / (111.320 * cos_lat)

    return (
        (center_lon - 0.5 * lon_span, center_lon + 0.5 * lon_span),
        (center_lat - 0.5 * lat_span, center_lat + 0.5 * lat_span),
    )


def load_boundary(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    geometries = [shape(feature["geometry"]) for feature in payload.get("features", [])]
    if not geometries:
        raise ValueError(f"No geometries found in {path}")
    return unary_union(geometries)


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


def pick_window(
    df: pd.DataFrame,
    window_index: int,
    value_column: str,
    excluded_sensors: set[int],
) -> pd.DataFrame:
    frame = df.loc[df["window_index"] == window_index].copy()
    if frame.empty:
        raise ValueError(f"No rows found for window_index={window_index}")
    frame = frame.loc[frame["baseline_ok"].fillna(False)].copy()
    if excluded_sensors:
        frame = frame.loc[~frame["sensor_index"].isin(excluded_sensors)].copy()
    frame[value_column] = frame[value_column].fillna(0.0).clip(lower=0.0)
    frame = frame.dropna(subset=["longitude", "latitude"])
    if len(frame) < 8:
        raise ValueError(f"Need at least 8 sensors for kriging; found {len(frame)}")
    return frame


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


def krige_frame(
    frame: pd.DataFrame,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    boundary,
    distance_mask_km: float,
    value_column: str,
    variogram_model: str,
) -> tuple[np.ndarray, np.ndarray, float]:
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
        frame[value_column].to_numpy(),
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
    variance_p90 = float(np.nanpercentile(variance_masked, 90)) if np.isfinite(variance_masked).any() else np.nan
    return z_masked, valid_mask, variance_p90
