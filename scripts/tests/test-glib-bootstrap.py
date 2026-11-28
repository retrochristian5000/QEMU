#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit checks for the GLib bootstrap without downloading or building GLib."""
import argparse
import importlib.util
import json
import subprocess
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
    def test_apple_ar_without_version_option(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / "ar"
            tool.touch()
            with mock.patch.object(glib, "run", side_effect=
                                   subprocess.CalledProcessError(1, [str(tool)])):
                result = glib.tool_identity([str(tool)])
            self.assertEqual(result["path"], str(tool.resolve()))
            self.assertEqual(result["version"], "")

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

    def test_missing_pkg_config_provider_is_deferred(self):
        def pkg_config(argv, **kwargs):
            if argv[-1] == "libffi >= 3.0.0":
                raise subprocess.CalledProcessError(1, argv)
            return {"--exists": "", "--modversion": "1.2.3",
                    "--cflags": "-I/host/include -lprovider",
                    "--variable=pcfiledir": "/host/lib/pkgconfig"}[argv[1]]

        with mock.patch.object(glib, "run", side_effect=pkg_config):
            inputs = glib.dependency_inputs(["pkg-config"])
        self.assertEqual(inputs[0], {
            "requirement": "libffi >= 3.0.0", "pkg_config": "unavailable",
        })
        self.assertEqual(inputs[1]["version"], "1.2.3")
        self.assertEqual(inputs[2]["pcfiledir"], "/host/lib/pkgconfig")

    def test_pkg_config_execution_error_is_not_missing_dependency(self):
        with mock.patch.object(glib, "run", side_effect=
                               subprocess.CalledProcessError(2, ["pkg-config"])):
            with self.assertRaises(subprocess.CalledProcessError):
                glib.dependency_inputs(["pkg-config"])

    def test_wrap_mode_and_cache_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                mode="1", build_dir=str(root), allow_source_init=True,
                allow_download=True, cc="cc", ar="ar", pkg_config="pkg-config",
                meson="meson", ninja="ninja", cflags="", ldflags="",
            )
            inputs = [{"requirement": "zlib", "pkg_config": "unavailable"}]
            with mock.patch.object(glib.platform, "system", return_value="Darwin"), \
                 mock.patch.object(glib, "command", side_effect=lambda v: [v]), \
                 mock.patch.object(glib, "tool_identity", side_effect=lambda v: v), \
                 mock.patch.object(glib, "pinned_source", return_value=(root, "a" * 40)), \
                 mock.patch.object(glib, "dependency_inputs", return_value=inputs), \
                 mock.patch.object(glib, "probe"), \
                 mock.patch.object(glib, "run", return_value="") as run:
                prefix = glib.bootstrap(args)
                setup = run.call_args_list[0].args[0]
                self.assertIn("--wrap-mode=default", setup)
                marker = prefix / ".whp-glib-bootstrap"
                self.assertEqual(json.loads(marker.read_text())["inputs"], inputs)
                args.allow_download = False
                args.allow_source_init = False
                run.reset_mock()
                self.assertEqual(glib.bootstrap(args), prefix)
                run.assert_not_called()
                # Invalidate only the fixture's completion marker to force a
                # new setup with downloads disabled.
                marker.unlink()
                self.assertEqual(glib.bootstrap(args), prefix)
                self.assertIn("--wrap-mode=nodownload",
                              run.call_args_list[0].args[0])

    def test_configure_forwards_download_permission(self):
        configure = (ROOT / "configure").read_text(encoding="utf-8")
        block = configure.split("    whp_glib_init=\n", 1)[1]
        block = "    whp_glib_init=\n" + block.split("    whp_glib_prefix=", 1)[0]
        for policy, expected in (
            ("enabled", "--allow-source-init --allow-download"),
            ("disabled", ""),
        ):
            result = subprocess.run(
                ["/bin/sh", "-c", block +
                 'printf "%s %s\\n" "$whp_glib_init" "$whp_glib_download"'],
                env={**glib.os.environ, "download": policy},
                text=True, capture_output=True, check=True,
            )
            self.assertEqual(result.stdout.strip(), expected)

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
