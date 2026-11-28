#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit checks for the GLib bootstrap without downloading or building GLib."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "ensure_glib", ROOT / "scripts/ensure-glib.py")
glib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(glib)


class BootstrapTest(unittest.TestCase):
    def test_native_array(self):
        self.assertEqual(glib.machine_array(["cc", "-arch", "arm64e"]),
                         "['cc', '-arch', 'arm64e']")
        with self.assertRaises(RuntimeError):
            glib.machine_array(["bad\nflag"])

    def test_private_pc_path_preserves_system_search(self):
        with mock.patch.dict(glib.os.environ, {"PKG_CONFIG_PATH": "/system"}):
            self.assertEqual(glib.pc_environment(Path("/private"))[
                "PKG_CONFIG_PATH"], "/private/lib/pkgconfig:/system")
            self.assertEqual(glib.os.environ["PKG_CONFIG_PATH"], "/system")

    def test_wrong_package_origin_fails_before_compilation(self):
        with mock.patch.object(glib, "run", side_effect=["", "/system/pkgconfig"]):
            with self.assertRaisesRegex(RuntimeError, "selected from"):
                glib.probe(["pkg-config"], ["cc"], [], [], Path("/private"))

    def test_missing_source_offline_does_not_initialize(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            with mock.patch.object(glib, "run", return_value=
                                   "160000 commit abc toolchains/glib") as run:
                with self.assertRaisesRegex(RuntimeError, "initialize pinned"):
                    glib.pinned_source(parent, "toolchains/glib", ["git"], False)
                self.assertEqual(run.call_count, 1)

    def test_wrong_revision_never_resets(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            target = parent / "toolchains/glib"
            (target / ".git").mkdir(parents=True)
            with mock.patch.object(glib, "run", side_effect=[
                    "160000 commit abc toolchains/glib", str(target), "def"
            ]) as run:
                with self.assertRaisesRegex(RuntimeError, "differs from"):
                    glib.pinned_source(parent, "toolchains/glib", ["git"], True)
                self.assertEqual(run.call_count, 3)


if __name__ == "__main__":
    unittest.main()
