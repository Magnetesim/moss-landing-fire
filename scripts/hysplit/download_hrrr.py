#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "hrrr"
DEFAULT_HOST = "ftp.arl.noaa.gov"
DEFAULT_REMOTE_DIR = "/pub/archives/hrrr"


@dataclass(frozen=True)
class MetFile:
    start: pd.Timestamp
    filename: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download archived ARL-format HRRR files for HYSPLIT from the NOAA ARL FTP archive."
    )
    parser.add_argument("--start-utc", required=True, help="UTC start time, e.g. 2025-01-16T23:00:00Z")
    parser.add_argument("--end-utc", required=True, help="UTC end time, e.g. 2025-01-18T06:00:00Z")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--host", default=DEFAULT_HOST, help="FTP host. Default matches current HYSPLIT archive config.")
    parser.add_argument(
        "--remote-dir",
        default=DEFAULT_REMOTE_DIR,
        help="Remote HRRR archive directory on the FTP host.",
    )
    parser.add_argument(
        "--email",
        default="anonymous@example.com",
        help="FTP password/email string for anonymous access.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Redownload files that already exist locally.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print required files and planned commands without downloading.",
    )
    return parser.parse_args()


def floor_to_hrrr_block(ts: pd.Timestamp) -> pd.Timestamp:
    hour = (ts.hour // 6) * 6
    return ts.floor("D") + pd.Timedelta(hours=hour)


def hrrr_filename(block_start: pd.Timestamp) -> str:
    return f"{block_start:%Y%m%d}_{block_start:%H}-{block_start.hour + 5:02d}_hrrr"


def required_met_files(start_time: pd.Timestamp, end_time: pd.Timestamp) -> list[MetFile]:
    block_start = floor_to_hrrr_block(start_time)
    block_end = floor_to_hrrr_block(end_time)
    files: list[MetFile] = []
    current = block_start
    while current <= block_end:
        files.append(MetFile(start=current, filename=hrrr_filename(current)))
        current += pd.Timedelta(hours=6)
    return files


def require_program(name: str) -> str:
    resolved = shutil.which(name)
    if resolved is None:
        raise FileNotFoundError(
            f"Required program {name!r} not found on PATH. Install it first, e.g. `sudo apt install lftp`."
        )
    return resolved


def download_with_lftp(
    lftp_bin: str,
    host: str,
    remote_dir: str,
    email: str,
    filename: str,
    output_dir: Path,
) -> None:
    script = (
        f"open -u anonymous,{email} {host}; "
        f"cd {remote_dir}; "
        f"lcd {output_dir}; "
        f"get {filename}; "
        "bye"
    )
    subprocess.run([lftp_bin, "-e", script], check=True)


def main() -> None:
    args = parse_args()
    start_utc = pd.Timestamp(args.start_utc, tz="UTC")
    end_utc = pd.Timestamp(args.end_utc, tz="UTC")
    if end_utc < start_utc:
        raise ValueError("--end-utc must be after --start-utc")

    files = required_met_files(start_utc, end_utc)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Host: {args.host}")
    print(f"Remote dir: {args.remote_dir}")
    print(f"Output dir: {args.output_dir}")
    print("Required HRRR files:")
    for met in files:
        print(f"  {met.filename}")

    if args.dry_run:
        return

    lftp_bin = require_program("lftp")

    for met in files:
        output_path = args.output_dir / met.filename
        if output_path.exists() and not args.overwrite:
            print(f"Skipping existing file: {output_path.name}")
            continue
        print(f"Downloading: {met.filename}")
        if args.dry_run:
            continue
        download_with_lftp(
            lftp_bin=lftp_bin,
            host=args.host,
            remote_dir=args.remote_dir,
            email=args.email,
            filename=met.filename,
            output_dir=args.output_dir,
        )


if __name__ == "__main__":
    main()
