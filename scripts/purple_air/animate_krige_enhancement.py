#!/usr/bin/env python3
"""
Animate kriged 4-hour PurpleAir enhancement windows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from pykrige.ok import OrdinaryKriging

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.purple_air.krige_enhancement import (
    DATA_DIR,
    KRIGING_DIR,
    ENHANCEMENT_BOUNDS,
    ENHANCEMENT_COLORS,
    ENHANCEMENT_LABELS,
    FIRE_START_LOCAL,
    MOSS_LANDING_LAT,
    MOSS_LANDING_LON,
    build_grid,
    build_mask,
    load_boundary,
    parse_sensor_exclusions,
    pick_window,
    resolve_basemap_provider,
    cx,
)


DEFAULT_INPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
DEFAULT_BOUNDARY = DATA_DIR / "monterey_bay_unified_apcd.geojson"
DEFAULT_GIF = KRIGING_DIR / "mbuapcd_enhancement_krige_postfire.gif"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animate kriged PurpleAir enhancement windows.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--boundary-geojson", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--gif-out", type=Path, default=DEFAULT_GIF)
    parser.add_argument("--start-window", type=int, default=-6)
    parser.add_argument("--end-window", type=int, default=12)
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--fps", type=int, default=2)
    parser.add_argument(
        "--hold-prefire",
        type=int,
        default=2,
        help="Repeat each pre-fire frame this many times to establish baseline behavior.",
    )
    parser.add_argument(
        "--hold-ignition",
        type=int,
        default=5,
        help="Repeat the ignition-crossing frame this many times.",
    )
    parser.add_argument(
        "--hold-postfire",
        type=int,
        default=1,
        help="Repeat each post-fire frame this many times.",
    )
    parser.add_argument(
        "--exclude-sensor",
        action="append",
        default=[],
        help="Sensor index to exclude from interpolation. Repeat the flag or pass a comma-separated list.",
    )
    parser.add_argument("--value-column", default="enhancement_pos_mean")
    parser.add_argument("--distance-mask-km", type=float, default=12.0)
    parser.add_argument("--grid-size", type=int, default=320)
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
        "--xlim",
        default=None,
        help="Optional lon range as min,max for a zoomed animation view.",
    )
    parser.add_argument(
        "--ylim",
        default=None,
        help="Optional lat range as min,max for a zoomed animation view.",
    )
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


def main() -> None:
    args = parse_args()
    if args.step < 1:
        raise ValueError("--step must be >= 1")
    if args.end_window < args.start_window:
        raise ValueError("--end-window must be >= --start-window")
    if args.hold_prefire < 1 or args.hold_ignition < 1 or args.hold_postfire < 1:
        raise ValueError("hold counts must be >= 1")
    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")

    df = pd.read_csv(args.input_csv)
    boundary = load_boundary(args.boundary_geojson)
    excluded_sensors = parse_sensor_exclusions(args.exclude_sensor)
    lon_grid, lat_grid = build_grid(boundary, args.grid_size)
    cmap = ListedColormap(ENHANCEMENT_COLORS)
    norm = BoundaryNorm(ENHANCEMENT_BOUNDS, cmap.N)

    window_indices = list(range(args.start_window, args.end_window + 1, args.step))
    frames: list[dict[str, object]] = []
    for window_index in window_indices:
        frame = pick_window(df, window_index, args.value_column, excluded_sensors)
        frame["window_start_local"] = pd.to_datetime(frame["window_start_local"], utc=True)
        frame["window_stop_local"] = pd.to_datetime(frame["window_stop_local"], utc=True)
        z_masked, valid_mask, variance_p90 = krige_frame(
            frame,
            lon_grid,
            lat_grid,
            boundary,
            args.distance_mask_km,
            args.value_column,
            args.variogram_model,
        )
        frames.append(
            {
                "window_index": window_index,
                "label": frame["window_label_local"].iloc[0],
                "frame": frame,
                "z_masked": z_masked,
                "variance_p90": variance_p90,
                "grid_kept": float(np.isfinite(z_masked).mean()),
                "start_local": frame["window_start_local"].iloc[0],
                "stop_local": frame["window_stop_local"].iloc[0],
            }
        )
        print(f"Prepared window {window_index}: {frame['window_label_local'].iloc[0]}")

    playback_frames: list[dict[str, object]] = []
    for state in frames:
        start_local = state["start_local"]
        stop_local = state["stop_local"]
        if stop_local <= FIRE_START_LOCAL:
            repeats = args.hold_prefire
        elif start_local <= FIRE_START_LOCAL < stop_local:
            repeats = args.hold_ignition
        else:
            repeats = args.hold_postfire
        playback_frames.extend([state] * repeats)

    fig, ax = plt.subplots(figsize=(10.7, 8.8), dpi=140)
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

    first = playback_frames[0]
    min_lon, min_lat, max_lon, max_lat = boundary.bounds
    view_xlim, view_ylim = adjust_view_bounds(
        xlim,
        ylim,
        (min_lon, min_lat, max_lon, max_lat),
        figure_size=(10.7, 8.8),
    )
    surface = ax.imshow(
        first["z_masked"],
        extent=(min_lon, max_lon, min_lat, max_lat),
        origin="lower",
        cmap=cmap,
        norm=norm,
        alpha=0.66,
        zorder=1,
        interpolation="bilinear",
        aspect="auto",
    )
    contour = ax.contour(
        lon_grid,
        lat_grid,
        first["z_masked"],
        levels=ENHANCEMENT_BOUNDS[1:-1],
        colors="white",
        linewidths=0.95,
        alpha=0.92,
        zorder=2,
    )

    boundary_x, boundary_y = boundary.exterior.xy
    ax.plot(boundary_x, boundary_y, color="#13d8ff", linewidth=1.8, alpha=0.95, zorder=3)

    first_frame = first["frame"]
    sensor_sizes = (first_frame[args.value_column].clip(lower=0.2, upper=80).pow(0.43) * 28).clip(lower=20, upper=160)
    scatter = ax.scatter(
        first_frame["longitude"],
        first_frame["latitude"],
        s=sensor_sizes,
        c=first_frame[args.value_column],
        cmap=cmap,
        norm=norm,
        edgecolors="#1c1c1c",
        linewidths=0.55,
        alpha=0.88,
        zorder=4,
    )

    ax.scatter([MOSS_LANDING_LON], [MOSS_LANDING_LAT], s=160, c="black", marker="x", linewidths=2.2, zorder=5)
    ax.scatter([MOSS_LANDING_LON], [MOSS_LANDING_LAT], s=480, c="#b30000", alpha=0.10, linewidths=0, zorder=4)

    ax.set_xlim(*view_xlim)
    ax.set_ylim(*view_ylim)

    title = fig.suptitle("Moss Landing Battery Fire - Kriged 4-Hour PM2.5 Enhancement", fontsize=16, weight="bold", y=0.97)
    subtitle = fig.text(0.5, 0.938, "", ha="center", va="center", fontsize=10.5, color="#36454f")
    stats_box = ax.text(
        0.985,
        0.02,
        "",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.4,
        color="#22313a",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.9, "edgecolor": "#b9c6d0"},
        zorder=6,
    )
    mask_box = ax.text(
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
    fire_box = ax.text(
        0.015,
        0.975,
        "",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=9.2,
        color="#4a0f0f",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.94, "edgecolor": "#d28d8d"},
        zorder=6,
    )

    legend_handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=color, markeredgecolor="#333333", markeredgewidth=0.6, markersize=8, label=label)
        for color, label in zip(ENHANCEMENT_COLORS, ENHANCEMENT_LABELS)
    ]
    legend_handles.append(
        Line2D([0], [0], marker="x", color="black", linestyle="None", markeredgewidth=2, markersize=9, label="Fire origin")
    )
    ax.legend(handles=legend_handles, loc="lower left", frameon=True, framealpha=0.9, facecolor="white", title="4-Hr Enhancement")

    cbar = fig.colorbar(surface, ax=ax, fraction=0.046, pad=0.03)
    cbar.set_label("PM2.5 enhancement (ug/m3)")
    cbar.set_ticks(ENHANCEMENT_BOUNDS[:-1])
    cbar.set_ticklabels(["0", "1", "5", "12", "35"])

    excluded_label = "none" if not excluded_sensors else ",".join(str(v) for v in sorted(excluded_sensors))
    contour_state = {"artist": contour}

    def update(frame_idx: int):
        nonlocal contour_state
        state = playback_frames[frame_idx]
        frame = state["frame"]
        z_masked = state["z_masked"]
        surface.set_data(z_masked)
        previous_contour = contour_state["artist"]
        if hasattr(previous_contour, "remove"):
            previous_contour.remove()
        elif hasattr(previous_contour, "collections"):
            for collection in previous_contour.collections:
                collection.remove()
        contour_state["artist"] = ax.contour(
            lon_grid,
            lat_grid,
            z_masked,
            levels=ENHANCEMENT_BOUNDS[1:-1],
            colors="white",
            linewidths=0.95,
            alpha=0.92,
            zorder=2,
        )
        sensor_sizes = (frame[args.value_column].clip(lower=0.2, upper=80).pow(0.43) * 28).clip(lower=20, upper=160)
        scatter.set_offsets(frame[["longitude", "latitude"]].to_numpy())
        scatter.set_sizes(sensor_sizes.to_numpy())
        scatter.set_array(frame[args.value_column].to_numpy())
        peak_row = frame.loc[frame[args.value_column].idxmax()]
        subtitle.set_text(state["label"])
        start_local = state["start_local"]
        stop_local = state["stop_local"]
        if stop_local <= FIRE_START_LOCAL:
            fire_box.set_text("Pre-fire window\nFire starts Jan 16, 2025\n5:35 PM PT")
            fire_box.set_bbox({"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.94, "edgecolor": "#d28d8d"})
        elif start_local <= FIRE_START_LOCAL < stop_local:
            fire_box.set_text("Ignition window\nFire starts during this panel\nJan 16, 2025 5:35 PM PT")
            fire_box.set_bbox({"boxstyle": "round,pad=0.35", "facecolor": "#fff3cd", "alpha": 0.96, "edgecolor": "#c98c00"})
        else:
            elapsed_hours = (start_local - FIRE_START_LOCAL).total_seconds() / 3600
            fire_box.set_text(
                "Post-ignition window\nStarted Jan 16, 2025 5:35 PM PT\nElapsed: {elapsed:.1f} h".format(
                    elapsed=elapsed_hours
                )
            )
            fire_box.set_bbox({"boxstyle": "round,pad=0.35", "facecolor": "#fff2f0", "alpha": 0.94, "edgecolor": "#b24a4a"})
        stats_box.set_text(
            "Window: {window}\nSensors: {count}\nPeak: {name}\nEnhancement: {peak:.1f} ug/m3\nGrid kept: {frac:.1%}\nVar p90: {var:.2f}\nExcluded: {excluded}".format(
                window=state["window_index"],
                count=len(frame),
                name=peak_row["name"][:24],
                peak=float(peak_row[args.value_column]),
                frac=state["grid_kept"],
                var=state["variance_p90"],
                excluded=excluded_label,
            )
        )
        return surface, scatter, subtitle, stats_box, title, fire_box, mask_box

    update(0)
    animation = FuncAnimation(fig, update, frames=len(playback_frames), interval=1000 / args.fps, blit=False)
    args.gif_out.parent.mkdir(parents=True, exist_ok=True)
    animation.save(args.gif_out, writer=PillowWriter(fps=args.fps))
    plt.close(fig)

    print(f"Saved kriging GIF to {args.gif_out}")
    print(f"Frames: {len(playback_frames)}")
    print(f"Unique windows: {len(frames)}")
    print(f"Windows: {args.start_window} to {args.end_window} step {args.step}")
    print(f"Excluded sensors: {excluded_label}")


if __name__ == "__main__":
    main()
