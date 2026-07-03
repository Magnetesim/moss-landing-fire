# Local Data Setup

This repository intentionally excludes large or machine-specific runtime data.

## PurpleAir API Key

The PurpleAir API key is local-only:

```text
purple_air_api.txt
```

Create it from the example file on each machine:

```bash
cp purple_air_api.txt.example purple_air_api.txt
```

Then paste the actual API key into `purple_air_api.txt`.

## HRRR Meteorology

HYSPLIT forward and backward runs use ARL-format HRRR meteorology files from the NOAA ARL archive.

Source:

```text
ftp://ftp.arl.noaa.gov/pub/archives/hrrr/
```

Local destination expected by the scripts:

```text
hrrr/
```

The files are 6-hour blocks named like:

```text
YYYYMMDD_HH-HH_hrrr
```

Example:

```text
20250117_00-05_hrrr
```

### Full Moss Landing Working Set

The current local workspace used these files for the January 16-18, 2025 Moss Landing workflows:

```text
20250116_00-05_hrrr
20250116_06-11_hrrr
20250116_12-17_hrrr
20250116_18-23_hrrr
20250117_00-05_hrrr
20250117_06-11_hrrr
20250117_12-17_hrrr
20250117_18-23_hrrr
20250118_00-05_hrrr
20250118_06-11_hrrr
20250118_12-17_hrrr
20250118_18-23_hrrr
```

Download command for the full set:

```bash
./.venv/bin/python scripts/hysplit/download_hrrr.py \
  --start-utc 2025-01-16T00:00:00Z \
  --end-utc 2025-01-18T23:00:00Z
```

### Minimum Forward-Sweep Set

For the current phase-1 forward comparisons from ignition through the Jan 18 06Z window, the smaller required set is:

```text
20250116_18-23_hrrr
20250117_00-05_hrrr
20250117_06-11_hrrr
20250117_12-17_hrrr
20250117_18-23_hrrr
20250118_00-05_hrrr
20250118_06-11_hrrr
```

Download command for that smaller set:

```bash
./.venv/bin/python scripts/hysplit/download_hrrr.py \
  --start-utc 2025-01-16T23:00:00Z \
  --end-utc 2025-01-18T06:00:00Z
```

Use `--dry-run` to print the exact file list without downloading:

```bash
./.venv/bin/python scripts/hysplit/download_hrrr.py \
  --start-utc 2025-01-16T00:00:00Z \
  --end-utc 2025-01-18T23:00:00Z \
  --dry-run
```

The downloader uses `lftp`, so on Ubuntu/WSL install it with:

```bash
sudo apt install lftp
```

## HYSPLIT

The HYSPLIT executables and support files are local-only because the dispersion bundle is distributed through NOAA's registration/download process.

Expected local layout:

```text
hysplit/install/hysplit.v5.4.2_x86_64/
```

See:

```text
hysplit/README.md
```

## Generated Outputs

These are local/generated and are not stored in Git:

```text
figures/
report/images/
hysplit/runs/
report/moss_landing_progress_report.pdf
```

Regenerate selected report figures with:

```bash
./.venv/bin/python scripts/report/render_key_figures.py
```
