#!/usr/bin/env python3
"""
Tier 1 plume visualization for the Moss Landing battery fire.

Outputs:
- Interactive HTML map animation
- Exportable GIF animation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import xyzservices.providers as xyz
except ImportError:
    xyz = None

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
FIGURES_DIR = PROJECT_ROOT / "figures" / "visualization"

DATA_PATH = DATA_DIR / "moss_landing_pm25.csv"
ENHANCEMENT_4H_PATH = DATA_DIR / "mbuapcd_pm25_enhancement_4h.csv"
SENSOR_PATHS = [DATA_DIR / "sensors_active.csv", DATA_DIR / "sensors.csv"]
HTML_OUT = FIGURES_DIR / "tier1_bubble_map.html"
GIF_OUT = FIGURES_DIR / "tier1_bubble_map.gif"
PNG_OUT = FIGURES_DIR / "tier1_bubble_map.png"
FILTER_REPORT_OUT = FIGURES_DIR / "tier1_bubble_map_filtered_sensors.csv"

MOSS_LANDING_LAT = 36.8044
MOSS_LANDING_LON = -121.7883
FIRE_START_LOCAL = pd.Timestamp("2025-01-16 17:35", tz="US/Pacific")
FIRE_START_UTC = FIRE_START_LOCAL.tz_convert("UTC")

AQI_ORDER = [
    "Good (0-12)",
    "Moderate (12-35)",
    "USG (35-55)",
    "Unhealthy (55-150)",
    "Very Unhealthy (150-250)",
    "Hazardous (250+)",
]

AQI_COLORS = {
    "Good (0-12)": "#00e400",
    "Moderate (12-35)": "#ffff00",
    "USG (35-55)": "#ff7e00",
    "Unhealthy (55-150)": "#ff0000",
    "Very Unhealthy (150-250)": "#8f3f97",
    "Hazardous (250+)": "#7e0023",
}

ENHANCEMENT_ORDER = [
    "Background (0-1)",
    "Low (1-5)",
    "Moderate (5-12)",
    "Elevated (12-35)",
    "High (35+)",
]

ENHANCEMENT_COLORS = {
    "Background (0-1)": "#2c7bb6",
    "Low (1-5)": "#00a6ca",
    "Moderate (5-12)": "#00cc66",
    "Elevated (12-35)": "#f9d057",
    "High (35+)": "#d7191c",
}

ESRI_WORLD_IMAGERY_TILES = [
    "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
]
ESRI_WORLD_GRAY_TILES = [
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}"
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Moss Landing plume visualizations.")
    parser.add_argument(
        "--data-csv",
        type=Path,
        default=DATA_PATH,
        help="Hourly PurpleAir history CSV to visualize.",
    )
    parser.add_argument(
        "--sensor-csv",
        type=Path,
        default=None,
        help="Optional sensor metadata CSV. If omitted, falls back to the default sensor file search order.",
    )
    parser.add_argument(
        "--boundary-geojson",
        type=Path,
        default=None,
        help="Optional GeoJSON boundary overlay to draw on the map.",
    )
    parser.add_argument(
        "--html-out",
        type=Path,
        default=HTML_OUT,
        help="HTML output path.",
    )
    parser.add_argument(
        "--gif-out",
        type=Path,
        default=GIF_OUT,
        help="GIF output path.",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Write the interactive HTML animation.",
    )
    parser.add_argument(
        "--gif",
        action="store_true",
        help="Write an animated GIF for slides or docs.",
    )
    parser.add_argument(
        "--png",
        action="store_true",
        help="Write a static PNG panel.",
    )
    parser.add_argument(
        "--gif-step-hours",
        type=int,
        default=3,
        help="Use every Nth hourly frame in the GIF export (default: 3).",
    )
    parser.add_argument(
        "--gif-fps",
        type=int,
        default=6,
        help="GIF playback speed in frames per second (default: 6).",
    )
    parser.add_argument(
        "--png-out",
        type=Path,
        default=PNG_OUT,
        help="PNG output path.",
    )
    parser.add_argument(
        "--window-index",
        type=int,
        default=None,
        help="Optional window/frame index to render for PNG mode. Defaults to the first post-fire frame.",
    )
    parser.add_argument(
        "--stuck-threshold",
        type=float,
        default=1000.0,
        help="Exclude sensors if a large fraction of values stay above this PM2.5 threshold (default: 1000).",
    )
    parser.add_argument(
        "--stuck-fraction",
        type=float,
        default=0.9,
        help="Exclude sensors if at least this fraction of rows exceed --stuck-threshold (default: 0.9).",
    )
    parser.add_argument(
        "--filter-report",
        type=Path,
        default=FILTER_REPORT_OUT,
        help="Write a CSV report of excluded sensors here.",
    )
    parser.add_argument(
        "--basemap-style",
        choices=("satellite", "gray", "light", "dark", "none"),
        default="gray",
        help="Basemap style for supported outputs. GIF uses the same tile providers as the HYSPLIT renderer.",
    )
    parser.add_argument(
        "--bubble-scale",
        type=float,
        default=1.25,
        help="Multiply rendered bubble sizes by this factor (default: 1.25).",
    )
    parser.add_argument(
        "--mode",
        choices=("raw", "enhancement"),
        default="raw",
        help="Visualization mode. 'raw' expects hourly pm2.5_atm data, 'enhancement' expects enhancement fields.",
    )
    parser.add_argument(
        "--value-column",
        default=None,
        help="Value column to render. Defaults to pm2.5_atm in raw mode and enhancement_pos_mean in enhancement mode.",
    )
    args = parser.parse_args()

    if not args.html and not args.gif and not args.png:
        args.html = True

    return args


def resolve_gif_basemap_provider(style: str):
    if xyz is None:
        return None
    providers = {
        "satellite": xyz.Esri.WorldImagery,
        "gray": xyz.Esri.WorldGrayCanvas,
        "light": xyz.CartoDB.Positron,
        "dark": xyz.CartoDB.DarkMatter,
        "none": None,
    }
    return providers[style]


def resolve_html_map_style(style: str) -> str:
    styles = {
        "light": "carto-positron",
        "dark": "carto-darkmatter",
        "gray": "white-bg",
        "satellite": "white-bg",
        "none": "white-bg",
    }
    return styles[style]


def html_map_layers(style: str) -> list[dict[str, object]]:
    if style not in {"satellite", "gray"}:
        return []
    return [
        {
            "below": "traces",
            "sourcetype": "raster",
            "source": ESRI_WORLD_IMAGERY_TILES if style == "satellite" else ESRI_WORLD_GRAY_TILES,
            "sourceattribution": "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
        }
    ]


def aqi_category(pm25: float) -> str:
    if pm25 <= 12.0:
        return "Good (0-12)"
    if pm25 <= 35.4:
        return "Moderate (12-35)"
    if pm25 <= 55.4:
        return "USG (35-55)"
    if pm25 <= 150.4:
        return "Unhealthy (55-150)"
    if pm25 <= 250.4:
        return "Very Unhealthy (150-250)"
    return "Hazardous (250+)"


def enhancement_category(value: float) -> str:
    if value <= 1.0:
        return "Background (0-1)"
    if value <= 5.0:
        return "Low (1-5)"
    if value <= 12.0:
        return "Moderate (5-12)"
    if value <= 35.0:
        return "Elevated (12-35)"
    return "High (35+)"


def load_sensor_metadata() -> pd.DataFrame:
    for path in SENSOR_PATHS:
        if path.exists():
            sensors = pd.read_csv(path)
            return sensors[["sensor_index", "latitude", "longitude", "name"]].drop_duplicates()

    raise FileNotFoundError(f"No sensor metadata file found in {DATA_DIR}.")


def load_boundary(boundary_path: Path | None) -> list[list[tuple[float, float]]]:
    if boundary_path is None:
        return []
    payload = json.loads(boundary_path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    rings: list[list[tuple[float, float]]] = []
    for feature in features:
        geometry = feature.get("geometry", {})
        geom_type = geometry.get("type")
        coords = geometry.get("coordinates", [])
        polygons = [coords] if geom_type == "Polygon" else coords if geom_type == "MultiPolygon" else []
        for polygon in polygons:
            if not polygon:
                continue
            outer = polygon[0]
            rings.append([(float(lon), float(lat)) for lon, lat in outer])
    return rings


def identify_stuck_sensors(
    df: pd.DataFrame,
    threshold: float,
    fraction: float,
) -> pd.DataFrame:
    grouped = (
        df.groupby(["sensor_index", "name", "latitude", "longitude"], dropna=False)["pm2.5_atm"]
        .agg(row_count="size", min_pm25="min", median_pm25="median", max_pm25="max")
        .reset_index()
    )
    grouped["frac_over_threshold"] = (
        df.groupby("sensor_index")["pm2.5_atm"].apply(lambda s: (s > threshold).mean()).to_numpy()
    )
    return grouped.loc[grouped["frac_over_threshold"] >= fraction].sort_values(
        ["frac_over_threshold", "median_pm25", "max_pm25"],
        ascending=[False, False, False],
    )


def load_data(
    data_path: Path,
    sensor_path: Path | None,
    stuck_threshold: float,
    stuck_fraction: float,
    filter_report: Path,
    bubble_scale: float,
    mode: str,
    value_column: str | None,
) -> pd.DataFrame:
    df = pd.read_csv(data_path)

    time_column = "time_stamp" if "time_stamp" in df.columns else "window_start_utc"
    local_time_column = "local_time" if "local_time" in df.columns else "window_start_local"
    frame_label_column = "frame_label" if "frame_label" in df.columns else "window_label_local"
    if value_column is None:
        value_column = "pm2.5_atm" if mode == "raw" else "enhancement_pos_mean"
    if value_column not in df.columns:
        raise ValueError(f"Requested value column '{value_column}' not found in {data_path}.")

    df[time_column] = pd.to_datetime(df[time_column], utc=True)
    if local_time_column in df.columns:
        df[local_time_column] = pd.to_datetime(df[local_time_column], utc=True)
    else:
        df[local_time_column] = df[time_column].dt.tz_convert("US/Pacific")

    if sensor_path is not None:
        sensors = pd.read_csv(sensor_path)[["sensor_index", "latitude", "longitude", "name"]].drop_duplicates()
    else:
        sensors = load_sensor_metadata()
    missing_meta_cols = {"latitude", "longitude", "name"} - set(df.columns)
    if missing_meta_cols:
        df = df.merge(sensors, on="sensor_index", how="left", validate="many_to_one")

    missing = df["latitude"].isna().sum()
    if missing:
        raise ValueError(f"Missing sensor metadata for {missing} rows.")

    if mode == "raw":
        excluded = identify_stuck_sensors(df, threshold=stuck_threshold, fraction=stuck_fraction)
        if not excluded.empty:
            filter_report.parent.mkdir(parents=True, exist_ok=True)
            excluded.to_csv(filter_report, index=False)
            excluded_ids = set(excluded["sensor_index"].tolist())
            df = df.loc[~df["sensor_index"].isin(excluded_ids)].copy()
            print(
                "Excluded {count} stuck sensors using pm2.5>{threshold:g} for >= {fraction:.0%} of rows".format(
                    count=len(excluded),
                    threshold=stuck_threshold,
                    fraction=stuck_fraction,
                )
            )
            for row in excluded.itertuples(index=False):
                print(
                    "  - {sensor} | {name} | median={median:.1f} max={maxv:.1f} frac={frac:.0%}".format(
                        sensor=row.sensor_index,
                        name=row.name,
                        median=row.median_pm25,
                        maxv=row.max_pm25,
                        frac=row.frac_over_threshold,
                    )
                )
        elif filter_report.exists():
            filter_report.unlink()

    df["display_value"] = df[value_column].fillna(0.0).clip(lower=0.0)
    df["time_stamp"] = df[time_column]
    df["hour"] = df["time_stamp"].dt.floor("h")
    df["local_time"] = df[local_time_column]
    if frame_label_column in df.columns:
        df["frame_label"] = df[frame_label_column].astype(str)
    else:
        df["frame_label"] = df["local_time"].dt.strftime("%b %d, %Y %I:%M %p PT")

    if mode == "raw":
        df["value_cat"] = pd.Categorical(
            df["display_value"].apply(aqi_category),
            categories=AQI_ORDER,
            ordered=True,
        )
        df["value_color"] = df["value_cat"].map(AQI_COLORS)
        clipped = df["display_value"].clip(lower=0.5, upper=400)
    else:
        df["value_cat"] = pd.Categorical(
            df["display_value"].apply(enhancement_category),
            categories=ENHANCEMENT_ORDER,
            ordered=True,
        )
        df["value_color"] = df["value_cat"].map(ENHANCEMENT_COLORS)
        clipped = df["display_value"].clip(lower=0.2, upper=80)

    # Cap only the rendered size so local hot spots do not bury nearby sensors.
    df["bubble_size"] = (clipped.pow(0.43) * 3.1 * bubble_scale).clip(lower=2.8, upper=48)
    df["bubble_area"] = (df["bubble_size"] * 1.35).clip(lower=24, upper=290)
    if "humidity" in df.columns:
        df["humidity"] = df["humidity"].fillna(np.nan)
    elif "humidity_mean" in df.columns:
        df["humidity"] = df["humidity_mean"].fillna(np.nan)
    else:
        df["humidity"] = np.nan

    return df.sort_values(["time_stamp", "display_value", "sensor_index"])


def build_html(
    df: pd.DataFrame,
    outfile: Path,
    basemap_style: str,
    boundary_rings: list[list[tuple[float, float]]],
    mode: str,
) -> None:
    import plotly.express as px

    if mode == "raw":
        title = (
            "Moss Landing Battery Fire - PM2.5 Plume Transport"
            "<br><sup>Jan 14-25, 2025 | PurpleAir hourly observations | EPA AQI colors | Fire reported Jan 16, 2025 5:35 PM PT</sup>"
        )
        legend_title = "PM2.5 AQI"
        color_map = AQI_COLORS
        color_orders = AQI_ORDER
        hover_data = {
            "display_value": ":.1f",
            "pm2.5_atm": False,
            "humidity": ":.0f",
            "value_cat": True,
            "frame_label": False,
            "local_time": False,
            "latitude": False,
            "longitude": False,
            "bubble_size": False,
            "hour": False,
        }
    else:
        title = (
            "Moss Landing Battery Fire - 4-Hour PM2.5 Enhancement"
            "<br><sup>PurpleAir per-sensor baseline removed | 4-hour windows aligned to 2025-01-16 23:00 UTC ignition anchor</sup>"
        )
        legend_title = "4-Hr Enhancement"
        color_map = ENHANCEMENT_COLORS
        color_orders = ENHANCEMENT_ORDER
        hover_data = {
            "display_value": ":.1f",
            "enhancement_pos_mean": False,
            "enhancement_mean": ":.1f",
            "pm25_mean": ":.1f",
            "baseline_pm25": ":.1f",
            "n_hours": True,
            "humidity_mean": ":.0f",
            "value_cat": True,
            "frame_label": False,
            "local_time": False,
            "latitude": False,
            "longitude": False,
            "bubble_size": False,
            "hour": False,
        }

    fig = px.scatter_map(
        df,
        lat="latitude",
        lon="longitude",
        color="value_cat",
        color_discrete_map=color_map,
        size="bubble_size",
        size_max=36,
        animation_frame="frame_label",
        hover_name="name",
        hover_data=hover_data,
        category_orders={"value_cat": color_orders},
        title=title,
        zoom=9.05,
        center={"lat": 36.82, "lon": -121.81},
        height=840,
        opacity=0.82,
    )

    fig.update_traces(
        marker={"allowoverlap": True, "opacity": 0.84},
        selector={"type": "scattermap"},
    )

    fig.update_layout(
        map_style=resolve_html_map_style(basemap_style),
        map_layers=html_map_layers(basemap_style),
        template="plotly_white",
        margin={"r": 10, "t": 72, "l": 10, "b": 10},
        legend={
            "title": legend_title,
            "yanchor": "top",
            "y": 0.99,
            "xanchor": "left",
            "x": 0.01,
            "bgcolor": "rgba(255,255,255,0.88)",
            "bordercolor": "rgba(80,80,80,0.18)",
            "borderwidth": 1,
        },
    )

    if fig.layout.updatemenus:
        fig.layout.updatemenus[0].buttons[0].args[1]["frame"]["duration"] = 420
        fig.layout.updatemenus[0].buttons[0].args[1]["transition"]["duration"] = 0
        fig.layout.updatemenus[0].buttons[1].args[1]["frame"]["duration"] = 0
        fig.layout.updatemenus[0].bgcolor = "rgba(255,255,255,0.82)"

    if fig.layout.sliders:
        fig.layout.sliders[0].currentvalue["prefix"] = "Local time: "
        fig.layout.sliders[0]["pad"] = {"t": 18}

    fig.add_scattermap(
        lat=[MOSS_LANDING_LAT],
        lon=[MOSS_LANDING_LON],
        mode="markers",
        marker={"size": 28, "color": "rgba(170, 0, 0, 0.18)"},
        hoverinfo="skip",
        showlegend=False,
    )
    fig.add_scattermap(
        lat=[MOSS_LANDING_LAT],
        lon=[MOSS_LANDING_LON],
        mode="markers",
        marker={"size": 18, "color": "black", "symbol": "x"},
        name="Moss Landing fire origin",
        showlegend=True,
        hovertemplate="Moss Landing fire origin<extra></extra>",
    )

    for idx, ring in enumerate(boundary_rings):
        lons = [lon for lon, _ in ring]
        lats = [lat for _, lat in ring]
        fig.add_scattermap(
            lat=lats,
            lon=lons,
            mode="lines",
            line={"width": 2.2, "color": "#13d8ff"},
            name="MBUAPCD boundary" if idx == 0 else None,
            showlegend=(idx == 0),
            hoverinfo="skip",
        )

    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(outfile)
    print(f"Saved HTML animation to {outfile}")


def build_gif(
    df: pd.DataFrame,
    outfile: Path,
    step_hours: int,
    fps: int,
    basemap_style: str,
    boundary_rings: list[list[tuple[float, float]]],
    mode: str,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    from matplotlib.lines import Line2D

    try:
        import contextily as cx
    except ImportError:
        cx = None

    if step_hours < 1:
        raise ValueError("--gif-step-hours must be >= 1")

    hours = sorted(df["hour"].drop_duplicates())
    sampled_hours = hours[::step_hours]
    frame_groups = [df.loc[df["hour"] == hour].copy() for hour in sampled_hours]

    lon_pad = 0.05
    lat_pad = 0.04
    min_lon = df["longitude"].min() - lon_pad
    max_lon = df["longitude"].max() + lon_pad
    min_lat = df["latitude"].min() - lat_pad
    max_lat = df["latitude"].max() + lat_pad

    fig, ax = plt.subplots(figsize=(10.5, 8.4), dpi=120)
    fig.subplots_adjust(top=0.86)
    fig.patch.set_facecolor("#eef4f8")
    ax.set_facecolor("#dbeaf4")
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.15, color="#4f6b82", linewidth=0.6)

    if cx is not None:
        try:
            cx.add_basemap(
                ax,
                crs="EPSG:4326",
                source=resolve_gif_basemap_provider(basemap_style),
                attribution=False,
                zoom=10,
            )
            ax.set_xlim(min_lon, max_lon)
            ax.set_ylim(min_lat, max_lat)
        except Exception as exc:
            print(f"Basemap fetch failed for GIF export; continuing without tiles: {exc}")

    for ring in boundary_rings:
        lons = [lon for lon, _ in ring]
        lats = [lat for _, lat in ring]
        ax.plot(lons, lats, color="#13d8ff", linewidth=1.8, alpha=0.95, zorder=2)

    color_order = AQI_ORDER if mode == "raw" else ENHANCEMENT_ORDER
    color_map = AQI_COLORS if mode == "raw" else ENHANCEMENT_COLORS
    legend_title = "PM2.5 AQI" if mode == "raw" else "4-Hr Enhancement"
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=color_map[label],
            markeredgecolor="#333333",
            markeredgewidth=0.6,
            markersize=8,
            label=label,
        )
        for label in color_order
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
        title=legend_title,
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
    fire_ring = ax.scatter(
        [MOSS_LANDING_LON],
        [MOSS_LANDING_LAT],
        s=700,
        facecolors="none",
        edgecolors="#8b0000",
        linewidths=2.0,
        alpha=0.0,
        zorder=4,
    )

    sample = frame_groups[0]
    scatter = ax.scatter(
        sample["longitude"],
        sample["latitude"],
        s=sample["bubble_area"],
        c=sample["value_color"],
        alpha=0.82,
        edgecolors="#2e2e2e",
        linewidths=0.55,
        zorder=3,
    )

    title = fig.suptitle("", fontsize=16, weight="bold", y=0.97)
    subtitle = fig.text(
        0.5,
        0.938,
        "",
        ha="center",
        va="center",
        fontsize=10.5,
        color="#36454f",
    )
    event_box = ax.text(
        0.985,
        0.975,
        "",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9.6,
        color="#4a0f0f",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.90, "edgecolor": "#d28d8d"},
    )
    stats_box = ax.text(
        0.985,
        0.02,
        "",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.5,
        color="#22313a",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.88, "edgecolor": "#b9c6d0"},
    )

    def update(frame_index: int):
        frame = frame_groups[frame_index].sort_values("display_value")
        scatter.set_offsets(frame[["longitude", "latitude"]].to_numpy())
        scatter.set_sizes(frame["bubble_area"].to_numpy())
        scatter.set_facecolors(frame["value_color"].to_numpy())
        scatter.set_edgecolors(np.full(len(frame), "#2e2e2e"))

        local_time = frame["local_time"].iloc[0]
        peak_row = frame.loc[frame["display_value"].idxmax()]
        if mode == "raw":
            title.set_text("Moss Landing Battery Fire - PM2.5 Plume Transport")
            subtitle.set_text(local_time.strftime("%b %d, %Y %I:%M %p PT"))
        else:
            title.set_text("Moss Landing Battery Fire - 4-Hour PM2.5 Enhancement")
            subtitle.set_text(frame["frame_label"].iloc[0])

        if local_time < FIRE_START_LOCAL:
            event_box.set_text(
                "Pre-fire baseline\nFire reported: Jan 16, 2025\n5:35 PM PT"
            )
            event_box.set_bbox({"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.90, "edgecolor": "#d28d8d"})
            fire_ring.set_alpha(0.0)
        else:
            elapsed_hours = (local_time - FIRE_START_LOCAL).total_seconds() / 3600
            event_box.set_text(
                "Fire active\nStarted: Jan 16, 2025 5:35 PM PT\nElapsed: {elapsed:.1f} hours".format(
                    elapsed=elapsed_hours
                )
            )
            event_box.set_bbox({"boxstyle": "round,pad=0.35", "facecolor": "#fff2f0", "alpha": 0.94, "edgecolor": "#b24a4a"})
            fire_ring.set_sizes([900 + min(elapsed_hours, 48) * 14])
            fire_ring.set_alpha(0.45)

        if mode == "raw":
            stats_box.set_text(
                "Peak sensor: {name}\nPM2.5: {pm:.1f} ug/m3\nMedian network PM2.5: {median:.1f} ug/m3".format(
                    name=peak_row["name"][:30],
                    pm=peak_row["display_value"],
                    median=frame["display_value"].median(),
                )
            )
        else:
            stats_box.set_text(
                "Peak sensor: {name}\nEnhancement: {enh:.1f} ug/m3\nMedian network enhancement: {median:.1f} ug/m3".format(
                    name=peak_row["name"][:30],
                    enh=peak_row["display_value"],
                    median=frame["display_value"].median(),
                )
            )
        return scatter, fire_ring, title, subtitle, event_box, stats_box

    animation = FuncAnimation(fig, update, frames=len(frame_groups), interval=1000 / fps, blit=False)

    outfile.parent.mkdir(parents=True, exist_ok=True)
    animation.save(outfile, writer=PillowWriter(fps=fps))
    plt.close(fig)
    print(
        f"Saved GIF animation to {outfile} "
        f"({len(frame_groups)} frames, every {step_hours} hour{'s' if step_hours != 1 else ''})"
    )


def build_png(
    df: pd.DataFrame,
    outfile: Path,
    basemap_style: str,
    boundary_rings: list[list[tuple[float, float]]],
    mode: str,
    window_index: int | None,
) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    try:
        import contextily as cx
    except ImportError:
        cx = None

    if window_index is None:
        post_fire = df.loc[df["time_stamp"] >= FIRE_START_UTC]
        frame = post_fire.copy() if not post_fire.empty else df.copy()
        selected_ts = frame["time_stamp"].min()
        frame = frame.loc[frame["time_stamp"] == selected_ts].copy()
    else:
        if "window_index" not in df.columns:
            raise ValueError("--window-index requires a dataset with a window_index column.")
        frame = df.loc[df["window_index"] == window_index].copy()
        if frame.empty:
            raise ValueError(f"No rows found for window_index={window_index}.")

    lon_pad = 0.05
    lat_pad = 0.04
    min_lon = df["longitude"].min() - lon_pad
    max_lon = df["longitude"].max() + lon_pad
    min_lat = df["latitude"].min() - lat_pad
    max_lat = df["latitude"].max() + lat_pad

    fig, ax = plt.subplots(figsize=(10.5, 8.4), dpi=160)
    fig.subplots_adjust(top=0.86)
    fig.patch.set_facecolor("#eef4f8")
    ax.set_facecolor("#dbeaf4")
    ax.set_xlim(min_lon, max_lon)
    ax.set_ylim(min_lat, max_lat)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.grid(alpha=0.15, color="#4f6b82", linewidth=0.6)

    provider = resolve_gif_basemap_provider(basemap_style)
    if cx is not None and provider is not None:
        try:
            cx.add_basemap(
                ax,
                crs="EPSG:4326",
                source=provider,
                attribution=False,
                zoom=10,
            )
            ax.set_xlim(min_lon, max_lon)
            ax.set_ylim(min_lat, max_lat)
        except Exception as exc:
            print(f"Basemap fetch failed for PNG export; continuing without tiles: {exc}")

    for ring in boundary_rings:
        lons = [lon for lon, _ in ring]
        lats = [lat for _, lat in ring]
        ax.plot(lons, lats, color="#13d8ff", linewidth=1.8, alpha=0.95, zorder=2)

    color_order = AQI_ORDER if mode == "raw" else ENHANCEMENT_ORDER
    color_map = AQI_COLORS if mode == "raw" else ENHANCEMENT_COLORS
    legend_title = "PM2.5 AQI" if mode == "raw" else "4-Hr Enhancement"
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=color_map[label],
            markeredgecolor="#333333",
            markeredgewidth=0.6,
            markersize=8,
            label=label,
        )
        for label in color_order
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
        title=legend_title,
    )

    ax.scatter(
        frame["longitude"],
        frame["latitude"],
        s=frame["bubble_area"],
        c=frame["value_color"],
        alpha=0.82,
        edgecolors="#2e2e2e",
        linewidths=0.55,
        zorder=3,
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

    peak_row = frame.loc[frame["display_value"].idxmax()]
    if mode == "raw":
        fig.suptitle("Moss Landing Battery Fire - PM2.5 Plume Transport", fontsize=16, weight="bold", y=0.97)
        subtitle_text = frame["local_time"].iloc[0].strftime("%b %d, %Y %I:%M %p PT")
        stats_text = (
            "Peak sensor: {name}\nPM2.5: {pm:.1f} ug/m3\nMedian network PM2.5: {median:.1f} ug/m3".format(
                name=peak_row["name"][:30],
                pm=peak_row["display_value"],
                median=frame["display_value"].median(),
            )
        )
    else:
        fig.suptitle("Moss Landing Battery Fire - 4-Hour PM2.5 Enhancement", fontsize=16, weight="bold", y=0.97)
        subtitle_text = frame["frame_label"].iloc[0]
        stats_text = (
            "Peak sensor: {name}\nEnhancement: {enh:.1f} ug/m3\nMedian network enhancement: {median:.1f} ug/m3".format(
                name=peak_row["name"][:30],
                enh=peak_row["display_value"],
                median=frame["display_value"].median(),
            )
        )

    fig.text(0.5, 0.938, subtitle_text, ha="center", va="center", fontsize=10.5, color="#36454f")
    ax.text(
        0.985,
        0.975,
        "Fire active\nStarted: Jan 16, 2025 5:35 PM PT",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=9.6,
        color="#4a0f0f",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "#fff2f0", "alpha": 0.94, "edgecolor": "#b24a4a"},
    )
    ax.text(
        0.985,
        0.02,
        stats_text,
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=9.5,
        color="#22313a",
        bbox={"boxstyle": "round,pad=0.35", "facecolor": "white", "alpha": 0.88, "edgecolor": "#b9c6d0"},
    )

    outfile.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(outfile, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved PNG panel to {outfile}")


def main() -> None:
    args = parse_args()
    df = load_data(
        data_path=args.data_csv,
        sensor_path=args.sensor_csv,
        stuck_threshold=args.stuck_threshold,
        stuck_fraction=args.stuck_fraction,
        filter_report=args.filter_report,
        bubble_scale=args.bubble_scale,
        mode=args.mode,
        value_column=args.value_column,
    )
    boundary_rings = load_boundary(args.boundary_geojson)

    print(f"Loaded {len(df)} rows across {df['sensor_index'].nunique()} sensors")
    print(f"Date range: {df['time_stamp'].min()} to {df['time_stamp'].max()}")
    print(f"Frames available: {df['hour'].nunique()}")

    if args.html:
        build_html(df, args.html_out, basemap_style=args.basemap_style, boundary_rings=boundary_rings, mode=args.mode)

    if args.gif:
        build_gif(
            df,
            args.gif_out,
            step_hours=args.gif_step_hours,
            fps=args.gif_fps,
            basemap_style=args.basemap_style,
            boundary_rings=boundary_rings,
            mode=args.mode,
        )

    if args.png:
        build_png(
            df,
            args.png_out,
            basemap_style=args.basemap_style,
            boundary_rings=boundary_rings,
            mode=args.mode,
            window_index=args.window_index,
        )


if __name__ == "__main__":
    main()
