# HYSPLIT Setup

This repository does **not** include the HYSPLIT executables or the gated dispersion-model download bundle.

Those files must be obtained separately from the NOAA HYSPLIT distribution site using your own registration/download process.

## Expected Local Layout

The scripts in this repo expect a local install under:

```text
hysplit/install/hysplit.v5.4.2_x86_64/
```

In practice that means after downloading/extracting HYSPLIT yourself, the install tree should contain paths like:

```text
hysplit/install/hysplit.v5.4.2_x86_64/exec/
hysplit/install/hysplit.v5.4.2_x86_64/bdyfiles/
hysplit/install/hysplit.v5.4.2_x86_64/python/hysplitdata/
```

## Also Required

- HRRR meteorology files in `hrrr/`
- local PurpleAir API key in `purple_air_api.txt`

## Notes

- `hysplit/install/` is ignored by Git
- `hysplit/runs/` is ignored by Git
- if you change the local HYSPLIT install path, update the defaults in the HYSPLIT scripts accordingly
