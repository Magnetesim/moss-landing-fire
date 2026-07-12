from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str, relative_path: str, stub_hysplitdata: bool = False):
    if stub_hysplitdata:
        sys.modules.setdefault("hysplitdata", ModuleType("hysplitdata"))
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / relative_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {relative_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase1 = load_script("phase1_sweep_for_tests", "scripts/hysplit/run_phase1_sweep.py")
forward = load_script("forward_dispersion_for_tests", "scripts/hysplit/run_forward_dispersion.py")
manifest_builder = load_script(
    "forward_manifest_for_tests",
    "scripts/hysplit/build_forward_manifest.py",
)
combined_comparator = load_script(
    "combined_comparator_for_tests",
    "scripts/hysplit/compare_combined_to_separate.py",
)
convergence_summary = load_script(
    "particle_convergence_for_tests",
    "scripts/hysplit/summarize_particle_convergence.py",
)
scorer = load_script(
    "score_against_purpleair_for_tests",
    "scripts/hysplit/score_against_purpleair.py",
    stub_hysplitdata=True,
)


class CombinedSweepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ignition = pd.Timestamp("2025-01-16T23:00:00Z")
        self.windows = phase1.build_sample_windows(
            self.ignition,
            [1, 4, 7, 10],
            window_hours=4.0,
            window_step_hours=4.0,
        )
        self.setups = phase1.parse_source_setups(phase1.DEFAULT_SOURCE_SETUPS)

    def test_combined_default_matrix_has_96_physical_runs(self) -> None:
        jobs = phase1.build_jobs(
            ignition_utc=self.ignition,
            source_heights=phase1.parse_float_list(phase1.DEFAULT_SOURCE_HEIGHTS_M),
            release_durations_h=phase1.parse_float_list(phase1.DEFAULT_RELEASE_DURATIONS_H),
            source_setups=self.setups,
            windows=self.windows,
            execution_shape="combined",
        )
        self.assertEqual(96, len(jobs))
        self.assertTrue(all(len(job["sample_windows"]) == 4 for job in jobs))

    def test_separate_default_matrix_preserves_384_runs(self) -> None:
        jobs = phase1.build_jobs(
            ignition_utc=self.ignition,
            source_heights=phase1.parse_float_list(phase1.DEFAULT_SOURCE_HEIGHTS_M),
            release_durations_h=phase1.parse_float_list(phase1.DEFAULT_RELEASE_DURATIONS_H),
            source_setups=self.setups,
            windows=self.windows,
            execution_shape="separate",
        )
        self.assertEqual(384, len(jobs))
        self.assertTrue(all(len(job["sample_windows"]) == 1 for job in jobs))

    def test_cumulative_shape_uses_common_sampling_start(self) -> None:
        jobs = phase1.build_jobs(
            ignition_utc=self.ignition,
            source_heights=[10.0],
            release_durations_h=[12.0],
            source_setups=[self.setups[0]],
            windows=self.windows,
            execution_shape="cumulative",
        )
        self.assertEqual(4, len(jobs))
        starts = [job["sample_windows"][0][1] for job in jobs]
        stops = [job["sample_windows"][0][2] for job in jobs]
        self.assertEqual({self.windows[0][1]}, set(starts))
        self.assertEqual([window[2] for window in self.windows], stops)

    def test_combined_window_envelope_is_4_to_44_hours_after_ignition(self) -> None:
        starts = [window[1] for window in self.windows]
        stops = [window[2] for window in self.windows]
        self.assertEqual(self.ignition + pd.Timedelta(hours=4), min(starts))
        self.assertEqual(self.ignition + pd.Timedelta(hours=44), max(stops))

    def test_combined_run_command_uses_one_multi_period_envelope(self) -> None:
        args = SimpleNamespace(
            run_tag_prefix="test",
            source_lat=36.8044,
            source_lon=-121.7883,
            source_rotation_deg=0.0,
            emission_rate=1.0,
            concentration_level_m=10.0,
            grid_center_lat=36.82,
            grid_center_lon=-121.80,
            grid_spacing_deg="0.01,0.01",
            grid_span_deg="1.40,1.20",
            window_hours=4.0,
            numpar=500,
            maxpar=50000,
            krand=2,
            seed=0,
            plot_styles="county",
            dry_run=False,
            execution_shape="combined",
        )
        setup = {
            "source_geometry": "point",
            "source_footprint_m": "300,120",
            "source_grid_shape": "1,1",
        }
        with tempfile.TemporaryDirectory() as output_root, patch.object(
            phase1.subprocess,
            "run",
            return_value=SimpleNamespace(returncode=0, stdout="ok"),
        ) as run_mock:
            result = phase1.run_case(
                python_exe="python",
                forward_script=Path("run_forward_dispersion.py"),
                output_root=Path(output_root),
                ignition_utc=self.ignition,
                sample_windows=self.windows,
                release_end_utc=self.ignition + pd.Timedelta(hours=12),
                source_height_m=10.0,
                scenario_tag="h10_dur12_pt",
                setup=setup,
                args=args,
            )

        command = run_mock.call_args.args[0]
        option_value = lambda option: command[command.index(option) + 1]
        self.assertEqual("2025-01-17T03:00:00Z", option_value("--sample-start-utc"))
        self.assertEqual("2025-01-18T19:00:00Z", option_value("--sample-stop-utc"))
        self.assertEqual("2025-01-18T19:00:00Z", option_value("--end-utc"))
        self.assertEqual("1,4,7,10", result["window_indices"])
        self.assertEqual(4, result["window_count"])


class ForwardManifestTests(unittest.TestCase):
    def test_combined_manifest_uses_one_isolated_row_per_scenario(self) -> None:
        args = SimpleNamespace(
            ignition_utc="2025-01-16T23:00:00Z",
            source_heights_m="10,25",
            release_durations_h="4",
            source_setups="point|300,120|1,1",
            window_indices="1,4",
            execution_shape="combined",
            window_hours=4.0,
            window_step_hours=4.0,
            source_lat=36.8044,
            source_lon=-121.7883,
            source_rotation_deg=0.0,
            emission_rate=1.0,
            concentration_level_m=10.0,
            grid_center_lat=36.82,
            grid_center_lon=-121.80,
            grid_spacing_deg="0.01,0.01",
            grid_span_deg="1.40,1.20",
            numpar=500,
            maxpar=50000,
            krand=2,
            seed=0,
            replicates=1,
            vary_seed_by_replicate=False,
            plot_styles="county",
            hrrr_dir=PROJECT_ROOT / "hrrr",
            hysplit_root=PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64",
            forward_script=PROJECT_ROOT / "scripts" / "hysplit" / "run_forward_dispersion.py",
            runs_root=PROJECT_ROOT / "hysplit" / "runs" / "test_manifest_rows",
            run_tag_prefix="test",
        )
        rows = manifest_builder.build_rows(args)
        self.assertEqual(2, len(rows))
        self.assertEqual({"1,4"}, {row["logical_window_indices"] for row in rows})
        self.assertEqual(2, len({row["config_hash"] for row in rows}))
        self.assertEqual(2, len({row["row_output_root"] for row in rows}))
        self.assertTrue(all(not str(row["expected_run_dir"]).endswith("pt") for row in rows))

    def test_replicates_have_unique_hashes_and_controlled_seeds(self) -> None:
        args = SimpleNamespace(
            ignition_utc="2025-01-16T23:00:00Z",
            source_heights_m="10",
            release_durations_h="12",
            source_setups="point|300,120|1,1",
            window_indices="10",
            execution_shape="separate",
            window_hours=4.0,
            window_step_hours=4.0,
            source_lat=36.8044,
            source_lon=-121.7883,
            source_rotation_deg=0.0,
            emission_rate=1.0,
            concentration_level_m=10.0,
            grid_center_lat=36.82,
            grid_center_lon=-121.80,
            grid_spacing_deg="0.01,0.01",
            grid_span_deg="1.40,1.20",
            numpar=500,
            maxpar=50000,
            krand=2,
            seed=7,
            replicates=3,
            vary_seed_by_replicate=False,
            plot_styles="county",
            hrrr_dir=PROJECT_ROOT / "hrrr",
            hysplit_root=PROJECT_ROOT / "hysplit" / "install" / "hysplit.v5.4.2_x86_64",
            forward_script=PROJECT_ROOT / "scripts" / "hysplit" / "run_forward_dispersion.py",
            runs_root=PROJECT_ROOT / "hysplit" / "runs" / "test_replicates",
            run_tag_prefix="repeat",
        )
        fixed_rows = manifest_builder.build_rows(args)
        self.assertEqual([7, 7, 7], [row["seed"] for row in fixed_rows])
        self.assertEqual(3, len({row["config_hash"] for row in fixed_rows}))
        args.vary_seed_by_replicate = True
        varied_rows = manifest_builder.build_rows(args)
        self.assertEqual([7, 8, 9], [row["seed"] for row in varied_rows])


class CombinedComparatorTests(unittest.TestCase):
    def test_logical_period_uses_window_index_not_cumulative_envelope(self) -> None:
        combined_row = pd.Series(
            {
                "sample_start_utc": "2025-01-17T03:00:00Z",
                "sample_stop_utc": "2025-01-18T19:00:00Z",
                "sampling_interval_hours": 4.0,
            }
        )
        start, stop = combined_comparator.logical_window_period(combined_row, 4)
        self.assertEqual(pd.Timestamp("2025-01-17T15:00:00Z"), start)
        self.assertEqual(pd.Timestamp("2025-01-17T19:00:00Z"), stop)

    def test_setup_records_randomization_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            setup = Path(directory) / "SETUP.CFG"
            forward.write_setup_cfg(setup, numpar=2000, maxpar=50000, krand=2, seed=7)
            text = setup.read_text(encoding="ascii")
        self.assertIn("numpar = 2000", text)
        self.assertIn("krand = 2", text)
        self.assertIn("seed = 7", text)


class ParticleConvergenceTests(unittest.TestCase):
    def test_rank_summary_detects_stable_top_scenarios(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {}
            for count, scores in ((500, [0.5, 0.4, 0.3]), (2000, [0.51, 0.39, 0.31]), (10000, [0.52, 0.41, 0.29])):
                path = root / f"n{count}.csv"
                pd.DataFrame(
                    {"scenario_id": ["a", "b", "c"], "mean_total_score": scores}
                ).to_csv(path, index=False)
                paths[count] = path
            long = convergence_summary.load_scenarios(paths)
            stability = convergence_summary.scenario_stability(long)
            pairs = convergence_summary.pairwise_rank_metrics(long, top_k=2)
        self.assertEqual(9, len(long))
        self.assertEqual(0, int(stability["rank_range"].max()))
        self.assertTrue(all(pair["spearman_rho"] == 1.0 for pair in pairs))
        self.assertTrue(all(pair["top_k_overlap"] == 2 for pair in pairs))


class CdumpPeriodSelectionTests(unittest.TestCase):
    @staticmethod
    def grid(index: int, start_hour: int, stop_hour: int) -> SimpleNamespace:
        base = datetime(2025, 1, 17, tzinfo=timezone.utc)
        return SimpleNamespace(
            time_index=index,
            starting_datetime=base + pd.Timedelta(hours=start_hour),
            ending_datetime=base + pd.Timedelta(hours=stop_hour),
        )

    def setUp(self) -> None:
        self.cdump = SimpleNamespace(
            grids=[
                self.grid(0, 0, 4),
                self.grid(1, 4, 8),
                self.grid(2, 8, 12),
            ]
        )

    def test_selects_exact_period_by_timestamp(self) -> None:
        selected = scorer.select_time_index(
            self.cdump,
            "2025-01-17T04:00:00Z",
            "2025-01-17T08:00:00Z",
        )
        self.assertEqual(1, selected)

    def test_legacy_no_timestamp_behavior_selects_last_period(self) -> None:
        self.assertEqual(2, scorer.select_time_index(self.cdump))

    def test_missing_period_is_an_explicit_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "Available periods"):
            scorer.select_time_index(
                self.cdump,
                "2025-01-17T05:00:00Z",
                "2025-01-17T09:00:00Z",
            )

    def test_manifest_combined_window_indices_are_expanded(self) -> None:
        row = pd.Series({"window_indices": "1,4,7,10"})
        self.assertEqual([1, 4, 7, 10], scorer.manifest_window_indices(row, {}))

    def test_cluster_logical_window_indices_are_expanded(self) -> None:
        row = pd.Series({"logical_window_indices": "1,4,7,10"})
        self.assertEqual([1, 4, 7, 10], scorer.manifest_window_indices(row, {}))

    def test_cluster_merged_manifest_columns_are_normalized(self) -> None:
        manifest = pd.DataFrame(
            [
                {"row_status": "completed", "row_run_dir": "/scratch/good"},
                {"row_status": "failed", "row_run_dir": "/scratch/bad"},
            ]
        )
        prepared = scorer.prepare_manifest_for_scoring(manifest)
        self.assertEqual(1, len(prepared))
        self.assertEqual("/scratch/good", prepared.iloc[0]["run_dir"])


if __name__ == "__main__":
    unittest.main()
