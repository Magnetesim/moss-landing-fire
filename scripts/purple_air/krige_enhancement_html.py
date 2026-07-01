#!/usr/bin/env python3
"""
Interactive HTML slider for kriged 4-hour PurpleAir enhancement windows.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.purple_air.animate_krige_enhancement import (
    adjust_view_bounds,
    krige_frame,
    parse_range_arg,
)
from scripts.purple_air.krige_enhancement import (
    DATA_DIR,
    KRIGING_DIR,
    ENHANCEMENT_BOUNDS,
    ENHANCEMENT_COLORS,
    FIRE_START_LOCAL,
    MOSS_LANDING_LAT,
    MOSS_LANDING_LON,
    build_grid,
    load_boundary,
    parse_sensor_exclusions,
    pick_window,
)


DEFAULT_INPUT_CSV = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
DEFAULT_BOUNDARY = DATA_DIR / "monterey_bay_unified_apcd.geojson"
DEFAULT_HTML = KRIGING_DIR / "mbuapcd_enhancement_krige_slider.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Interactive HTML for kriged PurpleAir enhancement windows.")
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT_CSV)
    parser.add_argument("--boundary-geojson", type=Path, default=DEFAULT_BOUNDARY)
    parser.add_argument("--html-out", type=Path, default=DEFAULT_HTML)
    parser.add_argument("--start-window", type=int, default=-6)
    parser.add_argument("--end-window", type=int, default=12)
    parser.add_argument("--step", type=int, default=1)
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
    parser.add_argument("--xlim", default=None, help="Optional lon range as min,max for a zoomed HTML view.")
    parser.add_argument("--ylim", default=None, help="Optional lat range as min,max for a zoomed HTML view.")
    return parser.parse_args()


def fire_phase(start_local: pd.Timestamp, stop_local: pd.Timestamp) -> str:
    if stop_local <= FIRE_START_LOCAL:
        return "Pre-fire"
    if start_local <= FIRE_START_LOCAL < stop_local:
        return "Ignition window"
    elapsed_hours = (start_local - FIRE_START_LOCAL).total_seconds() / 3600
    return f"Post-ignition (+{elapsed_hours:.1f} h)"


def build_colorscale() -> list[list[object]]:
    vmax = ENHANCEMENT_BOUNDS[-1]
    colorscale: list[list[object]] = []
    for i, color in enumerate(ENHANCEMENT_COLORS):
        low = ENHANCEMENT_BOUNDS[i] / vmax
        high = ENHANCEMENT_BOUNDS[i + 1] / vmax
        colorscale.append([low, color])
        colorscale.append([high, color])
    return colorscale


def main() -> None:
    args = parse_args()
    if args.step < 1:
        raise ValueError("--step must be >= 1")
    if args.end_window < args.start_window:
        raise ValueError("--end-window must be >= --start-window")

    xlim = parse_range_arg(args.xlim, "--xlim")
    ylim = parse_range_arg(args.ylim, "--ylim")

    df = pd.read_csv(args.input_csv)
    boundary = load_boundary(args.boundary_geojson)
    excluded_sensors = parse_sensor_exclusions(args.exclude_sensor)
    lon_grid, lat_grid = build_grid(boundary, args.grid_size)
    min_lon, min_lat, max_lon, max_lat = boundary.bounds
    view_xlim, view_ylim = adjust_view_bounds(
        xlim, ylim, (min_lon, min_lat, max_lon, max_lat), figure_size=(10.7, 8.8)
    )

    window_indices = list(range(args.start_window, args.end_window + 1, args.step))
    frame_states: list[dict[str, object]] = []
    for window_index in window_indices:
        frame = pick_window(df, window_index, args.value_column, excluded_sensors)
        frame["window_start_local"] = pd.to_datetime(frame["window_start_local"], utc=True)
        frame["window_stop_local"] = pd.to_datetime(frame["window_stop_local"], utc=True)
        z_masked, _, variance_p90 = krige_frame(
            frame,
            lon_grid,
            lat_grid,
            boundary,
            args.distance_mask_km,
            args.value_column,
            args.variogram_model,
        )
        peak_row = frame.loc[frame[args.value_column].idxmax()]
        frame_states.append(
            {
                "window_index": window_index,
                "label": frame["window_label_local"].iloc[0],
                "frame": frame,
                "z_masked": z_masked,
                "variance_p90": variance_p90,
                "grid_kept": float(np.isfinite(z_masked).mean()),
                "peak_name": peak_row["name"][:28],
                "peak_value": float(peak_row[args.value_column]),
                "phase": fire_phase(frame["window_start_local"].iloc[0], frame["window_stop_local"].iloc[0]),
            }
        )
        print(f"Prepared window {window_index}: {frame['window_label_local'].iloc[0]}")

    boundary_x, boundary_y = boundary.exterior.xy
    boundary_x = list(boundary_x)
    boundary_y = list(boundary_y)
    colorscale = build_colorscale()
    excluded_label = "none" if not excluded_sensors else ",".join(str(v) for v in sorted(excluded_sensors))
    contour_levels = ENHANCEMENT_BOUNDS[1:-1]

    first = frame_states[0]
    first_frame = first["frame"]
    hover_text = [
        (
            f"{name}<br>Enhancement: {val:.1f} ug/m3<br>Lon: {lon:.4f}<br>Lat: {lat:.4f}"
        )
        for name, val, lon, lat in zip(
            first_frame["name"], first_frame[args.value_column], first_frame["longitude"], first_frame["latitude"]
        )
    ]

    fig = go.Figure(
        data=[
            go.Contour(
                x=lon_grid[0, :],
                y=lat_grid[:, 0],
                z=first["z_masked"],
                colorscale=colorscale,
                zmin=0,
                zmax=ENHANCEMENT_BOUNDS[-1],
                contours=dict(
                    start=contour_levels[0],
                    end=contour_levels[-1],
                    size=contour_levels[1] - contour_levels[0],
                    coloring="heatmap",
                    showlines=True,
                ),
                line=dict(color="white", width=1),
                colorbar=dict(
                    title="PM2.5 enhancement (ug/m3)",
                    tickvals=ENHANCEMENT_BOUNDS[:-1],
                    ticktext=["0", "1", "5", "12", "35"],
                ),
                hoverinfo="skip",
                opacity=0.78,
                name="Kriged enhancement",
            ),
            go.Scatter(
                x=boundary_x,
                y=boundary_y,
                mode="lines",
                line=dict(color="#13d8ff", width=2),
                name="District boundary",
                hoverinfo="skip",
            ),
            go.Scatter(
                x=first_frame["longitude"],
                y=first_frame["latitude"],
                mode="markers",
                marker=dict(
                    size=8,
                    color=first_frame[args.value_column],
                    colorscale=colorscale,
                    cmin=0,
                    cmax=ENHANCEMENT_BOUNDS[-1],
                    line=dict(color="#1c1c1c", width=0.7),
                ),
                text=hover_text,
                hoverinfo="text",
                name="Sensors",
            ),
            go.Scatter(
                x=[MOSS_LANDING_LON],
                y=[MOSS_LANDING_LAT],
                mode="markers",
                marker=dict(size=14, symbol="x", color="black"),
                name="Fire origin",
                hovertemplate="Moss Landing fire origin<extra></extra>",
            ),
        ]
    )

    frames = []
    slider_steps = []
    for idx, state in enumerate(frame_states):
        frame_df = state["frame"]
        hover_text = [
            (
                f"{name}<br>Enhancement: {val:.1f} ug/m3<br>Lon: {lon:.4f}<br>Lat: {lat:.4f}"
            )
            for name, val, lon, lat in zip(
                frame_df["name"], frame_df[args.value_column], frame_df["longitude"], frame_df["latitude"]
            )
        ]
        annotation_text = (
            f"{state['phase']}<br>"
            f"Window {state['window_index']}<br>"
            f"Peak: {state['peak_name']} ({state['peak_value']:.1f} ug/m3)<br>"
            f"Grid kept: {state['grid_kept']:.1%} | Var p90: {state['variance_p90']:.2f}<br>"
            f"Excluded: {excluded_label}"
        )
        frames.append(
            go.Frame(
                name=str(state["window_index"]),
                data=[
                    go.Contour(z=state["z_masked"]),
                    go.Scatter(),
                    go.Scatter(
                        x=frame_df["longitude"],
                        y=frame_df["latitude"],
                        marker=dict(color=frame_df[args.value_column]),
                        text=hover_text,
                    ),
                    go.Scatter(),
                ],
                layout=go.Layout(
                    title=dict(
                        text=(
                            "Moss Landing Battery Fire - Kriged 4-Hour PM2.5 Enhancement"
                            f"<br><sup>{state['label']}</sup>"
                        )
                    ),
                    annotations=[
                        dict(
                            x=0.015,
                            y=0.98,
                            xref="paper",
                            yref="paper",
                            xanchor="left",
                            yanchor="top",
                            showarrow=False,
                            align="left",
                            bgcolor="rgba(255,255,255,0.92)",
                            bordercolor="#c98c00" if state["phase"] == "Ignition window" else "#d28d8d",
                            borderwidth=1.5,
                            text=annotation_text,
                            font=dict(size=12),
                        )
                    ],
                ),
            )
        )
        slider_steps.append(
            {
                "args": [[str(state["window_index"])], {"frame": {"duration": 0, "redraw": True}, "mode": "immediate"}],
                "label": state["label"],
                "method": "animate",
            }
        )

    fig.frames = frames
    fig.update_layout(
        title=(
            "Moss Landing Battery Fire - Kriged 4-Hour PM2.5 Enhancement"
            f"<br><sup>{first['label']}</sup>"
        ),
        template="plotly_white",
        width=1150,
        height=900,
        margin=dict(l=40, r=40, t=90, b=110),
        xaxis=dict(title="Longitude", range=list(view_xlim), scaleanchor="y", scaleratio=1),
        yaxis=dict(title="Latitude", range=list(view_ylim)),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="left",
            x=0.0,
            bgcolor="rgba(255,255,255,0.85)",
        ),
        sliders=[
            {
                "active": 0,
                "currentvalue": {"prefix": "Window: "},
                "pad": {"t": 45},
                "steps": slider_steps,
            }
        ],
        updatemenus=[
            {
                "type": "buttons",
                "direction": "left",
                "x": 0.0,
                "y": -0.12,
                "showactive": False,
                "buttons": [
                    {
                        "label": "Play",
                        "method": "animate",
                        "args": [
                            None,
                            {"frame": {"duration": 900, "redraw": True}, "fromcurrent": True, "transition": {"duration": 0}},
                        ],
                    },
                    {
                        "label": "Pause",
                        "method": "animate",
                        "args": [[None], {"frame": {"duration": 0, "redraw": False}, "mode": "immediate"}],
                    },
                ],
            }
        ],
        annotations=[
            dict(
                x=0.015,
                y=0.98,
                xref="paper",
                yref="paper",
                xanchor="left",
                yanchor="top",
                showarrow=False,
                align="left",
                bgcolor="rgba(255,255,255,0.92)",
                bordercolor="#d28d8d",
                borderwidth=1.5,
                text=(
                    f"{first['phase']}<br>"
                    f"Window {first['window_index']}<br>"
                    f"Peak: {first['peak_name']} ({first['peak_value']:.1f} ug/m3)<br>"
                    f"Grid kept: {first['grid_kept']:.1%} | Var p90: {first['variance_p90']:.2f}<br>"
                    f"Excluded: {excluded_label}"
                ),
                font=dict(size=12),
            )
        ],
    )

    args.html_out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(args.html_out, include_plotlyjs="cdn")
    print(f"Saved HTML slider to {args.html_out}")
    print(f"Frames: {len(frame_states)}")
    print(f"Windows: {args.start_window} to {args.end_window} step {args.step}")
    print(f"Excluded sensors: {excluded_label}")


if __name__ == "__main__":
    main()
