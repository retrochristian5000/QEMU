#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check C dialect admission without a QEMU source build."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts/check-c-standard.py"
spec = importlib.util.spec_from_file_location("whp_c_standard", PROBE)
assert spec is not None and spec.loader is not None
standard_probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(standard_probe)


class CStandardTests(unittest.TestCase):
    def setUp(self):
        self.env = os.environ.copy()
        for key in ("CFLAGS", "CPPFLAGS", "OBJCFLAGS", "CXXFLAGS"):
            self.env.pop(key, None)
        work = tempfile.TemporaryDirectory(prefix="whp-c-standard-tests-")
        self.addCleanup(work.cleanup)
        self.work = Path(work.name)

    def run_probe(self, compiler: str, standard: str, env=None):
        return subprocess.run(
            [sys.executable, str(PROBE), "--compiler", compiler,
             "--standard", standard, "--check"],
            env=self.env if env is None else env, capture_output=True,
            text=True, timeout=45, check=False,
        )

    def test_invalid_standard(self):
        p = self.run_probe("cc", "gnu89")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("unsupported C standard", p.stderr)

    def test_global_standard_flags_rejected(self):
        for variable, flags in (
            ("CFLAGS", "-O2 -std=gnu99"),
            ("CPPFLAGS", "-std=c23 -DTEST"),
            ("OBJCFLAGS", "-ansi"),
            ("CXXFLAGS", "-std=gnu++17"),
        ):
            with self.subTest(variable=variable):
                p = self.run_probe("cc", "gnu11", {**self.env, variable: flags})
                self.assertNotEqual(p.returncode, 0)
                self.assertIn(variable, p.stderr)
                self.assertIn("component-owned", p.stderr)

    def test_fake_compiler_cannot_admit_by_exit_status(self):
        fake = self.work / "banner-only"
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
        p = self.run_probe(str(fake), "gnu11")
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("no object file produced", p.stderr)

    def test_native_dialects(self):
        cc = shutil.which("cc")
        if not cc:
            self.skipTest("C compiler unavailable")
        for standard in ("c99", "gnu99", "c11", "gnu11", "c17", "gnu17",
                         "c23", "gnu23"):
            with self.subTest(standard=standard):
                p = self.run_probe(cc, standard)
                if p.returncode:
                    self.assertIn("not supported", p.stderr)
                else:
                    self.assertIn("supported", p.stdout)

    def test_actual_qemu_integration(self):
        prepare = (ROOT / "scripts/whp-build/prepare-build.bash").read_text()
        configure = (ROOT / "scripts/whp-build/configure.bash").read_text()
        portable = (ROOT / "scripts/whp-build/portable-build.py").read_text()
        llvm = (ROOT / "scripts/bootstrap-native-clang.bash").read_text()
        libisofs = (ROOT / "scripts/ensure-libisofs.py").read_text()
        self.assertIn("reject_global_language_standard_flags", prepare)
        self.assertIn("check-c-standard.py", configure)
        self.assertIn('QEMU_C_STANDARD"', configure)
        self.assertIn("'--standard', values['QEMU_C_STANDARD']", portable)
        self.assertIn('LIBISOFS_C_STANDARD = "gnu11"', libisofs)
        self.assertIn("unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS", llvm)
        self.assertNotIn("-std=c23", llvm)


if __name__ == "__main__":
    unittest.main()
