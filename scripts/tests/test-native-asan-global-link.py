#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Host-independent regression tests for the Darwin ASan global-link probe."""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROBE = ROOT / "scripts" / "verify-native-asan-darwin.py"
BOOTSTRAP = ROOT / "scripts" / "bootstrap-native-clang.bash"


def load_probe():
    spec = importlib.util.spec_from_file_location("whp_asanglobals", PROBE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NativeASanGlobalsTests(unittest.TestCase):
    def setUp(self):
        self.module = load_probe()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.prefix = pathlib.Path(self.temp.name)
        self.resource = self.prefix / "clang-resource"
        self.runtime = (
            self.resource / "lib" / "darwin" /
            "libclang_rt.asan_osx_dynamic.dylib"
        )
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_bytes(b"runtime fixture")
        self.calls = []

    def fake_run(self, cmd):
        command = list(cmd)
        self.calls.append(command)
        if command[-1] == "--print-resource-dir":
            return subprocess.CompletedProcess(command, 0, stdout=str(self.resource))
        if "--sections" in command:
            return subprocess.CompletedProcess(
                command, 0, stdout="Section { Name: __asan_globals }\n"
            )
        if "-c" in command:
            return subprocess.CompletedProcess(command, 0, stdout="")
        pathlib.Path(command[-1]).write_bytes(b"linked test fixture")
        return subprocess.CompletedProcess(command, 0, stdout="")

    def verify(self, use_lld=True):
        self.module.verify(
            self.prefix / "clang", self.prefix / "llvm-readobj",
            "arm64", self.prefix / "MacOSX.sdk", "15.0", use_lld,
        )

    def test_native_lld_compiles_macho_globals_and_links_with_asan_driver(self):
        with mock.patch.object(self.module, "run", side_effect=self.fake_run):
            self.verify()
        self.assertEqual(len(self.calls), 4)
        self.assertIn("-fsanitize=address", self.calls[1])
        self.assertIn("-c", self.calls[1])
        self.assertIn("--sections", self.calls[2])
        self.assertIn("-fuse-ld=lld", self.calls[3])
        self.assertIn("-fsanitize=address", self.calls[3])

    def test_apple_ld_path_does_not_force_lld(self):
        with mock.patch.object(self.module, "run", side_effect=self.fake_run):
            self.verify(use_lld=False)
        self.assertNotIn("-fuse-ld=lld", self.calls[-1])
        self.assertIn("-fsanitize=address", self.calls[-1])

    def test_missing_compiler_rt_fails_before_compiling(self):
        self.runtime.unlink()
        with mock.patch.object(self.module, "run", side_effect=self.fake_run):
            with self.assertRaisesRegex(RuntimeError, "dylib is missing"):
                self.verify()
        self.assertEqual(len(self.calls), 1)

    def test_missing_macho_global_metadata_is_rejected(self):
        def missing_section(cmd):
            if "--sections" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="no ASan")
            return self.fake_run(cmd)
        with mock.patch.object(self.module, "run", side_effect=missing_section):
            with self.assertRaisesRegex(RuntimeError, "lacks Mach-O __asan_globals"):
                self.verify()

    def test_asan_globals_required_is_diagnosed_not_faked(self):
        def link_error(cmd):
            if "-fsanitize=address" in cmd and "-c" not in cmd:
                return subprocess.CompletedProcess(
                    cmd, 1, stdout="",
                    stderr="ld64.lld: error: undefined symbol: __asan_globals_required",
                )
            return self.fake_run(cmd)
        with mock.patch.object(self.module, "run", side_effect=link_error):
            with self.assertRaisesRegex(RuntimeError, "__asan_globals_required"):
                self.verify()
        self.assertEqual(len(self.calls), 3)

    def test_lld_missing_symbol_isolated_by_successful_apple_ld(self):
        def only_lld_fails(cmd):
            if "-fsanitize=address" in cmd and "-c" not in cmd:
                if "-fuse-ld=lld" in cmd:
                    return subprocess.CompletedProcess(
                        cmd, 1, stdout="",
                        stderr="undefined symbol: __asan_globals_required",
                    )
            return self.fake_run(cmd)
        with mock.patch.object(self.module, "run", side_effect=only_lld_fails):
            with self.assertRaisesRegex(RuntimeError, "Apple ld linked"):
                self.verify()
        self.assertNotIn("-fuse-ld=lld", self.calls[-1])

    def test_native_bootstrap_runs_probe_only_for_requested_sanitizer(self):
        code = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('NATIVE_LLVM_VALIDATE_ASAN=', code)
        self.assertIn('verify_asan_when_requested()', code)
        self.assertIn('scripts/verify-native-asan-darwin.py', code)
        self.assertIn('asan_args+=(--use-lld)', code)
        self.assertIn('verify_asan_when_requested "$TOOLCHAIN_DIR" || exit 1', code)
        self.assertIn('verify_asan_when_requested "$staged_toolchain" || exit 1',
                      code)
        self.assertNotIn('undefined dynamic_lookup', code)


if __name__ == "__main__":
    unittest.main()
