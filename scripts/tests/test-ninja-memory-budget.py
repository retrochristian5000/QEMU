#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""WHP Ninja bootstrap memory-budget regression checks."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/ensure-ninja.py"
HOST_TOOLS = ROOT / "scripts/whp-build/host-tools.sh"


def load_helper():
    spec = importlib.util.spec_from_file_location("whp_ninja_memory_test", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NinjaMemoryBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = load_helper()

    def test_default_is_two_jobs(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.helper.bootstrap_job_limit(), 2)

    def test_host_job_budget_can_lower_not_raise_default(self):
        for value, expected in (("1", 1), ("2", 2), ("16", 2)):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"JOBS": value}, clear=True):
                    self.assertEqual(self.helper.bootstrap_job_limit(), expected)

    def test_explicit_bootstrap_override_is_authoritative(self):
        with patch.dict(os.environ,
                        {"JOBS": "1", "NINJA_BOOTSTRAP_JOBS": "3"},
                        clear=True):
            self.assertEqual(self.helper.bootstrap_job_limit(), 3)

    def test_malformed_budgets_are_rejected(self):
        for value in ("0", "-1", "1.5", "2 workers", "2147483648"):
            with self.subTest(value=value):
                with patch.dict(os.environ, {"NINJA_BOOTSTRAP_JOBS": value},
                                clear=True):
                    with self.assertRaises(RuntimeError):
                        self.helper.bootstrap_job_limit()

    def test_ninja_auto_cap_is_only_in_bundled_host_tool_path(self):
        host_tools = HOST_TOOLS.read_text(encoding="utf-8")
        self.assertIn(
            "*/.whp-host-tools/ninja-*/ninja|*/.whp-host-tools/ninja-*/ninja.exe)",
            host_tools,
        )
        self.assertIn("NINJA_AUTO_JOBS=${NINJA_AUTO_JOBS:-2}", host_tools)
        self.assertIn("export NINJA_AUTO_JOBS", host_tools)


if __name__ == "__main__":
    unittest.main()
