#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
import importlib.util
import pathlib
import unittest

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
