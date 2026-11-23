#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test paired split W^X benchmark ordering and reported median statistics."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "scripts" / "bench-i386-tcg.py"
SPEC = importlib.util.spec_from_file_location("bench_i386_tcg", BENCHMARK)
assert SPEC is not None and SPEC.loader is not None
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


class SplitWxComparisonTests(unittest.TestCase):
    def test_interleaved_modes_and_medians(self) -> None:
        modes: list[str] = []
        durations = {
            "off": iter((0.100, 0.120, 0.110, 0.130)),
            "on": iter((0.090, 0.095, 0.100, 0.105)),
        }

        def fake_run(qemu, bios, tcg_thread, mode, tb_size, timeout):
            self.assertEqual(qemu, "qemu-test")
            self.assertEqual(tcg_thread, "single")
            self.assertEqual(tb_size, 64)
            self.assertEqual(timeout, 5.0)
            modes.append(mode)
            return next(durations[mode])

        with patch.object(bench, "run_once", side_effect=fake_run):
            results = bench.compare_splitwx_runtime(
                "qemu-test", Path("bios.bin"), "single", 64, 4, 5.0
            )

        self.assertEqual(
            modes, ["off", "on", "on", "off",
                    "off", "on", "on", "off"]
        )
        self.assertAlmostEqual(results["off"][0], 0.115)
        self.assertAlmostEqual(results["on"][0], 0.0975)
        self.assertEqual(len(results["off"][1]), 4)
        self.assertEqual(len(results["on"][1]), 4)

    def test_single_round_preserves_off_then_on_order(self) -> None:
        modes: list[str] = []

        def fake_run(qemu, bios, tcg_thread, mode, tb_size, timeout):
            modes.append(mode)
            return 0.1 if mode == "off" else 0.2

        with patch.object(bench, "run_once", side_effect=fake_run):
            result = bench.compare_splitwx_runtime(
                "qemu-test", Path("bios.bin"), "single", None, 1, 5.0
            )
        self.assertEqual(modes, ["off", "on"])
        self.assertAlmostEqual(result["off"][0], 0.1)
        self.assertAlmostEqual(result["on"][0], 0.2)


if __name__ == "__main__":
    unittest.main()
