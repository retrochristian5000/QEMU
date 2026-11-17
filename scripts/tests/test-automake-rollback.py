#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline tests for managed Automake GNU M4 and installation recovery."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "whp_automake_recovery", ROOT / "scripts/ensure-automake.py"
)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot import Automake bootstrap helper")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class AutomakeRecoveryTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="whp-automake-recovery-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.prefix = self.root / "deps/automake"
        self.backup = self.root / "bootstrap/automake-previous-install"

    def old_install(self, path):
        path.mkdir(parents=True, exist_ok=True)
        (path / ".whp-automake-bootstrap").write_text("old\n")
        (path / "healthy").write_text("old-suite")

    def mocked_inputs(self, runner):
        # Exercise prefix replacement, M4 forwarding, and marker generation
        # with fixed tools; real GNU provider checks stay in gnum4.sh.
        return patch.multiple(
            helper,
            ensure_source=lambda: "revision",
            select_seed_sed=lambda: "/dummy/sed",
            select_seed_perl=lambda: "/dummy/perl",
            select_gnu_m4=lambda: "/dummy/gnu-m4",
            select_seed_autoconf_pair=lambda root: (
                "/dummy/autoconf", "/dummy/autom4te"
            ),
            select_gnu_make=lambda: "/dummy/make",
            select_makeinfo=lambda: "/dummy/makeinfo",
            select_native_sdk=lambda root: None,
            select_native_cc=lambda root: "/dummy/cc",
            select_bootstrap_cflags=lambda *args: "",
            select_bootstrap_ldflags=lambda *args, **kwargs: "",
            explicit_tool=lambda name: None,
            first_line=lambda command: "GNU test tool",
            tolerant_identity=lambda command: "seed test tool",
            automake_pair_usable=lambda path: (path / "healthy").is_file(),
            copy_source=lambda rev, path: path.mkdir(parents=True),
            run_logged=runner,
        )

    def test_failed_install_restores_previous(self):
        self.old_install(self.prefix)

        def fail(command, *, cwd, env):
            if command[1].endswith("/bootstrap"):
                (cwd / "configure").touch()
            elif command[1] == "install":
                self.prefix.mkdir(parents=True)
                (self.prefix / "partial").touch()
                raise RuntimeError("simulated Automake install failure")

        with self.mocked_inputs(fail):
            with self.assertRaisesRegex(RuntimeError, "simulated Automake install failure"):
                helper.bootstrap(self.root)
        self.assertEqual((self.prefix / "healthy").read_text(), "old-suite")
        self.assertEqual(
            (self.prefix / ".whp-automake-bootstrap").read_text(), "old\n"
        )
        self.assertFalse((self.prefix / "partial").exists())
        self.assertFalse(self.backup.exists())

    def test_interrupted_rebuild_restores_previous(self):
        self.old_install(self.backup)
        self.prefix.mkdir(parents=True)
        (self.prefix / "partial").touch()

        def fail(command, *, cwd, env):
            raise RuntimeError("simulated Automake restart failure")

        with self.mocked_inputs(fail):
            with self.assertRaisesRegex(RuntimeError, "simulated Automake restart failure"):
                helper.bootstrap(self.root)
        self.assertEqual((self.prefix / "healthy").read_text(), "old-suite")
        self.assertFalse((self.prefix / "partial").exists())
        self.assertFalse(self.backup.exists())

    def test_success_commits_replacement_and_locks_m4(self):
        self.old_install(self.prefix)
        seen_env = []

        def succeed(command, *, cwd, env):
            seen_env.append(env)
            if command[1].endswith("/bootstrap"):
                self.assertEqual(env["M4"], "/dummy/gnu-m4")
                self.assertEqual(
                    (self.root / "bootstrap/automake/seed-bin/m4").readlink(),
                    Path("/dummy/gnu-m4"),
                )
                (cwd / "configure").touch()
            elif command[1] == "install":
                self.prefix.mkdir(parents=True)
                (self.prefix / "healthy").write_text("new-suite")

        with self.mocked_inputs(succeed):
            installed = helper.bootstrap(self.root)
        self.assertEqual(installed, self.prefix)
        self.assertEqual((self.prefix / "healthy").read_text(), "new-suite")
        marker = (self.prefix / ".whp-automake-bootstrap").read_text()
        self.assertIn("AUTOMAKE_BOOTSTRAP_SCHEMA=6\n", marker)
        self.assertIn("M4_PATH=/dummy/gnu-m4\n", marker)
        self.assertEqual(len(seen_env), 4)
        self.assertFalse(self.backup.exists())

    def test_rejects_unavailable_gnu_m4(self):
        missing = subprocess.CompletedProcess(
            ["/bin/sh", "gnum4.sh", "--print-seed"],
            1, "", "no GNU M4 with trace support",
        )
        with patch.object(helper.subprocess, "run", return_value=missing):
            with self.assertRaisesRegex(RuntimeError, "validated GNU M4"):
                helper.select_gnu_m4()


if __name__ == "__main__":
    unittest.main()
