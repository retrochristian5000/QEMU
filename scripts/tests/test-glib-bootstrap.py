#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Unit checks for the GLib bootstrap without downloading or building GLib."""
import argparse
import importlib.util
import json
import signal
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
    def test_signal_diagnostics(self):
        direct = subprocess.CalledProcessError(-signal.SIGSEGV,
                                               ["clang", "file name.c"])
        self.assertTrue(glib.is_signal_failure(direct))
        self.assertIn("signal 11 (SIGSEGV)", glib.describe_failure(direct))
        self.assertIn("'file name.c'", glib.describe_failure(direct))
        wrapped = subprocess.CalledProcessError(128 + signal.SIGSEGV,
                                                ["sccache", "clang"])
        self.assertTrue(glib.is_signal_failure(wrapped))
        self.assertIn("possible wrapped SIGSEGV", glib.describe_failure(wrapped))
        ordinary = subprocess.CalledProcessError(1, ["cc"])
        self.assertFalse(glib.is_signal_failure(ordinary))
        self.assertIn("status 1", glib.describe_failure(ordinary))

    def test_auto_probe_signal_does_not_fall_back(self):
        args = argparse.Namespace(mode="auto", cc="cc", ar="ar",
                                  pkg_config="pkg-config", cflags="", ldflags="",
                                  consumer_cflags="", consumer_ldflags="")
        for code in (-signal.SIGSEGV, 128 + signal.SIGSEGV):
            with self.subTest(code=code), \
                 mock.patch.dict(glib.os.environ, {"WHP_GLIB_TESTS": "0"}), \
                 mock.patch.object(glib.platform, "system", return_value="Darwin"), \
                 mock.patch.object(glib, "command", side_effect=lambda v: [v]), \
                 mock.patch.object(glib, "probe", side_effect=
                                   subprocess.CalledProcessError(code, ["cc"])), \
                 mock.patch.object(glib, "pinned_source") as pinned:
                with self.assertRaises(subprocess.CalledProcessError):
                    glib.bootstrap(args)
                pinned.assert_not_called()

    def test_tool_identity_does_not_hide_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            tool = Path(directory) / "clang"
            tool.touch()
            with mock.patch.object(glib, "run", side_effect=
                                   subprocess.CalledProcessError(-signal.SIGSEGV,
                                                                 [str(tool)])):
                with self.assertRaises(subprocess.CalledProcessError):
                    glib.tool_identity([str(tool)])

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

    def test_explicit_glib_flags_rejected(self):
        for flags in (
            ["-I/opt/homebrew/include/glib-2.0"],
            ["-isystem", "/opt/homebrew/opt/glib/include"],
            ["-L/opt/homebrew/Cellar/glib/2.88/lib"],
            ["-lglib-2.0"],
            ["-Wl,-lglib-2.0"],
            ["-l:libglib-2.0.so"],
            ["-Wl,-rpath,/opt/homebrew/opt/glib/lib"],
            ["/usr/lib/libgobject-2.0.so.0"],
        ):
            with self.subTest(flags=flags):
                with self.assertRaisesRegex(RuntimeError, "conflicts"):
                    glib.validate_managed_flags(flags, "test flags")
        glib.validate_managed_flags(
            ["-arch", "arm64e", "-O2", "-I/opt/homebrew/include",
             "-L/opt/homebrew/lib", "-lffi", "-lz", "-flto=thin"],
            "test flags",
        )

    def test_header_origin_rejects_same_version_foreign_headers(self):
        with tempfile.TemporaryDirectory(prefix="glib test ") as directory:
            prefix = Path(directory)
            header = prefix / "include/glib-2.0/glib.h"
            config = prefix / "lib/glib-2.0/include/glibconfig.h"
            def escape(path):
                return str(path).replace(" ", "\\ ")
            good = "whp-glib-probe: " + escape(header) + " " + escape(config)
            glib.verify_header_origin(good, prefix)
            bad = "whp-glib-probe: /external/glib.h " + escape(config)
            with self.assertRaisesRegex(RuntimeError, "header glib.h"):
                glib.verify_header_origin(bad, prefix)
            with self.assertRaisesRegex(RuntimeError, "header glibconfig.h"):
                glib.verify_header_origin(
                    "whp-glib-probe: " + escape(header), prefix
                )

    def test_managed_probe_rejects_wrong_headers_before_linking(self):
        prefix = Path("/private")
        def command(argv, **kwargs):
            if argv[0] == "pkg-config":
                if argv[1] == "--exists":
                    return ""
                if argv[1] == "--variable=pcfiledir":
                    return "/private/lib/pkgconfig"
                if argv[1] == "--cflags":
                    return "-I/private/include/glib-2.0"
                if argv[1] == "--libs":
                    return "-L/private/lib -lglib-2.0"
            if argv[0] == "cc" and "-M" in argv:
                self.assertLess(argv.index("-I/external"),
                                argv.index("-I/private/include/glib-2.0"))
                return ("whp-glib-probe: /external/glib.h "
                        "/private/lib/glib-2.0/include/glibconfig.h")
            self.fail(f"unexpected command before header rejection: {argv}")

        with mock.patch.object(glib, "run", side_effect=command):
            with self.assertRaisesRegex(RuntimeError, "header glib.h"):
                glib.probe(["pkg-config"], ["cc"], ["-I/external"], [], prefix)

    def test_consumer_flags_are_forwarded(self):
        configure = (ROOT / "configure").read_text(encoding="utf-8")
        self.assertIn('--consumer-cflags="$EXTRA_CFLAGS"', configure)
        self.assertIn('--consumer-ldflags="$EXTRA_LDFLAGS"', configure)

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

    def test_managed_profile_excludes_optional_instrumentation(self):
        for option in ("sysprof", "libelf", "oss_fuzz"):
            self.assertIn(f"-D{option}=disabled", glib.MESON_PROFILE)
        for option in ("selinux", "libmount", "xattr", "file_monitor_backend"):
            self.assertFalse(any(arg.startswith(f"-D{option}=")
                                 for arg in glib.MESON_PROFILE))

    def test_wrap_mode_and_cache_reuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = argparse.Namespace(
                mode="1", build_dir=str(root), allow_source_init=True,
                allow_download=True, cc="cc", ar="ar", pkg_config="pkg-config",
                meson="meson", ninja="ninja", cflags="", ldflags="",
                consumer_cflags="", consumer_ldflags="",
            )
            inputs = [{"requirement": "zlib", "pkg_config": "unavailable"}]
            with mock.patch.dict(glib.os.environ, {"WHP_GLIB_TESTS": "0"}), \
                 mock.patch.object(glib.platform, "system", return_value="Darwin"), \
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
                identity = json.loads(marker.read_text())
                self.assertEqual(identity["inputs"], inputs)
                self.assertEqual(identity["schema"], 4)
                args.consumer_cflags = "-I/opt/homebrew/include/glib-2.0"
                with self.assertRaisesRegex(RuntimeError, "conflicts"):
                    glib.bootstrap(args)
                args.consumer_cflags = ""
                self.assertEqual(identity["profile"], list(glib.MESON_PROFILE))
                for option in identity["profile"]:
                    self.assertIn(option, setup)
                args.allow_download = False
                args.allow_source_init = False
                run.reset_mock()
                self.assertEqual(glib.bootstrap(args), prefix)
                run.assert_not_called()
                with mock.patch.object(glib, "probe", side_effect=
                                       subprocess.CalledProcessError(-signal.SIGSEGV,
                                                                     ["probe"])):
                    with self.assertRaises(subprocess.CalledProcessError):
                        glib.bootstrap(args)
                self.assertTrue(marker.is_file())
                run.assert_not_called()
                with mock.patch.dict(glib.os.environ, {"WHP_GLIB_TESTS": "1"}):
                    tested_prefix = glib.bootstrap(args)
                self.assertNotEqual(tested_prefix, prefix)
                tested_identity = json.loads(
                    (tested_prefix / ".whp-glib-bootstrap").read_text())
                self.assertIn("-Dtests=true", tested_identity["profile"])
                calls = [call.args[0] for call in run.call_args_list]
                test_call = next(call for call in calls if call[:2] ==
                                 ["meson", "test"])
                self.assertEqual(test_call[-2:], ["atomic", "thread"])
                self.assertLess(calls.index(test_call),
                                next(i for i, call in enumerate(calls)
                                     if call[:2] == ["meson", "install"]))
                run.reset_mock()
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
