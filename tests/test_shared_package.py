from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
from shapely.geometry import box

from moss_landing import fsutil, hysplit, kriging, paths, purpleair


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class PathsTests(unittest.TestCase):
    def test_hysplit_root_honors_environment_override(self) -> None:
        expected = Path("/cluster/apps/hysplit")
        with patch.dict(os.environ, {"HYSPLIT_ROOT": str(expected)}):
            self.assertEqual(expected, paths.hysplit_root())


class FilesystemTests(unittest.TestCase):
    def test_refresh_symlink_copy_fallback_replaces_old_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            target.mkdir()
            (target / "current.txt").write_text("current", encoding="utf-8")
            link = root / "latest"
            link.mkdir()
            (link / "stale.txt").write_text("stale", encoding="utf-8")

            with patch("moss_landing.fsutil.os.symlink", side_effect=OSError("disabled")):
                fsutil.refresh_symlink(link, target)

            self.assertEqual("current", (link / "current.txt").read_text(encoding="utf-8"))
            self.assertFalse((link / "stale.txt").exists())

    def test_ensure_bdyfiles_link_copy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            install = root / "install"
            output = root / "output"
            (install / "bdyfiles").mkdir(parents=True)
            output.mkdir()
            (install / "bdyfiles" / "ASCDATA.CFG").write_text("boundary", encoding="utf-8")

            with patch("moss_landing.fsutil.os.symlink", side_effect=OSError("disabled")):
                fsutil.ensure_bdyfiles_link(output, install)

            copied = output / "bdyfiles" / "ASCDATA.CFG"
            self.assertEqual("boundary", copied.read_text(encoding="utf-8"))


class HysplitImportTests(unittest.TestCase):
    def test_lazy_accessor_imports_once(self) -> None:
        sentinel = object()
        with patch.object(hysplit, "_cached_hysplitdata", None), patch.object(
            hysplit, "import_hysplitdata", return_value=sentinel
        ) as importer:
            self.assertIs(sentinel, hysplit.get_hysplitdata())
            self.assertIs(sentinel, hysplit.get_hysplitdata())
            importer.assert_called_once_with()


class PurpleAirTests(unittest.TestCase):
    def test_load_api_key_strips_whitespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            key_path = Path(tmp) / "key.txt"
            key_path.write_text("  secret-key\n", encoding="utf-8")
            self.assertEqual("secret-key", purpleair.load_api_key(key_path))

    def test_get_json_retries_transient_response(self) -> None:
        retry = SimpleNamespace(status_code=429, headers={"Retry-After": "1"})
        success = Mock(status_code=200, headers={})
        success.raise_for_status.return_value = None
        success.json.return_value = {"ok": True}

        with patch("moss_landing.purpleair.requests.get", side_effect=[retry, success]) as get, patch(
            "moss_landing.purpleair.time.sleep"
        ) as sleep:
            payload = purpleair.get_json(
                "https://example.test/sensors",
                "key",
                params={"fields": "pm2.5"},
                timeout=12,
            )

        self.assertEqual({"ok": True}, payload)
        self.assertEqual(2, get.call_count)
        sleep.assert_called_once_with(1.0)


class KrigingHelperTests(unittest.TestCase):
    def test_sensor_exclusions_and_range_validation(self) -> None:
        self.assertEqual({1, 2, 3}, kriging.parse_sensor_exclusions(["1, 2", "3"]))
        self.assertEqual((-122.0, -121.5), kriging.parse_range_arg("-122,-121.5", "--xlim"))
        with self.assertRaises(ValueError):
            kriging.parse_range_arg("2,1", "--xlim")

    def test_pick_window_filters_and_clips_values(self) -> None:
        frame = pd.DataFrame(
            {
                "window_index": [1] * 9,
                "baseline_ok": [True] * 9,
                "sensor_index": range(9),
                "enhancement": [-1.0] + [float(i) for i in range(1, 9)],
                "longitude": np.linspace(-122.0, -121.8, 9),
                "latitude": np.linspace(36.6, 36.8, 9),
            }
        )
        selected = kriging.pick_window(frame, 1, "enhancement", {8})
        self.assertEqual(8, len(selected))
        self.assertEqual(0.0, selected.iloc[0]["enhancement"])

    def test_grid_and_mask_shapes_match(self) -> None:
        boundary = box(-122.0, 36.5, -121.6, 36.7)
        lon_grid, lat_grid = kriging.build_grid(boundary, 80)
        valid, distance = kriging.build_mask(
            lon_grid,
            lat_grid,
            boundary,
            np.array([-121.8]),
            np.array([36.6]),
            distance_mask_km=100.0,
        )
        self.assertEqual((60, 80), lon_grid.shape)
        self.assertEqual(lon_grid.shape, valid.shape)
        self.assertEqual(lon_grid.shape, distance.shape)
        self.assertTrue(valid.any())


class CommandLineHelpTests(unittest.TestCase):
    def test_hysplit_analysis_help_does_not_require_noaa_python_bundle(self) -> None:
        scripts = [
            "scripts/hysplit/build_comparison_mode_sheet.py",
            "scripts/hysplit/build_phase1_comparison_gallery.py",
            "scripts/hysplit/plot_cdump.py",
            "scripts/hysplit/score_against_purpleair.py",
        ]
        clean_env = os.environ.copy()
        clean_env.pop("HYSPLIT_ROOT", None)
        for script in scripts:
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, script, "--help"],
                    cwd=PROJECT_ROOT,
                    env=clean_env,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                self.assertEqual(0, result.returncode, result.stderr)
                self.assertIn("usage:", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
