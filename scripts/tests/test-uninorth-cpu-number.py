#!/usr/bin/env python3
"""Guard UniNorth CPU_NUMBER against internal CPU-index/context confusion.

Core99 currently supports a single vCPU.  Revisit the per-CPU hardware
register contract before increasing that machine's max_cpus limit.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class UniNorthCpuNumberTests(unittest.TestCase):
    def test_bootstrap_cpu_contract(self):
        bridge = (ROOT / "hw/pci-host/uninorth.c").read_text(
            encoding="utf-8"
        )
        header = (ROOT / "include/hw/pci-host/uninorth.h").read_text(
            encoding="utf-8"
        )
        board = (ROOT / "hw/ppc/mac_newworld.c").read_text(
            encoding="utf-8"
        )
        qtest = (ROOT / "tests/qtest/macio-timer-test.c").read_text(
            encoding="utf-8"
        )

        self.assertRegex(
            header,
            r'(?m)^#define UNINORTH_CPU_NUMBER_BOOT\s+0x00000000U$',
        )
        self.assertRegex(
            bridge,
            r'case UNINORTH_REG_CPU_NUMBER:\s*/\*[\s\S]*?'
            r'\*/\s*value = UNINORTH_CPU_NUMBER_BOOT;',
        )
        self.assertNotIn("current_cpu->cpu_index", bridge)
        self.assertNotIn('#include "system/cpus.h"', bridge)
        self.assertRegex(
            board,
            r'mc->max_cpus\s*=\s*1;',
            msg="Core99 SMP needs an explicit UniNorth CPU_NUMBER model",
        )
        self.assertIn('"/ppc/uninorth/mac99-boot-cpu"', qtest)
        self.assertIn('test_mac99_uninorth_boot_cpu', qtest)
        self.assertIn('"/ppc/uninorth/sawtooth-registers"', qtest)
        self.assertGreaterEqual(qtest.count("UNINORTH_CPU_NUMBER_BOOT"), 3)

    def test_qtest_built_by_meson(self):
        meson = (ROOT / "tests/qtest/meson.build").read_text(
            encoding="utf-8"
        )
        self.assertIn("'macio-timer-test'", meson)


if __name__ == "__main__":
    unittest.main()
