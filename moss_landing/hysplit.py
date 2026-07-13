"""Import helpers for the NOAA-bundled ``hysplitdata`` Python module."""

from __future__ import annotations

import sys
from pathlib import Path

from moss_landing.paths import hysplit_root


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
