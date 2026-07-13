#!/usr/bin/env python3
"""
Build a conservative kriged PM2.5 enhancement panel for a single 4-hour window.

The interpolation is deliberately masked:
- outside the MBUAPCD boundary
- farther than a configurable distance from the nearest PurpleAir sensor
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from pykrige.ok import OrdinaryKriging

from moss_landing.constants import (
    ENHANCEMENT_BOUNDS,
    ENHANCEMENT_COLORS,
    ENHANCEMENT_LABELS,
    MOSS_LANDING_LAT,
    MOSS_LANDING_LON,
)
from moss_landing.kriging import (
    adjust_view_bounds,
    build_grid,
    build_mask,
    cx,
    load_boundary,
    parse_range_arg,
    parse_sensor_exclusions,
    pick_window,
    resolve_basemap_provider,
)
from moss_landing.paths import DATA_DIR, KRIGING_DIR

DEFAULT_INPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
DEFAULT_BOUNDARY = DATA_DIR / "monterey_bay_unified_apcd.geojson"
DEFAULT_OUTPUT = KRIGING_DIR / "mbuapcd_enhancement_krige_window0.png"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kriged PurpleAir enhancement panel.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--boundary-geojson", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--output-png", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--window-index", type=int, default=0)
    parser.add_argument(
        "--exclude-sensor",
        action="append",
        default=[],
        help="Sensor index to exclude from interpolation. Repeat the flag or pass a comma-separated list.",
    )
    parser.add_argument(
        "--value-column",
        default="enhancement_pos_mean",
        help="4-hour enhancement column to interpolate.",
    )
    parser.add_argument(
        "--distance-mask-km",
        type=float,
        default=12.0,
        help="Mask interpolated cells farther than this from the nearest sensor.",
    )
    parser.add_argument(
        "--grid-size",
        type=int,
        default=320,
        help="Grid resolution along the longer bbox dimension.",
    )
    parser.add_argument(
        "--variogram-model",
        choices=("linear", "power", "gaussian", "spherical", "exponential"),
        default="gaussian",
    )
    parser.add_argument(
        "--basemap-style",
        choices=("gray", "satellite", "light", "dark", "none"),
        default="gray",
    )
    parser.add_argument(
        "--save-grid-csv",
        type=Path,
        default=None,
        help="Optional CSV output for the masked kriging grid.",
    )
    parser.add_argument(
        "--xlim",
        default=None,
        help="Optional lon range as min,max for a zoomed static view.",
    )
    parser.add_argument(
        "--ylim",
        default=None,
        help="Optional lat range as min,max for a zoomed static view.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")

    df = pd.read_csv(args.input_csv)
    boundary = load_boundary(args.boundary_geojson)
    excluded_sensors = parse_sensor_exclusions(args.exclude_sensor)
    frame = pick_window(df, args.window_index, args.value_column, excluded_sensors)
    frame["window_start_local"] = pd.to_datetime(frame["window_start_local"], utc=True)
    frame["window_stop_local"] = pd.to_datetime(frame["window_stop_local"], utc=True)

    lon_grid, lat_grid = build_grid(boundary, args.grid_size)
    valid_mask, nearest_km = build_mask(
        lon_grid,
        lat_grid,
        boundary,
        frame["longitude"].to_numpy(),
        frame["latitude"].to_numpy(),
        args.distance_mask_km,
    )

    ok = OrdinaryKriging(
        frame["longitude"].to_numpy(),
        frame["latitude"].to_numpy(),
        frame[args.value_column].to_numpy(),
        variogram_model=args.variogram_model,
        coordinates_type="geographic",
        enable_plotting=False,
        verbose=False,
    )
    grid_lon_vals = lon_grid[0, :]
    grid_lat_vals = lat_grid[:, 0]
    z_grid, variance_grid = ok.execute("grid", grid_lon_vals, grid_lat_vals)
    z_grid = np.asarray(z_grid, dtype=float)
    variance_grid = np.asarray(variance_grid, dtype=float)
    z_grid = np.clip(z_grid, 0.0, ENHANCEMENT_BOUNDS[-1])

    z_masked = np.where(valid_mask, z_grid, np.nan)
    variance_masked = np.where(valid_mask, variance_grid, np.nan)

    if args.save_grid_csv is not None:
        out = pd.DataFrame(
            {
                "longitude": lon_grid.ravel(),
                "latitude": lat_grid.ravel(),
                "enhancement_kriged": z_masked.ravel(),
                "kriging_variance": variance_masked.ravel(),
                "nearest_sensor_km": nearest_km.ravel(),
                "inside_mask": valid_mask.ravel(),
            }
        )
        args.save_grid_csv.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(args.save_grid_csv, index=False)

    cmap = ListedColormap(ENHANCEMENT_COLORS)
    norm = BoundaryNorm(ENHANCEMENT_BOUNDS, cmap.N)

    fig, ax = plt.subplots(figsize=(10.7, 8.8), dpi=170)
    fig.subplots_adjust(top=0.87)
    fig.patch.set_facecolor("#eef4f8")
    ax.set_facecolor("#dbeaf4")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.14, color="#4f6b82", linewidth=0.6, zorder=0)

    if args.basemap_style != "none" and cx is not None:
        provider = resolve_basemap_provider(args.basemap_style)
        if provider is not None:
            cx.add_basemap(ax, crs="EPSG:4326", source=provider, attribution=False, zoom=10)

    surface = ax.pcolormesh(
        lon_grid,
        lat_grid,
        z_masked,
        cmap=cmap,
        norm=norm,
        shading="auto",
        alpha=0.58,
        zorder=1,
    )

    boundary_x, boundary_y = boundary.exterior.xy
    ax.plot(boundary_x, boundary_y, color="#13d8ff", linewidth=1.8, alpha=0.95, zorder=3)

    sensor_sizes = (frame[args.value_column].clip(lower=0.2, upper=80).pow(0.43) * 28).clip(lower=20, upper=160)
    ax.scatter(
        frame["longitude"],
        frame["latitude"],
        s=sensor_sizes,
        c=frame[args.value_column],
        cmap=cmap,
        norm=norm,
        edgecolors="#1c1c1c",
        linewidths=0.55,
        alpha=0.95,
        zorder=4,
    )

    ax.scatter(
        [MOSS_LANDING_LON],
        [MOSS_LANDING_LAT],
        s=160,
        c="black",
        marker="x",
        linewidths=2.2,
        zorder=5,
    )
    ax.scatter(
        [MOSS_LANDING_LON],
        [MOSS_LANDING_LAT],
        s=480,
        c="#b30000",
        alpha=0.10,
        linewidths=0,
        zorder=4,
    )

    min_lon, min_lat, max_lon, max_lat = boundary.bounds
    view_xlim, view_ylim = adjust_view_bounds(
        xlim,
        ylim,
        (min_lon, min_lat, max_lon, max_lat),
        figure_size=(10.7, 8.8),
    )
    ax.set_xlim(*view_xlim)
    ax.set_ylim(*view_ylim)

    local_label = frame["window_label_local"].iloc[0]
    fig.suptitle("Moss Landing Battery Fire - Kriged 4-Hour PM2.5 Enhancement", fontsize=16, weight="bold", y=0.97)
    fig.text(0.5, 0.938, local_label, ha="center", va="center", fontsize=10.5, color="#36454f")

    peak_row = frame.loc[frame[args.value_column].idxmax()]
    mask_fraction = float(np.isfinite(z_masked).mean())
    variance_p90 = float(np.nanpercentile(variance_masked, 90)) if np.isfinite(variance_masked).any() else np.nan
    stats_text = (
        "Sensors used: {count}\nPeak sensor: {name}\nPeak enhancement: {peak:.1f} ug/m3\n"
        "Distance mask: {mask:.0f} km\nGrid kept: {frac:.1%}\nVar p90: {var:.2f}\nExcluded: {excluded}"
    ).format(
        count=len(frame),
        name=peak_row["name"][:30],
        peak=float(peak_row[args.value_column]),
        mask=args.distance_mask_km,
        frac=mask_fraction,
        var=variance_p90,
        excluded=("none" if not excluded_sensors else ",".join(str(v) for v in sorted(excluded_sensors))),
    )
    ax.text(
        0.985,
        0.02,
        stats_text,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.4,
        color="#22313a",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9, "edgecolor": "#b9c6d0"},
        zorder=6,
    )
    ax.text(
        0.985,
        0.975,
        "Masked outside district\nand beyond nearest-sensor radius",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9.2,
        color="#4a0f0f",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fff2f0", "alpha": 0.94, "edgecolor": "#b24a4a"},
        zorder=6,
    )

    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=color,
            markeredgecolor="#333333",
            markeredgewidth=0.6,
            markersize=8,
            label=label,
        )
        for color, label in zip(ENHANCEMENT_COLORS, ENHANCEMENT_LABELS)
    ]
    legend_handles.append(
        Line2D(
            [0],
            [0],
            marker="x",
            color="black",
            linestyle="None",
            markeredgewidth=2,
            markersize=9,
            label="Fire origin",
        )
    )
    ax.legend(
        handles=legend_handles,
        loc="lower left",
        frameon=True,
        framealpha=0.9,
        facecolor="white",
        title="4-Hr Enhancement",
    )

    cbar = fig.colorbar(surface, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label("PM2.5 enhancement (ug/m3)")
    cbar.set_ticks(ENHANCEMENT_BOUNDS[:-1])
    cbar.set_ticklabels(["0", "1", "5", "12", "35"])

    args.output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output_png, bbox_inches="tight")
    plt.close(fig)

    print(f"Saved kriged panel to {args.output_png}")
    print(f"Window: {local_label}")
    print(f"Sensors used: {len(frame)}")
    print(f"Distance mask: {args.distance_mask_km:.1f} km")
    print(f"Masked grid fraction kept: {mask_fraction:.1%}")
    print(f"Peak enhancement: {float(frame[args.value_column].max()):.2f} ug/m3")
    print(
        "Excluded sensors: "
        + ("none" if not excluded_sensors else ",".join(str(v) for v in sorted(excluded_sensors)))
    )


if __name__ == "__main__":
    main()
