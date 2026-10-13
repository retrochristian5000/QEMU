#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline contract tests for LLDB crash capture; no macOS or debugserver needed."""

from pathlib import Path
import importlib.util
import os
import subprocess
import tempfile
import unittest
from unittest import mock


RUNNER = Path(__file__).resolve().parents[1] / "whp-lldb-autodebug.py"
spec = importlib.util.spec_from_file_location("whp_lldb_autodebug", RUNNER)
assert spec is not None and spec.loader is not None
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class AutoDebugTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory(prefix="whp-lldb-contract-")
        self.addCleanup(self.root.cleanup)
        self.dir = Path(self.root.name)
        self.lldb = self.dir / "lldb"
        self.lldb.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.lldb.chmod(0o700)

    def test_crash_collects_pac_registers_and_private_report(self):
        result = subprocess.CompletedProcess(
            [], 0,
            "Process 1 stopped\nstop reason = EXC_BAD_ACCESS\n"
            "frame #0: libsystem_c.dylib\n",
            "",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=result) as call:
            status, report = runner.capture(
                self.lldb, ["/bin/false"], "arm64e/healthy",
                self.dir / "reports", 5,
            )
        self.assertEqual(status, 1)
        self.assertTrue(report.is_file())
        self.assertEqual(report.stat().st_mode & 0o777, 0o600)
        self.assertIn("stop reason = EXC_BAD_ACCESS", report.read_text())
        self.assertIn("x8 x16 x17 x22", " ".join(call.call_args.args[0]))
        self.assertIn("--one-line-on-crash", call.call_args.args[0])
        self.assertEqual(call.call_args.args[0][-2:], ["--", "/bin/false"])

    def test_clean_exit_not_marked_as_crash(self):
        result = subprocess.CompletedProcess(
            [], 0, "Process 1 exited with status = 0 (0x00000000)\n", "",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=result):
            status, report = runner.capture(
                self.lldb, ["/bin/true"], "startup", self.dir, 5,
            )
        self.assertEqual(status, 0)
        self.assertIn("target_failed=False", report.read_text())

    def test_nonzero_program_exit_is_not_silent_success(self):
        result = subprocess.CompletedProcess(
            [], 0, "Process 1 exited with status = 9 (0x00000009)\n", "",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=result):
            status, _ = runner.capture(
                self.lldb, ["/bin/false"], "overflow", self.dir, 5,
            )
        self.assertEqual(status, 1)

    def test_failed_debugger_launch_not_treated_as_healthy(self):
        result = subprocess.CompletedProcess(
            [], 0, "", "error: process launch failed: permission denied\\n",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=result):
            status, report = runner.capture(
                self.lldb, ["/bin/true"], "denied", self.dir, 5,
            )
        self.assertEqual(status, 1)
        self.assertIn("permission denied", report.read_text())

    def test_debugger_timeout_keeps_partial_diagnostics(self):
        timeout = subprocess.TimeoutExpired(
            cmd=["lldb"], timeout=5, output=b"frame #0: partial\n",
            stderr=b"debugserver hung\n",
        )
        with mock.patch.object(runner.subprocess, "run", side_effect=timeout):
            status, report = runner.capture(
                self.lldb, ["/bin/false"], "timeout", self.dir, 5,
            )
        self.assertEqual(status, 1)
        self.assertIn("frame #0: partial", report.read_text())
        self.assertIn("debugserver hung", report.read_text())

    def test_missing_lldb_fails_without_system_fallback(self):
        with self.assertRaisesRegex(RuntimeError, "does not exist"):
            runner.capture(self.dir / "absent", ["/bin/true"],
                           "missing", self.dir, 5)


if __name__ == "__main__":
    unittest.main()
