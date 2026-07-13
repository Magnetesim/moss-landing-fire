"""Shared helpers for the Moss Landing battery-fire analysis workspace.

Modules:
- ``paths``: repository-relative directories and HYSPLIT root resolution
- ``constants``: fire coordinates, event timestamps, enhancement class scheme
- ``purpleair``: API key loading and robust PurpleAir HTTP requests
- ``hysplit``: bundled ``hysplitdata`` module import
- ``fsutil``: symlink helpers with Windows fallbacks
- ``kriging``: shared kriging, masking, and map-view helpers
"""
