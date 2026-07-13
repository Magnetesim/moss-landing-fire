#!/usr/bin/env python3

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from moss_landing import paths
from moss_landing.fsutil import ensure_bdyfiles_link
from moss_landing.paths import DATA_DIR, HRRR_DIR as DEFAULT_HRRR_DIR, PROJECT_ROOT

DEFAULT_EVENTS_PATH = DATA_DIR / "receptor_events.csv"
DEFAULT_HYSPLIT_ROOT = paths.hysplit_root()
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "hysplit" / "runs" / "trajectory_runs"


@dataclass(frozen=True)
class MetFile:
    start: pd.Timestamp
    filename: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-run HYSPLIT backward trajectories from PurpleAir receptor events."
    )
    parser.add_argument("--events-csv", type=Path, default=DEFAULT_EVENTS_PATH)
    parser.add_argument("--hrrr-dir", type=Path, default=DEFAULT_HRRR_DIR)
    parser.add_argument("--hysplit-root", type=Path, default=DEFAULT_HYSPLIT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--durations-hours",
        default="24",
        help="Comma-separated backward durations, e.g. 24 or 24,36,48.",
    )
    parser.add_argument(
        "--heights-agl",
        default="10,50,200,500",
        help="Comma-separated starting heights in meters AGL.",
    )
    parser.add_argument(
        "--time-column",
        choices=["peak_time_utc", "onset_time_utc"],
        default="peak_time_utc",
        help="Which receptor-event time to use as the backward trajectory start.",
    )
    parser.add_argument(
        "--primary-only",
        action="store_true",
        help="Use only the primary event per sensor from receptor_events.csv.",
    )
    parser.add_argument(
        "--sensor-limit",
        type=int,
        default=None,
        help="Optional limit on number of event rows to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write CONTROL files and manifest rows but do not call hyts_std.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of HYSPLIT runs to execute concurrently. Use 1 for serial execution.",
    )
    return parser.parse_args()


def parse_int_list(raw: str) -> list[int]:
    values = [int(piece.strip()) for piece in raw.split(",") if piece.strip()]
    if not values:
        raise ValueError("Expected at least one integer value")
    return values


def floor_to_hrrr_block(ts: pd.Timestamp) -> pd.Timestamp:
    hour = (ts.hour // 6) * 6
    return ts.floor("D") + pd.Timedelta(hours=hour)


def hrrr_filename(block_start: pd.Timestamp) -> str:
    return f"{block_start:%Y%m%d}_{block_start:%H}-{block_start.hour + 5:02d}_hrrr"


def required_met_files(end_time: pd.Timestamp, duration_hours: int) -> list[MetFile]:
    start_time = end_time - pd.Timedelta(hours=duration_hours)
    block_start = floor_to_hrrr_block(start_time)
    block_end = floor_to_hrrr_block(end_time)

    files: list[MetFile] = []
    current = block_start
    while current <= block_end:
        files.append(MetFile(start=current, filename=hrrr_filename(current)))
        current += pd.Timedelta(hours=6)
    return files


def load_events(events_csv: Path, time_column: str, primary_only: bool, sensor_limit: int | None) -> pd.DataFrame:
    events = pd.read_csv(events_csv)
    for col in ["peak_time_utc", "onset_time_utc"]:
        if col in events.columns:
            events[col] = pd.to_datetime(events[col], utc=True)

    required_cols = ["sensor_index", "name", "latitude", "longitude", time_column]
    missing = [col for col in required_cols if col not in events.columns]
    if missing:
        raise ValueError(f"Missing required event columns: {missing}")

    if primary_only:
        if "is_primary_event" not in events.columns:
            raise ValueError("--primary-only requested but is_primary_event column is missing")
        events = events[events["is_primary_event"] == True].copy()  # noqa: E712

    events = events.sort_values(["sensor_index", time_column]).reset_index(drop=True)
    if sensor_limit is not None:
        events = events.head(sensor_limit).copy()
    return events


def ensure_batch_support_files(output_root: Path, hysplit_root: Path) -> None:
    ensure_bdyfiles_link(output_root, hysplit_root)


def tdump_has_points(tdump_path: Path) -> bool:
    if not tdump_path.exists():
        return False
    with tdump_path.open("r", encoding="utf-8", errors="ignore") as handle:
        for idx, _line in enumerate(handle, start=1):
            if idx >= 10:
                return True
    return False


def write_control(
    control_path: Path,
    end_time: pd.Timestamp,
    latitude: float,
    longitude: float,
    height_agl: int,
    duration_hours: int,
    hrrr_dir: Path,
    met_files: list[MetFile],
) -> None:
    lines = [
        end_time.strftime("%y %m %d %H"),
        "1",
        f"{latitude:.6f} {longitude:.6f} {height_agl}",
        f"-{duration_hours}",
        "0",
        "10000.0",
        f"{len(met_files)} 1",
    ]

    met_dir = str(hrrr_dir.resolve()) + "/"
    for met_file in met_files:
        lines.extend([met_dir, met_file.filename])

    lines.extend(["./", "tdump"])
    control_path.write_text("\n".join(lines) + "\n", encoding="ascii")


def build_manifest_row(
    row: pd.Series,
    event_time: pd.Timestamp,
    event_rank: int,
    episode_number: int,
    time_column: str,
    height_agl: int,
    duration_hours: int,
    run_dir: Path,
    control_path: Path,
    tdump_path: Path,
    log_path: Path,
    met_files: list[MetFile],
    missing_met: list[str],
    status: str,
) -> dict[str, object]:
    return {
        "sensor_index": int(row["sensor_index"]),
        "name": row["name"],
        "event_time_utc": event_time,
        "event_rank": event_rank,
        "episode_number": episode_number,
        "time_column": time_column,
        "peak_pm25_atm": float(row["peak_pm25_atm"]) if "peak_pm25_atm" in row and pd.notna(row["peak_pm25_atm"]) else None,
        "height_agl_m": height_agl,
        "duration_hours": duration_hours,
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "run_dir": str(run_dir.resolve()),
        "control_path": str(control_path.resolve()),
        "tdump_path": str(tdump_path.resolve()),
        "log_path": str(log_path.resolve()),
        "met_files": ";".join(mf.filename for mf in met_files),
        "missing_met_files": ";".join(missing_met),
        "status": status,
    }


def run_hysplit_task(
    hyts_std: Path,
    row: pd.Series,
    event_time: pd.Timestamp,
    event_rank: int,
    episode_number: int,
    time_column: str,
    height_agl: int,
    duration_hours: int,
    hrrr_dir: Path,
    output_root: Path,
    dry_run: bool,
) -> dict[str, object]:
    met_files = required_met_files(end_time=event_time, duration_hours=duration_hours)
    missing_met = [mf.filename for mf in met_files if not (hrrr_dir / mf.filename).exists()]

    event_label = f"sensor_{int(row['sensor_index'])}_event_{event_rank:03d}_episode_{episode_number:03d}"
    run_dir = output_root / f"{event_label}_t{event_time:%Y%m%d%H}_d{duration_hours:02d}_h{height_agl:04d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    control_path = run_dir / "CONTROL"
    log_path = run_dir / "run.log"
    tdump_path = run_dir / "tdump"

    write_control(
        control_path=control_path,
        end_time=event_time,
        latitude=float(row["latitude"]),
        longitude=float(row["longitude"]),
        height_agl=height_agl,
        duration_hours=duration_hours,
        hrrr_dir=hrrr_dir,
        met_files=met_files,
    )

    status = "dry_run" if dry_run else "pending"
    if missing_met:
        status = "missing_met"
        log_path.write_text(
            "Missing meteorology files:\n" + "\n".join(missing_met) + "\n",
            encoding="utf-8",
        )
    elif not dry_run:
        proc = subprocess.run(
            [str(hyts_std)],
            cwd=run_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        log_path.write_text(proc.stdout, encoding="utf-8")
        status = "completed" if proc.returncode == 0 and tdump_has_points(tdump_path) else "failed"

    return build_manifest_row(
        row=row,
        event_time=event_time,
        event_rank=event_rank,
        episode_number=episode_number,
        time_column=time_column,
        height_agl=height_agl,
        duration_hours=duration_hours,
        run_dir=run_dir,
        control_path=control_path,
        tdump_path=tdump_path,
        log_path=log_path,
        met_files=met_files,
        missing_met=missing_met,
        status=status,
    )


def main() -> None:
    args = parse_args()

    durations = parse_int_list(args.durations_hours)
    heights = parse_int_list(args.heights_agl)
    if args.jobs < 1:
        raise ValueError("--jobs must be at least 1")

    events = load_events(
        events_csv=args.events_csv,
        time_column=args.time_column,
        primary_only=args.primary_only,
        sensor_limit=args.sensor_limit,
    )
    if events.empty:
        raise ValueError("No events selected for trajectory generation")

    hrrr_dir = args.hrrr_dir.resolve()
    hysplit_root = args.hysplit_root.resolve()
    hyts_std = hysplit_root / "exec" / "hyts_std"
    if not hyts_std.exists():
        raise FileNotFoundError(f"Could not find hyts_std at {hyts_std}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    ensure_batch_support_files(args.output_root, hysplit_root)
    task_specs: list[dict[str, object]] = []

    for event_idx, row in events.iterrows():
        end_time = row[args.time_column]
        if not isinstance(end_time, pd.Timestamp):
            end_time = pd.Timestamp(end_time, tz="UTC")

        event_rank = int(row["event_rank"]) if "event_rank" in row and pd.notna(row["event_rank"]) else event_idx + 1
        episode_number = int(row["episode_number"]) if "episode_number" in row and pd.notna(row["episode_number"]) else event_rank
        for duration_hours in durations:
            for height_agl in heights:
                task_specs.append(
                    {
                        "row": row.copy(),
                        "event_time": end_time,
                        "event_rank": event_rank,
                        "episode_number": episode_number,
                        "height_agl": height_agl,
                        "duration_hours": duration_hours,
                    }
                )

    manifest_rows: list[dict[str, object]] = []
    if args.jobs == 1:
        for spec in task_specs:
            manifest_rows.append(
                run_hysplit_task(
                    hyts_std=hyts_std,
                    row=spec["row"],
                    event_time=spec["event_time"],
                    event_rank=spec["event_rank"],
                    episode_number=spec["episode_number"],
                    time_column=args.time_column,
                    height_agl=spec["height_agl"],
                    duration_hours=spec["duration_hours"],
                    hrrr_dir=hrrr_dir,
                    output_root=args.output_root,
                    dry_run=args.dry_run,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            futures = [
                executor.submit(
                    run_hysplit_task,
                    hyts_std,
                    spec["row"],
                    spec["event_time"],
                    spec["event_rank"],
                    spec["episode_number"],
                    args.time_column,
                    spec["height_agl"],
                    spec["duration_hours"],
                    hrrr_dir,
                    args.output_root,
                    args.dry_run,
                )
                for spec in task_specs
            ]
            for future in as_completed(futures):
                manifest_rows.append(future.result())

    manifest = pd.DataFrame(manifest_rows)
    manifest = manifest.sort_values(
        ["event_time_utc", "sensor_index", "duration_hours", "height_agl_m"]
    ).reset_index(drop=True)
    manifest_path = args.output_root / "trajectory_manifest.csv"
    manifest.to_csv(manifest_path, index=False)

    print(f"Loaded {len(events):,} receptor events from {args.events_csv}")
    print(f"Durations: {durations}")
    print(f"Heights AGL: {heights}")
    print(f"Concurrent jobs: {args.jobs}")
    print(f"Saved manifest to {manifest_path}")
    print(manifest["status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
