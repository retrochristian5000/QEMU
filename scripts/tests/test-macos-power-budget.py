#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts" / "job-budget.py"

def load_module():
    spec = importlib.util.spec_from_file_location("whp_job_budget", TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load job-budget.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

class MacOSPowerBudgetTests(unittest.TestCase):
    def test_balanced_reduces_many_core_parallelism(self):
        mod = load_module()
        self.assertEqual(mod.recommended_macos_jobs("balanced", 4), 2)
        self.assertEqual(mod.recommended_macos_jobs("balanced", 8), 4)
        self.assertEqual(mod.recommended_macos_jobs("balanced", 12), 6)
        self.assertEqual(mod.recommended_macos_jobs("balanced", 20), 6)

    def test_eco_and_performance_are_explicit_extremes(self):
        mod = load_module()
        self.assertEqual(mod.recommended_macos_jobs("eco", 12), 2)
        self.assertEqual(mod.recommended_macos_jobs("performance", 12), 12)

    def test_explicit_jobs_override_power_profile(self):
        mod = load_module()
        self.assertEqual(mod.resolve_jobs({"JOBS":"3","MACOS_BUILD_POWER":"eco"},system="Darwin",cpu_count=16),3)

    def test_non_macos_keeps_full_default_parallelism(self):
        mod = load_module()
        self.assertEqual(mod.resolve_jobs({},system="Linux",cpu_count=12),12)

    def test_invalid_values_fail_closed(self):
        mod = load_module()
        with self.assertRaises(ValueError):
            mod.resolve_jobs({"JOBS":"0"},system="Darwin",cpu_count=8)
        with self.assertRaises(ValueError):
            mod.resolve_jobs({"MACOS_BUILD_POWER":"turbo"},system="Darwin",cpu_count=8)

    def test_memory_cap_preserves_cpu_profile_and_explicit_jobs(self):
        mod = load_module()
        for gib, expected in ((4, 1), (8, 2), (16, 5), (32, 6)):
            with self.subTest(gib=gib):
                self.assertEqual(
                    mod.resolve_jobs({"MACOS_BUILD_POWER": "performance"},
                                     system="Darwin", cpu_count=6,
                                     memory_bytes=gib * mod.GIB),
                    expected,
                )
        self.assertEqual(mod.resolve_jobs({}, system="Darwin", cpu_count=6,
                                          memory_bytes=8113733632), 2)
        self.assertEqual(mod.resolve_jobs({}, system="Darwin", cpu_count=2,
                                          memory_bytes=32 * mod.GIB), 2)
        self.assertEqual(mod.resolve_jobs({"JOBS": "6"}, system="Darwin",
                                          cpu_count=6, memory_bytes=4 * mod.GIB), 6)
        self.assertEqual(mod.resolve_jobs({}, system="Linux", cpu_count=6,
                                          memory_bytes=4 * mod.GIB), 6)

    def test_unknown_memory_is_conservative(self):
        mod = load_module()
        self.assertEqual(mod.resolve_jobs({}, system="Darwin", cpu_count=8,
                                          memory_bytes=0), 2)
        self.assertEqual(mod.resolve_jobs({}, system="Darwin", cpu_count=1,
                                          memory_bytes=0), 1)

    def test_macos_memory_detection(self):
        mod = load_module()
        with mock.patch.object(mod.subprocess, "run") as run:
            run.return_value.stdout = "8113733632\n"
            self.assertEqual(mod.macos_usable_memory(), 8113733632)
            self.assertEqual(run.call_args.args[0][-1], "hw.memsize_usable")
            run.reset_mock()
            run.side_effect = [
                mod.subprocess.CalledProcessError(1, "sysctl"),
                mock.Mock(stdout="8589934592\n"),
            ]
            self.assertEqual(mod.macos_usable_memory(), 8589934592)
            self.assertEqual(run.call_args.args[0][-1], "hw.memsize")
            run.side_effect = [mock.Mock(stdout="0"), mock.Mock(stdout="invalid")]
            self.assertEqual(mod.macos_usable_memory(), 0)
            run.side_effect = mod.subprocess.TimeoutExpired("sysctl", 2)
            self.assertEqual(mod.macos_usable_memory(), 0)

    def test_explicit_and_non_darwin_skip_memory_probe(self):
        mod = load_module()
        with mock.patch.object(mod, "macos_usable_memory") as probe:
            self.assertEqual(mod.resolve_jobs({"JOBS": "3"}, system="Darwin",
                                              cpu_count=6), 3)
            self.assertEqual(mod.resolve_jobs({}, system="Linux",
                                              cpu_count=6), 6)
            probe.assert_not_called()

    def test_config_exposes_balanced_default(self):
        config_path = ROOT / "scripts" / "whp-config" / "config.py"
        spec = importlib.util.spec_from_file_location("whp_config_for_power", config_path)
        if spec is None or spec.loader is None:
            raise RuntimeError("could not load WHP config")
        config = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config)
        option = config.OPTION_BY_KEY["MACOS_BUILD_POWER"]
        self.assertEqual(option.default, "balanced")
        self.assertEqual(option.choices, ("eco","balanced","performance"))

if __name__ == "__main__":
    unittest.main()
