#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm, Normalize
import numpy as np
import pandas as pd

try:
    import contextily as cx
except ImportError:
    cx = None

try:
    import xyzservices.providers as xyz
except ImportError:
    xyz = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HYSPLIT_ROOT = PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64"
HYSPLIT_ROOT = Path(os.environ.get("HYSPLIT_ROOT", DEFAULT_HYSPLIT_ROOT))
HYSPLITDATA_ROOT = HYSPLIT_ROOT / "python" / "hysplitdata"

if str(HYSPLITDATA_ROOT) not in sys.path:
    sys.path.insert(0, str(HYSPLITDATA_ROOT))

import hysplitdata  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a custom PNG and data exports from a HYSPLIT cdump file.")
    parser.add_argument("cdump", type=Path, help="Path to the HYSPLIT cdump file.")
    parser.add_argument("--output-png", type=Path, help="PNG output path. Defaults next to the cdump.")
    parser.add_argument("--output-csv", type=Path, help="CSV output path for nonzero grid cells. Defaults next to the cdump.")
    parser.add_argument("--output-json", type=Path, help="JSON summary output path. Defaults next to the cdump.")
    parser.add_argument("--time-index", type=int, default=-1, help="Time index to plot. Default is the last time index.")
    parser.add_argument("--level", type=int, help="Vertical level in meters AGL. Default is the first/only level.")
    parser.add_argument("--pollutant", default=None, help="Pollutant name to plot. Default is the first/only pollutant.")
    parser.add_argument("--scale", choices=("log", "linear"), default="log", help="Color scaling for the raster plot.")
    parser.add_argument("--num-levels", type=int, default=6, help="Number of contour levels when --levels is not provided.")
    parser.add_argument(
        "--levels",
        help="Comma-separated contour levels. If omitted, levels are auto-derived from the selected grid.",
    )
    parser.add_argument(
        "--min-positive",
        type=float,
        help="Optional lower bound for positive values in the plot. Defaults to the smallest positive cell value.",
    )
    parser.add_argument("--title", help="Optional custom plot title.")
    parser.add_argument(
        "--view",
        choices=("plume", "full"),
        default="plume",
        help="Plot either the full model domain or auto-zoom to the nonzero plume envelope.",
    )
    parser.add_argument(
        "--pad-deg",
        type=float,
        default=0.08,
        help="Padding in degrees to add around the plotted plume/domain extent.",
    )
    parser.add_argument(
        "--basemap",
        action="store_true",
        help="Overlay a contextily basemap if the package is available.",
    )
    parser.add_argument(
        "--basemap-style",
        choices=("satellite", "light", "dark"),
        default="satellite",
        help="Basemap style to use with --basemap. Satellite uses Esri.WorldImagery.",
    )
    parser.add_argument(
        "--xlim",
        default=None,
        help="Optional longitude range as min,max for a custom zoom window.",
    )
    parser.add_argument(
        "--ylim",
        default=None,
        help="Optional latitude range as min,max for a custom zoom window.",
    )
    return parser.parse_args()


def default_output_path(cdump_path: Path, suffix: str) -> Path:
    return cdump_path.with_name(f"{cdump_path.name}_{suffix}")


def read_manifest_metadata(cdump_path: Path) -> dict[str, object]:
    run_dir = cdump_path.parent.resolve()
    sweeps_dir = run_dir.parent
    metadata: dict[str, object] = {}

    manifest_candidates = sorted(sweeps_dir.glob("*manifest*.csv"))
    for manifest_path in manifest_candidates:
        try:
            manifest = pd.read_csv(manifest_path)
        except Exception:
            continue
        if "run_dir" not in manifest.columns:
            continue
        run_dirs = manifest["run_dir"].astype(str).map(lambda raw: str(Path(raw).resolve()))
        matches = manifest.loc[run_dirs == str(run_dir)]
        if matches.empty:
            continue
        row = matches.iloc[0]
        for key in (
            "emission_hours",
            "emission_rate",
            "source_height_m",
            "source_geometry",
            "source_footprint_m",
            "source_grid_shape",
            "source_rotation_deg",
            "sample_start_utc",
            "sample_stop_utc",
            "release_end_utc",
            "start_utc",
            "end_utc",
            "ignition_utc",
            "simulation_end_utc",
        ):
            if key in row and pd.notna(row[key]):
                metadata[key] = row[key]
        break

    return metadata


def infer_run_metadata(cdump_path: Path) -> dict[str, object]:
    run_dir_name = cdump_path.parent.name
    metadata: dict[str, object] = {
        "run_dir_name": run_dir_name,
        "run_start_utc": None,
        "run_end_utc": None,
        "emission_hours": None,
        "emission_rate": None,
        "release_start_utc": None,
        "release_end_utc": None,
    }

    time_match = re.search(r"_t(\d{10})_to_(\d{10})_", run_dir_name)
    if time_match:
        metadata["run_start_utc"] = pd.to_datetime(time_match.group(1), format="%Y%m%d%H", utc=True)
        metadata["run_end_utc"] = pd.to_datetime(time_match.group(2), format="%Y%m%d%H", utc=True)

    emission_hours_match = re.search(r"_eh(\d+(?:p\d+)?)", run_dir_name)
    if emission_hours_match:
        metadata["emission_hours"] = float(emission_hours_match.group(1).replace("p", "."))

    emission_rate_match = re.search(r"_er(\d+(?:p\d+)?)", run_dir_name)
    if emission_rate_match:
        metadata["emission_rate"] = float(emission_rate_match.group(1).replace("p", "."))

    if metadata["run_start_utc"] is not None:
        metadata["release_start_utc"] = metadata["run_start_utc"]
    if metadata["run_start_utc"] is not None and metadata["emission_hours"] is not None:
        metadata["release_end_utc"] = metadata["run_start_utc"] + pd.to_timedelta(metadata["emission_hours"], unit="h")

    manifest_metadata = read_manifest_metadata(cdump_path)
    if manifest_metadata:
        if "emission_hours" in manifest_metadata:
            metadata["emission_hours"] = float(manifest_metadata["emission_hours"])
        if "emission_rate" in manifest_metadata:
            metadata["emission_rate"] = float(manifest_metadata["emission_rate"])
        if "ignition_utc" in manifest_metadata:
            metadata["release_start_utc"] = pd.Timestamp(manifest_metadata["ignition_utc"], tz="UTC")
        elif "start_utc" in manifest_metadata:
            metadata["release_start_utc"] = pd.Timestamp(manifest_metadata["start_utc"], tz="UTC")
        if "release_end_utc" in manifest_metadata:
            metadata["release_end_utc"] = pd.Timestamp(manifest_metadata["release_end_utc"], tz="UTC")
        if "simulation_end_utc" in manifest_metadata:
            metadata["run_end_utc"] = pd.Timestamp(manifest_metadata["simulation_end_utc"], tz="UTC")
        elif "end_utc" in manifest_metadata:
            metadata["run_end_utc"] = pd.Timestamp(manifest_metadata["end_utc"], tz="UTC")

    if metadata["release_start_utc"] is not None and metadata["release_end_utc"] is None and metadata["emission_hours"] is not None:
        metadata["release_end_utc"] = metadata["release_start_utc"] + pd.to_timedelta(metadata["emission_hours"], unit="h")

    return metadata


def resolve_time_index(cdump, requested_index: int) -> int:
    time_indices = sorted({grid.time_index for grid in cdump.grids})
    if not time_indices:
        raise ValueError("The cdump file does not contain any grids.")
    if requested_index < 0:
        requested_index = time_indices[requested_index]
    if requested_index not in time_indices:
        raise ValueError(f"time index {requested_index} not found; valid choices: {time_indices}")
    return requested_index


def select_grids(cdump, time_index: int, level: int | None, pollutant: str | None):
    selected = [grid for grid in cdump.grids if grid.time_index == time_index]
    if pollutant is None:
        pollutant = cdump.pollutants[0]
    selected = [grid for grid in selected if grid.pollutant == pollutant]
    if not selected:
        raise ValueError(f"No grids found for time index {time_index} and pollutant {pollutant!r}.")

    if level is None:
        level = selected[0].vert_level
    selected = [grid for grid in selected if grid.vert_level == level]
    if not selected:
        available = sorted({grid.vert_level for grid in cdump.grids if grid.time_index == time_index and grid.pollutant == pollutant})
        raise ValueError(
            f"No grids found for time index {time_index}, pollutant {pollutant!r}, level {level}. "
            f"Available levels: {available}"
        )
    return selected, level, pollutant


def build_dataframe(longitudes: list[float], latitudes: list[float], conc: np.ndarray) -> pd.DataFrame:
    lon_grid, lat_grid = np.meshgrid(np.asarray(longitudes), np.asarray(latitudes))
    frame = pd.DataFrame(
        {
            "longitude": lon_grid.ravel(),
            "latitude": lat_grid.ravel(),
            "concentration": conc.ravel(),
        }
    )
    frame["is_positive"] = frame["concentration"] > 0
    return frame


def compute_levels(values: np.ndarray, scale: str, num_levels: int, levels_arg: str | None, min_positive: float | None) -> np.ndarray:
    if levels_arg:
        levels = np.array([float(part.strip()) for part in levels_arg.split(",") if part.strip()], dtype=float)
        levels = np.unique(levels)
        if len(levels) < 2:
            raise ValueError("At least two distinct contour levels are required.")
        return levels

    positive = np.sort(values[values > 0])
    if positive.size == 0:
        raise ValueError("No positive concentrations found in the selected grid.")
    low = min_positive if min_positive is not None else float(positive[0])
    high = float(positive[-1])
    if low <= 0:
        low = float(positive[0])
    if scale == "log":
        levels = np.geomspace(low, high, num=max(num_levels, 2))
    else:
        levels = np.linspace(low, high, num=max(num_levels, 2))
    levels = np.unique(levels)
    if len(levels) < 2:
        levels = np.array([low, high], dtype=float)
    return levels


def centers_to_edges(values: np.ndarray) -> np.ndarray:
    if values.size == 1:
        delta = 0.005
        return np.array([values[0] - delta, values[0] + delta], dtype=float)
    mids = (values[:-1] + values[1:]) / 2.0
    first = values[0] - (mids[0] - values[0])
    last = values[-1] + (values[-1] - mids[-1])
    return np.concatenate(([first], mids, [last]))


def write_summary_json(output_path: Path, payload: dict[str, object]) -> None:
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compute_bounds(
    longitudes: np.ndarray,
    latitudes: np.ndarray,
    conc: np.ndarray,
    source_lon: float,
    source_lat: float,
    view: str,
    pad_deg: float,
) -> tuple[float, float, float, float]:
    lon_min = float(longitudes.min())
    lon_max = float(longitudes.max())
    lat_min = float(latitudes.min())
    lat_max = float(latitudes.max())

    if view == "full" or not np.any(conc > 0):
        return lon_min, lon_max, lat_min, lat_max

    positive_rows, positive_cols = np.where(conc > 0)
    plume_lon_min = float(longitudes[positive_cols.min()])
    plume_lon_max = float(longitudes[positive_cols.max()])
    plume_lat_min = float(latitudes[positive_rows.min()])
    plume_lat_max = float(latitudes[positive_rows.max()])

    # Always keep the source inside the plot, even if all positive cells drift away.
    plume_lon_min = min(plume_lon_min, source_lon)
    plume_lon_max = max(plume_lon_max, source_lon)
    plume_lat_min = min(plume_lat_min, source_lat)
    plume_lat_max = max(plume_lat_max, source_lat)

    bounded = (
        max(lon_min, plume_lon_min - pad_deg),
        min(lon_max, plume_lon_max + pad_deg),
        max(lat_min, plume_lat_min - pad_deg),
        min(lat_max, plume_lat_max + pad_deg),
    )
    return bounded


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


def resolve_basemap_provider(style: str):
    if xyz is None:
        return None
    providers = {
        "satellite": xyz.Esri.WorldImagery,
        "light": xyz.CartoDB.Positron,
        "dark": xyz.CartoDB.DarkMatter,
    }
    return providers.get(style)


def add_basemap_if_available(ax: plt.Axes, style: str) -> None:
    if cx is None:
        return
    provider = resolve_basemap_provider(style)
    if provider is None:
        return
    try:
        cx.add_basemap(
            ax,
            crs="EPSG:4326",
            source=provider,
            attribution=False,
            zoom="auto",
        )
    except Exception:
        # Tile fetches are opportunistic; plotting should still succeed offline.
        return


def plot_grid(
    output_path: Path,
    longitudes: np.ndarray,
    latitudes: np.ndarray,
    conc: np.ndarray,
    source_lon: float,
    source_lat: float,
    levels: np.ndarray,
    scale: str,
    title: str,
    view: str,
    pad_deg: float,
    basemap: bool,
    basemap_style: str,
    stats_text: str,
    xlim: tuple[float, float] | None,
    ylim: tuple[float, float] | None,
) -> None:
    positive = conc[conc > 0]
    if positive.size == 0:
        raise ValueError("No positive concentrations found in the selected grid.")

    if scale == "log":
        norm = LogNorm(vmin=float(levels[0]), vmax=float(max(levels[-1], positive.max())))
    else:
        norm = Normalize(vmin=float(levels[0]), vmax=float(max(levels[-1], positive.max())))

    masked = np.ma.masked_less_equal(conc, 0.0)
    lon_edges = centers_to_edges(longitudes)
    lat_edges = centers_to_edges(latitudes)
    lon_grid, lat_grid = np.meshgrid(longitudes, latitudes)
    bounds = compute_bounds(longitudes, latitudes, conc, source_lon, source_lat, view=view, pad_deg=pad_deg)
    view_xlim, view_ylim = adjust_view_bounds(
        xlim,
        ylim,
        bounds,
        figure_size=(12, 8),
    )

    fig = plt.figure(figsize=(12, 8), dpi=180)
    ax = fig.add_axes([0.07, 0.12, 0.68, 0.78])
    mesh = ax.pcolormesh(lon_edges, lat_edges, masked, shading="auto", cmap="viridis", norm=norm, alpha=0.9)
    contour = ax.contour(lon_grid, lat_grid, masked, levels=levels, colors="white", linewidths=0.75, alpha=0.95)
    ax.clabel(contour, fmt="%.1e", inline=True, fontsize=7)
    if basemap:
        add_basemap_if_available(ax, style=basemap_style)
    ax.scatter([source_lon], [source_lat], marker="*", s=170, color="#ff3b30", edgecolor="black", linewidth=0.8, zorder=6)
    ax.set_xlim(*view_xlim)
    ax.set_ylim(*view_ylim)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title(title)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(alpha=0.15, linewidth=0.5, color="#708090")

    inset = fig.add_axes([0.78, 0.56, 0.18, 0.28])
    inset.pcolormesh(lon_edges, lat_edges, masked, shading="auto", cmap="viridis", norm=norm)
    inset.scatter([source_lon], [source_lat], marker="*", s=60, color="#ff3b30", edgecolor="black", linewidth=0.6, zorder=6)
    inset.set_xlim(float(longitudes.min()), float(longitudes.max()))
    inset.set_ylim(float(latitudes.min()), float(latitudes.max()))
    inset.set_xticks([])
    inset.set_yticks([])
    inset.set_title("Full Domain", fontsize=9)
    rect_x = [bounds[0], bounds[1], bounds[1], bounds[0], bounds[0]]
    rect_y = [bounds[2], bounds[2], bounds[3], bounds[3], bounds[2]]
    if xlim is not None or ylim is not None:
        rect_x = [view_xlim[0], view_xlim[1], view_xlim[1], view_xlim[0], view_xlim[0]]
        rect_y = [view_ylim[0], view_ylim[0], view_ylim[1], view_ylim[1], view_ylim[0]]
    inset.plot(rect_x, rect_y, color="white", linewidth=1.2)

    cbar = fig.colorbar(mesh, ax=ax, pad=0.02, shrink=0.9)
    cbar.set_label("Concentration (mass/m3)")

    stats_ax = fig.add_axes([0.78, 0.12, 0.18, 0.34])
    stats_ax.axis("off")
    stats_ax.text(
        0.0,
        1.0,
        stats_text,
        va="top",
        ha="left",
        fontsize=9,
        family="monospace",
        bbox={"facecolor": "#f4f6f8", "edgecolor": "#c7d0d9", "boxstyle": "round,pad=0.5"},
    )

    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")

    cdump_path = args.cdump.resolve()
    output_png = args.output_png or default_output_path(cdump_path, "custom.png")
    output_csv = args.output_csv or default_output_path(cdump_path, "nonzero.csv")
    output_json = args.output_json or default_output_path(cdump_path, "summary.json")

    cdump = hysplitdata.read_cdump(str(cdump_path))
    inferred = infer_run_metadata(cdump_path)
    time_index = resolve_time_index(cdump, args.time_index)
    selected_grids, level, pollutant = select_grids(cdump, time_index, args.level, args.pollutant)

    combined_conc = np.sum([grid.conc for grid in selected_grids], axis=0)
    data = build_dataframe(cdump.longitudes, cdump.latitudes, combined_conc)
    nonzero = data[data["is_positive"]].drop(columns=["is_positive"]).copy()
    nonzero = nonzero.sort_values("concentration", ascending=False).reset_index(drop=True)
    nonzero.to_csv(output_csv, index=False)

    first_grid = selected_grids[0]
    levels = compute_levels(
        combined_conc,
        scale=args.scale,
        num_levels=args.num_levels,
        levels_arg=args.levels,
        min_positive=args.min_positive,
    )

    summary = {
        "cdump_path": str(cdump_path),
        "meteo_model": cdump.meteo_model,
        "grid_size": {"lon": cdump.grid_sz[0], "lat": cdump.grid_sz[1]},
        "grid_deltas": {"lon": cdump.grid_deltas[0], "lat": cdump.grid_deltas[1]},
        "grid_origin": {"lon": cdump.grid_loc[0], "lat": cdump.grid_loc[1]},
        "source_location": {"lon": cdump.release_locs[0][0], "lat": cdump.release_locs[0][1]},
        "source_height_m_agl": cdump.release_heights[0],
        "run_start_utc": inferred["run_start_utc"].isoformat() if inferred["run_start_utc"] is not None else None,
        "run_end_utc": inferred["run_end_utc"].isoformat() if inferred["run_end_utc"] is not None else None,
        "release_start_utc": inferred["release_start_utc"].isoformat() if inferred["release_start_utc"] is not None else None,
        "release_end_utc": inferred["release_end_utc"].isoformat() if inferred["release_end_utc"] is not None else None,
        "emission_hours": inferred["emission_hours"],
        "emission_rate": inferred["emission_rate"],
        "time_index": time_index,
        "sample_start_utc": first_grid.starting_datetime.isoformat(),
        "sample_stop_utc": first_grid.ending_datetime.isoformat(),
        "level_m_agl": level,
        "pollutant": pollutant,
        "scale": args.scale,
        "view": args.view,
        "basemap": args.basemap,
        "basemap_style": args.basemap_style,
        "contour_levels": levels.tolist(),
        "positive_cell_count": int((combined_conc > 0).sum()),
        "positive_cell_fraction": float((combined_conc > 0).sum() / combined_conc.size),
        "min_positive_concentration": float(combined_conc[combined_conc > 0].min()),
        "max_concentration": float(combined_conc.max()),
        "mean_positive_concentration": float(combined_conc[combined_conc > 0].mean()),
        "output_png": str(output_png),
        "output_csv": str(output_csv),
    }
    write_summary_json(output_json, summary)

    title = args.title or (
        f"{cdump.meteo_model} forward plume | Src {summary['source_height_m_agl']:g} m | "
        f"{first_grid.starting_datetime:%Y-%m-%d %H:%M} to {first_grid.ending_datetime:%Y-%m-%d %H:%M} UTC"
    )
    stats_text = "\n".join(
        [
            f"Source: {cdump.release_locs[0][1]:.4f}, {cdump.release_locs[0][0]:.4f}",
            f"Src h:  {summary['source_height_m_agl']} m AGL",
            f"Conc z: {level} m AGL",
            f"Emit h: {summary['emission_hours'] if summary['emission_hours'] is not None else 'n/a'}",
            f"Rel st: {summary['release_start_utc'][5:16] if summary['release_start_utc'] else 'n/a'}",
            f"Rel en: {summary['release_end_utc'][5:16] if summary['release_end_utc'] else 'n/a'}",
            f"Samp st:{summary['sample_start_utc'][5:16]}",
            f"Samp en:{summary['sample_stop_utc'][5:16]}",
            f"Cells+:  {summary['positive_cell_count']}",
            f"Frac+:   {summary['positive_cell_fraction']:.3f}",
            f"Min+:    {summary['min_positive_concentration']:.2e}",
            f"Mean+:   {summary['mean_positive_concentration']:.2e}",
            f"Max:     {summary['max_concentration']:.2e}",
            f"Scale:   {args.scale}",
            f"View:    {args.view}",
            f"Base:    {args.basemap_style if args.basemap else 'off'}",
        ]
    )
    plot_grid(
        output_path=output_png,
        longitudes=np.asarray(cdump.longitudes),
        latitudes=np.asarray(cdump.latitudes),
        conc=combined_conc,
        source_lon=cdump.release_locs[0][0],
        source_lat=cdump.release_locs[0][1],
        levels=levels,
        scale=args.scale,
        title=title,
        view=args.view,
        pad_deg=args.pad_deg,
        basemap=args.basemap,
        basemap_style=args.basemap_style,
        stats_text=stats_text,
        xlim=xlim,
        ylim=ylim,
    )

    print(f"Wrote PNG: {output_png}")
    print(f"Wrote CSV: {output_csv}")
    print(f"Wrote JSON: {output_json}")
    print(f"Positive cells: {summary['positive_cell_count']} / {combined_conc.size}")
    print(f"Max concentration: {summary['max_concentration']:.6e}")


if __name__ == "__main__":
    main()
