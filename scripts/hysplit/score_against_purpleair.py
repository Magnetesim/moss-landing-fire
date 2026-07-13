#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

from moss_landing.paths import set_mpl_cache

set_mpl_cache()

import numpy as np
import pandas as pd
from pykrige.ok import OrdinaryKriging
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep


from moss_landing.constants import ENHANCEMENT_BOUNDS as ENHANCEMENT_BOUNDS_LIST  # noqa: E402
from moss_landing.hysplit import import_hysplitdata  # noqa: E402
from moss_landing.paths import DATA_DIR, PROJECT_ROOT  # noqa: E402

hysplitdata = import_hysplitdata()

DEFAULT_PURPLEAIR_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
DEFAULT_BOUNDARY = DATA_DIR / "monterey_bay_unified_apcd.geojson"
DEFAULT_MANIFEST = (
    PROJECT_ROOT
    / "hysplit"
    / "runs"
    / "forward_dispersion"
    / "sweeps"
    / "krige_compare_scw_h10_25_50_manifest.csv"
)

ENHANCEMENT_BOUNDS = np.array(ENHANCEMENT_BOUNDS_LIST, dtype=float)
DEFAULT_ROWS = "1,4,7,10"
DEFAULT_XLIM = "-122.08,-121.67"
DEFAULT_YLIM = "36.48,37.18"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score HYSPLIT forward dispersion runs against PurpleAir 4-hour enhancement windows."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--purpleair-csv", type=Path, default=DEFAULT_PURPLEAIR_CSV)
    parser.add_argument("--boundary-geojson", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--rows", default=DEFAULT_ROWS, help="Comma-separated PurpleAir window indices to score.")
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
    parser.add_argument("--xlim", default=DEFAULT_XLIM)
    parser.add_argument("--ylim", default=DEFAULT_YLIM)
    parser.add_argument(
        "--scenario-columns",
        default="source_height_m,source_geometry,source_footprint_m,source_grid_shape,source_rotation_deg,emission_hours,emission_rate",
        help="Comma-separated manifest columns used to group windows into scenarios.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def parse_range_arg(value: str, label: str) -> tuple[float, float]:
    parts = [item.strip() for item in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"{label} must be formatted as min,max")
    low, high = (float(parts[0]), float(parts[1]))
    if low >= high:
        raise ValueError(f"{label} must have min < max")
    return low, high


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


def parse_scenario_columns(raw: str) -> list[str]:
    columns = [item.strip() for item in raw.split(",") if item.strip()]
    if not columns:
        raise ValueError("No scenario columns configured")
    return columns


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
) -> tuple[np.ndarray, np.ndarray]:
    valid_mask, _ = build_mask(
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
    z_grid, _ = ok.execute("grid", lon_grid[0, :], lat_grid[:, 0])
    z_grid = np.asarray(z_grid, dtype=float)
    z_grid = np.clip(z_grid, 0.0, ENHANCEMENT_BOUNDS[-1])
    return np.where(valid_mask, z_grid, np.nan), valid_mask


def enhancement_to_class(values: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, -1, dtype=int)
    finite = np.isfinite(values)
    clipped = np.clip(values[finite], ENHANCEMENT_BOUNDS[0], ENHANCEMENT_BOUNDS[-1] - 1e-9)
    out[finite] = np.digitize(clipped, ENHANCEMENT_BOUNDS[1:-1], right=False)
    return out


def as_utc_timestamp(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def select_time_index(
    cdump: object,
    sample_start_utc: object | None = None,
    sample_stop_utc: object | None = None,
) -> int:
    periods: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for grid in cdump.grids:
        if grid.time_index not in periods:
            periods[grid.time_index] = (
                as_utc_timestamp(grid.starting_datetime),
                as_utc_timestamp(grid.ending_datetime),
            )
    if not periods:
        raise ValueError("No concentration periods found in cdump")

    if sample_start_utc is None and sample_stop_utc is None:
        return max(periods)
    if sample_start_utc is None or sample_stop_utc is None:
        raise ValueError("Both sample_start_utc and sample_stop_utc are required for period selection")

    target_start = as_utc_timestamp(sample_start_utc)
    target_stop = as_utc_timestamp(sample_stop_utc)
    for time_index, (period_start, period_stop) in periods.items():
        if period_start == target_start and period_stop == target_stop:
            return time_index

    available = ", ".join(
        f"{start.isoformat()} to {stop.isoformat()}"
        for _, (start, stop) in sorted(periods.items())
    )
    raise ValueError(
        "No HYSPLIT concentration period exactly matched "
        f"{target_start.isoformat()} to {target_stop.isoformat()}. "
        f"Available periods: {available}"
    )


def load_hysplit_conc(
    cdump_path: Path,
    sample_start_utc: object | None = None,
    sample_stop_utc: object | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cdump = hysplitdata.read_cdump(str(cdump_path))
    try:
        time_index = select_time_index(cdump, sample_start_utc, sample_stop_utc)
    except ValueError as exc:
        raise ValueError(f"{exc}: {cdump_path}") from exc
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


def confusion_counts(observed: np.ndarray, modeled: np.ndarray) -> tuple[int, int, int, int]:
    tp = int(np.sum(observed & modeled))
    fn = int(np.sum(observed & ~modeled))
    fp = int(np.sum(~observed & modeled))
    tn = int(np.sum(~observed & ~modeled))
    return tp, fn, fp, tn


def f1_score(tp: int, fn: int, fp: int) -> float:
    denom = 2 * tp + fn + fp
    return float((2 * tp) / denom) if denom > 0 else 0.0


def iou_score(observed: np.ndarray, modeled: np.ndarray) -> float:
    union = np.sum(observed | modeled)
    if union == 0:
        return 1.0
    return float(np.sum(observed & modeled) / union)


def class_agreement_score(purple_class: np.ndarray, hysplit_class: np.ndarray) -> float:
    valid = (purple_class >= 0) & (hysplit_class >= 0)
    valid &= ~((purple_class == 0) & (hysplit_class == 0))
    if not np.any(valid):
        return 0.0
    error = np.abs(purple_class[valid] - hysplit_class[valid]) / 4.0
    return float(np.clip(1.0 - error.mean(), 0.0, 1.0))


def distance_score(
    sensor_lons: np.ndarray,
    sensor_lats: np.ndarray,
    observed_hit: np.ndarray,
    lon_grid: np.ndarray,
    lat_grid: np.ndarray,
    modeled_hit_grid: np.ndarray,
    max_distance_km: float,
) -> tuple[float, float]:
    impacted_idx = np.where(observed_hit)[0]
    if impacted_idx.size == 0:
        return 1.0, 0.0
    target_cells = modeled_hit_grid & np.isfinite(lon_grid) & np.isfinite(lat_grid)
    if not np.any(target_cells):
        return 0.0, float(max_distance_km)
    target_lon = lon_grid[target_cells]
    target_lat = lat_grid[target_cells]
    ref_lat = float(np.mean(sensor_lats))
    ref_lon = float(np.mean(sensor_lons))
    sensor_x, sensor_y = lonlat_to_km(sensor_lons[impacted_idx], sensor_lats[impacted_idx], ref_lon, ref_lat)
    target_x, target_y = lonlat_to_km(target_lon, target_lat, ref_lon, ref_lat)
    tree = cKDTree(np.column_stack([target_x, target_y]))
    distances, _ = tree.query(np.column_stack([sensor_x, sensor_y]), k=1)
    mean_distance = float(np.mean(distances))
    score = float(np.clip(1.0 - (mean_distance / max_distance_km), 0.0, 1.0))
    return score, mean_distance


def build_window_lookup(df: pd.DataFrame) -> dict[tuple[pd.Timestamp, pd.Timestamp], int]:
    lookup: dict[tuple[pd.Timestamp, pd.Timestamp], int] = {}
    for row in df[["window_index", "window_start_utc", "window_stop_utc"]].drop_duplicates().itertuples(index=False):
        start_key = as_utc_timestamp(row.window_start_utc)
        stop_key = as_utc_timestamp(row.window_stop_utc)
        lookup[(start_key, stop_key)] = int(row.window_index)
    return lookup


def build_window_interval_lookup(df: pd.DataFrame) -> dict[int, tuple[pd.Timestamp, pd.Timestamp]]:
    lookup: dict[int, tuple[pd.Timestamp, pd.Timestamp]] = {}
    for row in df[["window_index", "window_start_utc", "window_stop_utc"]].drop_duplicates().itertuples(index=False):
        window_index = int(row.window_index)
        interval = (
            as_utc_timestamp(row.window_start_utc),
            as_utc_timestamp(row.window_stop_utc),
        )
        previous = lookup.get(window_index)
        if previous is not None and previous != interval:
            raise ValueError(f"PurpleAir window {window_index} has inconsistent timestamps")
        lookup[window_index] = interval
    return lookup


def manifest_window_indices(
    row: pd.Series,
    window_lookup: dict[tuple[pd.Timestamp, pd.Timestamp], int],
) -> list[int]:
    for field in ("logical_window_indices", "window_indices"):
        raw = row.get(field)
        if raw is not None and not pd.isna(raw) and str(raw).strip():
            values = [int(piece.strip()) for piece in str(raw).split(",") if piece.strip()]
            if values:
                return values

    start_key = as_utc_timestamp(row["sample_start_utc"])
    stop_key = as_utc_timestamp(row["sample_stop_utc"])
    window_index = window_lookup.get((start_key, stop_key))
    return [] if window_index is None else [window_index]


def scenario_key(row: pd.Series, scenario_columns: list[str]) -> str:
    parts = [f"{column}={row[column]}" for column in scenario_columns]
    return "|".join(parts)


def prepare_manifest_for_scoring(manifest: pd.DataFrame) -> pd.DataFrame:
    """Normalize legacy/local and prefixed NERSC merged-manifest columns."""
    prepared = manifest.copy()
    status_column = "status" if "status" in prepared.columns else "row_status"
    if status_column not in prepared.columns:
        raise ValueError("Manifest needs a status or row_status column")
    prepared = prepared.loc[prepared[status_column] == "completed"].copy()
    if "run_dir" not in prepared.columns:
        for candidate in ("row_run_dir", "expected_run_dir"):
            if candidate in prepared.columns:
                prepared["run_dir"] = prepared[candidate]
                break
    if "run_dir" not in prepared.columns:
        raise ValueError("Manifest needs run_dir, row_run_dir, or expected_run_dir")
    return prepared


def main() -> None:
    args = parse_args()
    rows = parse_rows(args.rows)
    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")
    excluded_sensors = parse_sensor_exclusions(args.exclude_sensor)
    scenario_columns = parse_scenario_columns(args.scenario_columns)

    manifest = prepare_manifest_for_scoring(pd.read_csv(args.manifest))
    if manifest.empty:
        raise ValueError(f"No completed runs found in {args.manifest}")
    purpleair = pd.read_csv(args.purpleair_csv)
    boundary = load_boundary(args.boundary_geojson)
    lon_grid, lat_grid = build_grid(boundary, args.grid_size)
    grid_view = (
        (lon_grid >= xlim[0]) & (lon_grid <= xlim[1]) &
        (lat_grid >= ylim[0]) & (lat_grid <= ylim[1])
    )
    window_lookup = build_window_lookup(purpleair)
    window_intervals = build_window_interval_lookup(purpleair)

    purpleair_windows: dict[int, dict[str, object]] = {}
    for window_index in rows:
        frame = pick_window(purpleair, window_index, excluded_sensors)
        kriged, valid_mask = krige_window(
            frame,
            boundary,
            lon_grid,
            lat_grid,
            variogram_model=args.variogram_model,
            distance_mask_km=args.distance_mask_km,
        )
        purple_class = enhancement_to_class(kriged)
        purple_hit_grid = np.isfinite(kriged) & (kriged >= args.purpleair_threshold)
        purple_sensor_hit = frame["enhancement_pos_mean"].to_numpy() >= args.purpleair_threshold
        purpleair_windows[window_index] = {
            "frame": frame,
            "kriged": kriged,
            "class": purple_class,
            "hit_grid": purple_hit_grid,
            "sensor_hit": purple_sensor_hit,
            "valid_mask": valid_mask,
        }

    records: list[dict[str, object]] = []
    skipped_runs: list[dict[str, object]] = []
    for _, row in manifest.iterrows():
        selected_windows = manifest_window_indices(row, window_lookup)
        cdump_path = Path(row["run_dir"]) / "cdump"
        for window_index in selected_windows:
            if window_index not in purpleair_windows:
                continue
            if window_index not in window_intervals:
                skipped_runs.append(
                    {
                        "run_tag": row.get("run_tag"),
                        "scenario_id": scenario_key(row, scenario_columns),
                        "window_index": window_index,
                        "run_dir": row.get("run_dir"),
                        "reason": f"PurpleAir window {window_index} has no unique timestamp interval",
                    }
                )
                continue

            sample_start_utc, sample_stop_utc = window_intervals[window_index]
            window_data = purpleair_windows[window_index]
            frame = window_data["frame"]
            valid_mask = window_data["valid_mask"] & grid_view

            try:
                h_lons, h_lats, h_conc = load_hysplit_conc(
                    cdump_path,
                    sample_start_utc=sample_start_utc,
                    sample_stop_utc=sample_stop_utc,
                )
            except Exception as exc:
                skipped_runs.append(
                    {
                        "run_tag": row.get("run_tag"),
                        "scenario_id": scenario_key(row, scenario_columns),
                        "window_index": window_index,
                        "run_dir": row.get("run_dir"),
                        "reason": str(exc),
                    }
                )
                continue
            h_grid = interpolate_field_to_points(h_lons, h_lats, h_conc, lon_grid, lat_grid)
            h_grid = np.where(valid_mask, h_grid, np.nan)
            h_class, quantiles = hysplit_to_relative_class(h_grid, valid_mask)
            h_hit_grid = (h_class >= args.hysplit_binary_class) & valid_mask

            sensor_values = interpolate_field_to_points(
                h_lons,
                h_lats,
                h_conc,
                frame["longitude"].to_numpy(),
                frame["latitude"].to_numpy(),
            )
            sensor_class = np.zeros(sensor_values.shape, dtype=int)
            positive_sensor = sensor_values > 0
            sensor_class[positive_sensor] = 1
            sensor_class[sensor_values >= quantiles[0]] = 2
            sensor_class[sensor_values >= quantiles[1]] = 3
            sensor_class[sensor_values >= quantiles[2]] = 4
            sensor_hit = sensor_class >= args.hysplit_binary_class

            purple_sensor_hit = window_data["sensor_hit"]
            tp, fn, fp, tn = confusion_counts(purple_sensor_hit, sensor_hit)
            sensor_f1 = f1_score(tp, fn, fp)

            purple_hit_grid = window_data["hit_grid"] & valid_mask
            grid_iou = iou_score(purple_hit_grid, h_hit_grid)
            class_score = class_agreement_score(window_data["class"], h_class)
            dist_score, mean_distance_km = distance_score(
                frame["longitude"].to_numpy(),
                frame["latitude"].to_numpy(),
                purple_sensor_hit,
                lon_grid,
                lat_grid,
                h_hit_grid,
                max_distance_km=max(args.distance_mask_km, 1.0),
            )
            total_score = 0.40 * sensor_f1 + 0.30 * grid_iou + 0.20 * class_score + 0.10 * dist_score

            record = row.to_dict()
            record.update(
                {
                    "sample_start_utc": sample_start_utc.isoformat(),
                    "sample_stop_utc": sample_stop_utc.isoformat(),
                    "window_index": window_index,
                    "scenario_id": scenario_key(row, scenario_columns),
                    "sensor_tp": tp,
                    "sensor_fn": fn,
                    "sensor_fp": fp,
                    "sensor_tn": tn,
                    "sensor_f1": sensor_f1,
                    "grid_iou": grid_iou,
                    "class_score": class_score,
                    "distance_score": dist_score,
                    "mean_distance_km": mean_distance_km,
                    "hysplit_q40": float(quantiles[0]),
                    "hysplit_q70": float(quantiles[1]),
                    "hysplit_q88": float(quantiles[2]),
                    "hysplit_q97": float(quantiles[3]),
                    "grid_kept_fraction": float(np.mean(valid_mask)),
                    "total_score": total_score,
                }
            )
            records.append(record)

    if not records:
        raise ValueError("No manifest rows matched the requested PurpleAir windows.")

    per_run = pd.DataFrame(records).sort_values(["scenario_id", "window_index"]).reset_index(drop=True)
    group = per_run.groupby("scenario_id", dropna=False)
    per_scenario = group.agg(
        run_count=("run_tag", "count"),
        source_height_m=("source_height_m", "first"),
        source_geometry=("source_geometry", "first"),
        source_footprint_m=("source_footprint_m", "first"),
        source_grid_shape=("source_grid_shape", "first"),
        source_rotation_deg=("source_rotation_deg", "first"),
        emission_hours=("emission_hours", "first"),
        emission_rate=("emission_rate", "first"),
        mean_sensor_f1=("sensor_f1", "mean"),
        mean_grid_iou=("grid_iou", "mean"),
        mean_class_score=("class_score", "mean"),
        mean_distance_score=("distance_score", "mean"),
        mean_distance_km=("mean_distance_km", "mean"),
        mean_total_score=("total_score", "mean"),
        min_total_score=("total_score", "min"),
        max_total_score=("total_score", "max"),
    ).reset_index()
    per_scenario = per_scenario.sort_values("mean_total_score", ascending=False).reset_index(drop=True)

    output_dir = args.output_dir or args.manifest.parent / "scoring"
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_stem = args.manifest.stem
    per_run_path = output_dir / f"{manifest_stem}_per_run_scores.csv"
    per_scenario_path = output_dir / f"{manifest_stem}_scenario_scores.csv"
    skipped_path = output_dir / f"{manifest_stem}_skipped_runs.csv"
    per_run.to_csv(per_run_path, index=False)
    per_scenario.to_csv(per_scenario_path, index=False)
    pd.DataFrame(skipped_runs).to_csv(skipped_path, index=False)

    print(f"Wrote per-run scores: {per_run_path}")
    print(f"Wrote scenario scores: {per_scenario_path}")
    print(f"Wrote skipped runs: {skipped_path}")
    print(f"Scored runs: {len(per_run)} | Skipped runs: {len(skipped_runs)}")
    print("Top scenarios:")
    top = per_scenario.head(10)[["scenario_id", "mean_total_score", "mean_sensor_f1", "mean_grid_iou", "mean_class_score", "mean_distance_km"]]
    print(top.to_string(index=False))


if __name__ == "__main__":
    main()
