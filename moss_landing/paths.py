"""Repository-relative paths shared by all scripts.

The package is installed editable from the repository root, so
``PROJECT_ROOT`` is the directory containing ``pyproject.toml``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data" / "purple_air"
FIGURES_DIR = PROJECT_ROOT / "figures" / "visualization"
KRIGING_DIR = FIGURES_DIR / "kriging"
HRRR_DIR = PROJECT_ROOT / "hrrr"

DEFAULT_HYSPLIT_ROOT = PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64"


def hysplit_root() -> Path:
    """HYSPLIT install root, overridable with the HYSPLIT_ROOT environment variable."""
    return Path(os.environ.get("HYSPLIT_ROOT", DEFAULT_HYSPLIT_ROOT))


def set_mpl_cache() -> None:
    """Point matplotlib's cache at a writable temp directory.

    Call before the first ``import matplotlib``. Replaces the hard-coded
    ``/tmp/matplotlib`` used on cluster nodes with a per-platform temp path.
    """
    cache = Path(tempfile.gettempdir()) / "matplotlib"
    os.environ.setdefault("MPLCONFIGDIR", str(cache))
