#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check native libLLVM/libclang-cpp profile without building LLVM."""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts" / "bootstrap-native-clang.bash"


class SharedLLVMProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code = BOOTSTRAP.read_text(encoding="utf-8")
        start = cls.code.index("\nshared_host_libraries_usable()\n{") + 1
        stop = cls.code.index("\nusable()\n{", start)
        cls.helper = cls.code[start:stop]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.prefix = self.root / "install"
        (self.prefix / "lib").mkdir(parents=True)

    def check(self, enabled="1", host="linux", expect=0):
        env = os.environ.copy()
        env["NATIVE_LLVM_SHARED_TOOLCHAIN"] = enabled
        env["host_os"] = host
        env["PATH"] = str(self.root) + os.pathsep + env["PATH"]
        result = subprocess.run(
            ["bash", "-c", self.helper + '\nshared_host_libraries_usable "$1"',
             "whp-shared-test", str(self.prefix)],
            text=True, capture_output=True, env=env, check=False,
        )
        if expect == 0:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0)
        return result

    def test_bootstrap_syntax(self):
        subprocess.run(["bash", "-n", str(BOOTSTRAP)], check=True)

    def test_opt_in_policy_and_cache_identity(self):
        code = self.code
        self.assertIn('NATIVE_LLVM_SHARED_TOOLCHAIN=', code)
        self.assertIn('expected_marker="$expected_marker"$', code)
        self.assertIn("LLVM_SHARED_TOOLCHAIN=1", code)
        self.assertIn("BOOTSTRAP_SCHEMA=12", code)
        self.assertIn('LLVM;clang-cpp"', code)
        self.assertIn("-DBUILD_SHARED_LIBS=OFF", code)
        self.assertIn("-DLLVM_ENABLE_PIC=ON", code)
        self.assertIn('"-DLLVM_BUILD_LLVM_DYLIB=$llvm_build_shared"', code)
        self.assertIn('"-DLLVM_LINK_LLVM_DYLIB=$llvm_link_shared"', code)
        self.assertIn('"-DCLANG_LINK_CLANG_DYLIB=$clang_link_shared"', code)
        self.assertIn("-DLLVM_DYLIB_COMPONENTS=all", code)
        self.assertIn("llvm_build_shared=OFF", code)
        self.assertIn("llvm_link_shared=OFF", code)
        self.assertIn("clang_link_shared=OFF", code)
        self.assertIn("NATIVE_LLVM_SHARED_TOOLCHAIN=1 is unsupported", code)
        self.assertEqual(code.count("\nusable()\n{"), 1)
        self.assertEqual(code.count("cmake_args=("), 1)

    def test_default_needs_no_dylibs(self):
        self.check(enabled="0")

    def test_linux_needs_both_shared_libraries(self):
        self.check(expect=1)
        (self.prefix / "lib" / "libLLVM.so.19").write_bytes(b"mock")
        self.check(expect=1)
        (self.prefix / "lib" / "libclang-cpp.so.19").write_bytes(b"mock")
        self.check()

    def test_darwin_requires_dylibs_and_actual_clang_dependency(self):
        lib = self.prefix / "lib"
        (lib / "libLLVM.19.dylib").write_bytes(b"mock")
        (lib / "libclang-cpp.19.dylib").write_bytes(b"mock")
        (self.prefix / "bin").mkdir()
        (self.prefix / "bin" / "clang").write_bytes(b"mock")
        otool = self.root / "otool"
        otool.write_text(
            '#!/bin/sh\nprintf "clang:\\n\\t@rpath/libclang-cpp.19.dylib\\n"\n',
            encoding="utf-8",
        )
        otool.chmod(0o755)
        self.check(host="macos")
        otool.write_text(
            '#!/bin/sh\nprintf "clang:\\n\\t/usr/lib/libSystem.B.dylib\\n"\n',
            encoding="utf-8",
        )
        self.check(host="macos", expect=1)

    def test_toolchain_keeps_cross_targets_and_compiler_rt(self):
        code = self.code
        self.assertIn("LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'", code)
        self.assertIn("LLD_ENABLE_BACKENDS='ELF;COFF;MinGW;MachO'", code)
        self.assertIn("llvm_enable_runtimes=compiler-rt", code)


if __name__ == "__main__":
    unittest.main()
