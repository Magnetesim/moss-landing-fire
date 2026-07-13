#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from moss_landing.paths import DATA_DIR, PROJECT_ROOT
from moss_landing.purpleair import API_BASE_URL, DEFAULT_API_KEY_PATH, get_json, load_api_key

DEFAULT_BOUNDARY_PATH = PROJECT_ROOT / "data" / "Air_District_WFL1_-841210503623017823.geojson"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Discover PurpleAir sensors within a selected California air-district boundary."
    )
    parser.add_argument(
        "--boundary-geojson",
        type=Path,
        default=DEFAULT_BOUNDARY_PATH,
        help="Path to the statewide air-district GeoJSON.",
    )
    parser.add_argument(
        "--district-name",
        default="MONTEREY BAY UNIFIED APCD",
        help="Air district to extract from the statewide GeoJSON.",
    )
    parser.add_argument(
        "--api-key-path",
        type=Path,
        default=DEFAULT_API_KEY_PATH,
        help="Path to the PurpleAir API key file.",
    )
    parser.add_argument(
        "--output-sensors",
        type=Path,
        default=DATA_DIR / "sensors_mbuapcd.csv",
        help="CSV path for discovered sensors inside the district polygon.",
    )
    parser.add_argument(
        "--output-boundary",
        type=Path,
        default=DATA_DIR / "monterey_bay_unified_apcd.geojson",
        help="GeoJSON path for the extracted district boundary.",
    )
    parser.add_argument(
        "--output-nearby",
        type=Path,
        default=DATA_DIR / "sensors_mbuapcd_bbox.csv",
        help="CSV path for sensors returned by the bounding-box query before polygon filtering.",
    )
    return parser.parse_args()


def load_geojson(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def feature_name(feature: dict) -> str:
    props = feature.get("properties", {})
    return str(props.get("Air_District_Name", "")).strip()


def extract_district_feature(collection: dict, district_name: str) -> dict:
    matches = [
        feature
        for feature in collection.get("features", [])
        if feature_name(feature).casefold() == district_name.casefold()
    ]
    if not matches:
        known = sorted({feature_name(feature) for feature in collection.get("features", []) if feature_name(feature)})
        raise ValueError(f"District {district_name!r} not found. Available districts include: {', '.join(known[:8])} ...")
    if len(matches) > 1:
        raise ValueError(f"District name {district_name!r} matched multiple features.")
    return matches[0]


def iter_rings(geometry: dict):
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if geom_type == "Polygon":
        for ring in coords:
            yield ring
    elif geom_type == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                yield ring
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")


def polygon_bbox(geometry: dict) -> tuple[float, float, float, float]:
    lons: list[float] = []
    lats: list[float] = []
    for ring in iter_rings(geometry):
        for lon, lat in ring:
            lons.append(float(lon))
            lats.append(float(lat))
    return min(lons), min(lats), max(lons), max(lats)


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1.0e-12) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


def point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if geom_type == "Polygon":
        polygons = [coords]
    elif geom_type == "MultiPolygon":
        polygons = coords
    else:
        raise ValueError(f"Unsupported geometry type: {geom_type}")

    for polygon in polygons:
        outer = polygon[0]
        if not point_in_ring(lon, lat, outer):
            continue
        holes = polygon[1:]
        if any(point_in_ring(lon, lat, hole) for hole in holes):
            continue
        return True
    return False


def purpleair_bbox_query(api_key: str, bbox: tuple[float, float, float, float]) -> pd.DataFrame:
    min_lon, min_lat, max_lon, max_lat = bbox
    params = {
        "fields": "sensor_index,name,latitude,longitude,pm2.5_atm",
        "location_type": "0",
        "nwlng": min_lon,
        "nwlat": max_lat,
        "selng": max_lon,
        "selat": min_lat,
    }
    payload = get_json(f"{API_BASE_URL}/sensors", api_key, params=params)
    return pd.DataFrame(payload["data"], columns=payload["fields"])


def main() -> None:
    args = parse_args()
    api_key = load_api_key(args.api_key_path)
    collection = load_geojson(args.boundary_geojson)
    district_feature = extract_district_feature(collection, args.district_name)
    geometry = district_feature["geometry"]
    bbox = polygon_bbox(geometry)

    args.output_boundary.parent.mkdir(parents=True, exist_ok=True)
    args.output_sensors.parent.mkdir(parents=True, exist_ok=True)
    args.output_nearby.parent.mkdir(parents=True, exist_ok=True)

    district_collection = {
        "type": "FeatureCollection",
        "features": [district_feature],
    }
    args.output_boundary.write_text(json.dumps(district_collection) + "\n", encoding="utf-8")

    nearby = purpleair_bbox_query(api_key, bbox)
    nearby.to_csv(args.output_nearby, index=False)

    inside_mask = nearby.apply(
        lambda row: point_in_geometry(float(row["longitude"]), float(row["latitude"]), geometry),
        axis=1,
    )
    sensors = nearby.loc[inside_mask].sort_values(["name", "sensor_index"]).reset_index(drop=True)
    sensors.to_csv(args.output_sensors, index=False)

    print(f"District: {args.district_name}")
    print(f"Bounding-box sensors: {len(nearby)}")
    print(f"Inside-district sensors: {len(sensors)}")
    print(f"Saved district boundary to {args.output_boundary}")
    print(f"Saved bbox query sensors to {args.output_nearby}")
    print(f"Saved in-district sensors to {args.output_sensors}")


if __name__ == "__main__":
    main()
