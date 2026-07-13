"""Filesystem helpers for run directories and convenience pointers."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _copy_fallback(link_path: Path, target: Path) -> None:
    if target.is_dir():
        shutil.copytree(target, link_path, dirs_exist_ok=True)
    else:
        shutil.copy2(target, link_path)


def refresh_symlink(link_path: Path, target: Path) -> None:
    """Point ``link_path`` at ``target``, replacing any existing link.

    Falls back to copying on platforms where symlink creation is not
    permitted (e.g. Windows without Developer Mode); the pointers this
    maintains (``latest/``) are conveniences, so copy semantics suffice.
    """
    if os.path.lexists(link_path):
        try:
            if link_path.is_dir() and not link_path.is_symlink():
                shutil.rmtree(link_path)
            else:
                link_path.unlink()
        except FileNotFoundError:
            pass
    try:
        os.symlink(target, link_path, target_is_directory=target.is_dir())
    except OSError:
        _copy_fallback(link_path, target)


def ensure_bdyfiles_link(output_root: Path, hysplit_root: Path) -> None:
    """Make ``<output_root>/bdyfiles`` resolve to the HYSPLIT boundary files.

    Leaves an existing correct link or real directory in place; replaces a
    stale symlink. Falls back to copying the (small) bdyfiles directory when
    symlinks are unavailable.
    """
    target = hysplit_root / "bdyfiles"
    link_path = output_root / "bdyfiles"
    if link_path.is_symlink():
        try:
            if link_path.resolve(strict=True) == target.resolve(strict=True):
                return
        except FileNotFoundError:
            pass
        link_path.unlink()
    elif os.path.lexists(link_path):
        return
    try:
        os.symlink(target, link_path, target_is_directory=True)
    except OSError:
        _copy_fallback(link_path, target)
