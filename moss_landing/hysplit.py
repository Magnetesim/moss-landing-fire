"""Import helpers for the NOAA-bundled ``hysplitdata`` Python module."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from moss_landing.paths import hysplit_root


_cached_hysplitdata: Any | None = None


def import_hysplitdata(root: Path | None = None):
    """Import ``hysplitdata`` from the local HYSPLIT install tree.

    The module ships inside the registered NOAA HYSPLIT distribution under
    ``<install>/python/hysplitdata`` and is not pip-installable, so it is
    loaded by extending ``sys.path``. Honors an existing ``sys.modules``
    entry, which lets tests stub the module.
    """
    module_root = (root or hysplit_root()) / "python" / "hysplitdata"
    if str(module_root) not in sys.path:
        sys.path.insert(0, str(module_root))
    try:
        import hysplitdata  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(f"Could not import hysplitdata from {module_root}") from exc
    return hysplitdata


def get_hysplitdata():
    """Return the NOAA ``hysplitdata`` module, importing it on first use.

    Command-line tools use this lazy accessor so argument parsing and
    ``--help`` remain available on machines where the registered HYSPLIT
    distribution has not been installed.
    """
    global _cached_hysplitdata
    if _cached_hysplitdata is None:
        _cached_hysplitdata = import_hysplitdata()
    return _cached_hysplitdata
