#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline tests for safe Autoconf rebuild and interrupted-install recovery."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "whp_autoconf_recovery", ROOT / "scripts/ensure-autoconf.py"
)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot import Autoconf bootstrap helper")
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class AutoconfRecoveryTest(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="whp-autoconf-recovery-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.prefix = self.root / "deps/autoconf"
        self.backup = self.root / "bootstrap/autoconf-previous-install"

    def old_install(self, path):
        path.mkdir(parents=True, exist_ok=True)
        (path / ".whp-autoconf-bootstrap").write_text("old\n")
        (path / "healthy").write_text("old-suite")

    def mocked_inputs(self, runner):
        # Exercise the real directory transaction without running a large
        # toolchain build. No version banners or fake M4 are admitted by QEMU.
        return patch.multiple(
            helper,
            select_bootstrap_git=lambda: "/dummy/git",
            ensure_source=lambda git: "revision",
            select_automake_pair=lambda: ("/dummy/automake", "/dummy/aclocal"),
            select_gnu_m4=lambda: "/dummy/m4",
            select_seed_perl=lambda: "/dummy/perl",
            select_gnu_make=lambda: "/dummy/make",
            select_seed_sed=lambda: "/dummy/sed",
            select_seed_ln=lambda: "/dummy/ln",
            select_bootstrap_text_tool=lambda name: f"/dummy/{name}",
            select_native_sdk=lambda root: None,
            select_native_cc=lambda root: "/dummy/cc",
            select_bootstrap_cflags=lambda *args: "",
            select_bootstrap_ldflags=lambda *args, **kwargs: "",
            explicit_tool=lambda name: None,
            tool=lambda name: "/dummy/mktemp",
            marker_text=lambda *args: "new\n",
            suite_usable=lambda path, **kwargs: (path / "healthy").is_file(),
            copy_source=lambda rev, path, git: path.mkdir(parents=True),
            run_logged=runner,
        )

    def test_failed_install_restores_previous(self):
        self.old_install(self.prefix)

        def fail(command, *, cwd, env):
            if command[1].endswith("/bootstrap"):
                (cwd / "configure").touch()
            elif "install-binSCRIPTS" in command:
                self.prefix.mkdir(parents=True)
                (self.prefix / "partial").touch()
                raise RuntimeError("simulated install failure")

        with self.mocked_inputs(fail):
            with self.assertRaisesRegex(RuntimeError, "simulated install failure"):
                helper.bootstrap(self.root)
        self.assertEqual((self.prefix / "healthy").read_text(), "old-suite")
        self.assertEqual(
            (self.prefix / ".whp-autoconf-bootstrap").read_text(), "old\n"
        )
        self.assertFalse((self.prefix / "partial").exists())
        self.assertFalse(self.backup.exists())

    def test_interrupted_rebuild_recovers_previous(self):
        self.old_install(self.backup)
        self.prefix.mkdir(parents=True)
        (self.prefix / "partial").touch()

        def fail(command, *, cwd, env):
            raise RuntimeError("simulated restart failure")

        with self.mocked_inputs(fail):
            with self.assertRaisesRegex(RuntimeError, "simulated restart failure"):
                helper.bootstrap(self.root)
        self.assertEqual((self.prefix / "healthy").read_text(), "old-suite")
        self.assertFalse((self.prefix / "partial").exists())
        self.assertFalse(self.backup.exists())

    def test_success_commits_replacement(self):
        self.old_install(self.prefix)

        def succeed(command, *, cwd, env):
            if command[1].endswith("/bootstrap"):
                self.assertEqual(env["AWK"], "/dummy/awk")
                self.assertEqual(env["GREP"], "/dummy/grep")
                self.assertEqual(env["LN_S"], "ln -s")
                seed_bin = Path(env["PATH"].split(":")[0])
                self.assertEqual((seed_bin / "awk").readlink(), Path("/dummy/awk"))
                self.assertEqual((seed_bin / "grep").readlink(), Path("/dummy/grep"))
                self.assertEqual((seed_bin / "ln").readlink(), Path("/dummy/ln"))
                (cwd / "configure").touch()
            elif "install-binSCRIPTS" in command:
                self.prefix.mkdir(parents=True)
                (self.prefix / "healthy").write_text("new-suite")

        with self.mocked_inputs(succeed):
            installed = helper.bootstrap(self.root)
        self.assertEqual(installed, self.prefix)
        self.assertEqual((self.prefix / "healthy").read_text(), "new-suite")
        self.assertEqual(
            (self.prefix / ".whp-autoconf-bootstrap").read_text(), "new\n"
        )
        self.assertFalse(self.backup.exists())


if __name__ == "__main__":
    unittest.main()
