#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Host-independent regression tests for the Darwin ASan global-link probe."""

from __future__ import annotations

import importlib.util
import os
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

    def test_asan_and_arm64e_use_apple_ld_consistently(self):
        build = (ROOT / "build.sh").read_text(encoding="utf-8")
        bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
        self.assertIn('case "${QEMU_ASAN:-n}:${WHP_MACOS_ARCH:-auto}" in', build)
        self.assertIn("1:*|y:*)", build)
        self.assertIn("*:arm64e)", build)
        self.assertIn('WHP_ARM64E_USE_LLD', build)
        self.assertIn("LD=$(xcrun --find ld) || exit 1", build)
        self.assertIn("NATIVE_LLVM_LDFLAG=", build)
        self.assertIn('LD="$NATIVE_LLVM_DIR/bin/ld64.lld"', build)
        self.assertIn("NATIVE_LLVM_LDFLAG=-fuse-ld=lld", build)
        self.assertIn('"${QEMU_ASAN:-0}" != 1 && "${QEMU_ASAN:-0}" != y', bootstrap)
        self.assertIn("asan_args+=(--use-lld)", bootstrap)

    def test_native_linker_selection_honors_asan_and_arm64e(self):
        # Run the POSIX shell decision from build.sh against a fake xcrun.
        # This detects misplaced branches that source-text assertions miss.
        build = (ROOT / "build.sh").read_text(encoding="utf-8")
        start = build.index("    # Keep Clang, compiler-rt, and Mach-O linker selection coherent.")
        start = build.index('    if [ "$WHP_HOST_OS" = macos ]; then', start)
        end_text = "        export LD LIPO NATIVE_LLVM_LDFLAG LDFLAGS WHP_ARM64E_USE_LLD\\n    fi"
        end = build.index(end_text, start) + len(end_text)
        shell_code = build[start:end] + (
            '\\nprintf "%s|%s|%s\\n" "$LD" "$NATIVE_LLVM_LDFLAG" "$LDFLAGS"\\n'
        )
        with tempfile.TemporaryDirectory() as temp:
            bin_dir = pathlib.Path(temp)
            xcrun = bin_dir / "xcrun"
            xcrun.write_text(
                '#!/bin/sh\\n'
                '[ "$1" = "--find" ] && [ "$2" = "ld" ] || exit 1\\n'
                'printf "/mock/Apple/ld\\\\n"\\n',
                encoding="utf-8",
            )
            xcrun.chmod(0o755)
            env = os.environ.copy()
            env.update({
                "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
                "WHP_HOST_OS": "macos",
                "NATIVE_LLVM_DIR": "/mock/llvm",
            })
            for asan, arch, expected in (
                ("n", "arm64", "/mock/llvm/bin/ld64.lld|-fuse-ld=lld|-fuse-ld=lld"),
                ("y", "arm64", "/mock/Apple/ld||"),
                ("1", "arm64", "/mock/Apple/ld||"),
                ("n", "arm64e", "/mock/Apple/ld||"),
                ("n", "x86_64", "/mock/llvm/bin/ld64.lld|-fuse-ld=lld|-fuse-ld=lld"),
            ):
                with self.subTest(asan=asan, arch=arch):
                    local = dict(env, QEMU_ASAN=asan, WHP_MACOS_ARCH=arch,
                                 WHP_ARM64E_USE_LLD="0", LDFLAGS="")
                    proc = subprocess.run(
                        ["sh", "-c", shell_code], text=True, capture_output=True,
                        env=local, check=False,
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertEqual(proc.stdout.splitlines()[-1], expected)
            # The arm64e Mach-O LLD path is explicitly opt-in. This tests
            # the POSIX selection logic; a separate probe checks actual
            # authenticated relocations before the macOS wrapper links QEMU.
            local = dict(env, QEMU_ASAN="n", WHP_MACOS_ARCH="arm64e",
                         WHP_ARM64E_USE_LLD="1", LDFLAGS="")
            proc = subprocess.run(
                ["sh", "-c", shell_code], text=True, capture_output=True,
                env=local, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(
                proc.stdout.splitlines()[-1],
                "/mock/llvm/bin/ld64.lld|-fuse-ld=lld|-fuse-ld=lld",
            )

            local = dict(env, QEMU_ASAN="y", WHP_MACOS_ARCH="arm64",
                         WHP_ARM64E_USE_LLD="0", LDFLAGS="-fuse-ld=lld")
            proc = subprocess.run(
                ["sh", "-c", shell_code], text=True, capture_output=True,
                env=local, check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("overrides", proc.stderr)

            # This early POSIX guard must protect both driver commands and
            # per-language flags before the macOS Bash wrapper runs.
            for variable, injected in (
                ("CC", "clang -fuse-ld=lld"),
                ("CXX", "clang++ -fuse-ld=lld"),
                ("CFLAGS", "--ld-path=/mock/llvm/bin/ld64.lld"),
                ("CXXFLAGS", "-fuse-ld=lld"),
                ("OBJCFLAGS", "-fuse-ld=lld"),
                ("CPPFLAGS", "--ld-path=/mock/other/ld"),
                ("LDFLAGS", "--ld-path=/mock/other/ld"),
            ):
                with self.subTest(early_linker_override=variable):
                    local = dict(env, QEMU_ASAN="n", WHP_MACOS_ARCH="arm64e",
                                 WHP_ARM64E_USE_LLD="0",
                                 CC="", CXX="", CFLAGS="", CXXFLAGS="",
                                 OBJCFLAGS="", CPPFLAGS="", LDFLAGS="")
                    local[variable] = injected
                    proc = subprocess.run(
                        ["sh", "-c", shell_code], text=True,
                        capture_output=True, env=local, check=False,
                    )
                    self.assertNotEqual(proc.returncode, 0)
                    self.assertIn(variable, proc.stderr)

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
