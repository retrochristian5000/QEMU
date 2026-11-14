#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test macOS policy compiler identity without running Xcode bootstrap.

Invoke the actual policy functions in Bash; isolate only the top-level
Xcode-dependent bootstrapping, not the compiler classification logic.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "scripts/macos-compiler-policy.bash"
SOURCE = POLICY.read_text(encoding="utf-8")
BEGIN = SOURCE.index("set_compiler_command()\n")
END = SOURCE.index("compiler_target_triple()\n", BEGIN)
FUNCTIONS = SOURCE[BEGIN:END]


class CompilerFamilyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="whp-compiler-family-")
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)

    def identify(self, executable, *, macros="", verbose="unknown compiler",
                 banner="unknown compiler", fail_preprocessor=False):
        env = dict(os.environ)
        env.update(
            WHP_TEST_MACROS=macros,
            WHP_TEST_VERBOSE=verbose,
            WHP_TEST_BANNER=banner,
            WHP_TEST_PREPROCESS_FAIL="1" if fail_preprocessor else "0",
        )
        return subprocess.run(
            ["bash", "-c", FUNCTIONS + '\ncompiler_family "$1"\n',
             "whp-family-test", str(executable)],
            env=env, capture_output=True, text=True, timeout=20, check=False,
        )

    def wrapper(self, name):
        path = self.directory / name
        path.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  -dM)\n'
            '    [ "$WHP_TEST_PREPROCESS_FAIL" != 1 ] || exit 77\n'
            '    printf "%s\\n" "$WHP_TEST_MACROS" ;;\n'
            '  -v) printf "%s\\n" "$WHP_TEST_VERBOSE" >&2 ;;\n'
            '  --version) printf "%s\\n" "$WHP_TEST_BANNER" ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def assert_family(self, executable, expected, **kwargs):
        result = self.identify(executable, **kwargs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)
        self.assertEqual(result.stderr, "")

    def test_clang_wins_even_if_called_gcc_and_gnu_macros_exist(self):
        self.assert_family(
            self.wrapper("gcc"), "clang",
            macros="#define __GNUC__ 4\n#define __clang__ 1",
            verbose="gcc version 99.0",
            banner="GCC 99.0",
        )

    def test_real_gcc_does_not_need_gcc_executable_name(self):
        self.assert_family(
            self.wrapper("my-custom-cc"), "gcc",
            macros="#define __GNUC__ 14\n#define __GNUC_MINOR__ 2",
            verbose="gcc version 14.2.0 (GNU)",
            banner="clang version 21",
        )

    def test_gcc_banner_without_gnu_macro_is_unknown(self):
        self.assert_family(
            self.wrapper("banner-only"), "unknown",
            verbose="gcc version 99.0", banner="GCC 99.0",
        )

    def test_gnu_compatible_alternative_is_not_assumed_gcc(self):
        self.assert_family(
            self.wrapper("vendor-compiler"), "unknown",
            macros="#define __GNUC__ 13\n#define __INTEL_COMPILER 1",
            verbose="Vendor C/C++ compiler 21",
        )

    def test_clang_banner_does_not_override_gnu_compatibility(self):
        self.assert_family(
            self.wrapper("clang-banner"), "unknown",
            macros="#define __GNUC__ 12",
            verbose="clang version 21",
            banner="clang version 21",
        )

    def test_failed_macro_probe_is_unknown(self):
        self.assert_family(
            self.wrapper("preprocess-failure"), "unknown",
            verbose="gcc version 15.0",
            fail_preprocessor=True,
        )

    def test_native_compilers_when_installed(self):
        for name in ("clang", "gcc", "g++"):
            executable = shutil.which(name)
            if not executable:
                continue
            result = subprocess.run(
                ["bash", "-c", FUNCTIONS + '\ncompiler_family "$1"\n',
                 "whp-family-native", executable],
                capture_output=True, text=True, timeout=20, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            if name == "clang":
                self.assertEqual(result.stdout.strip(), "clang")
            else:
                # Apple /usr/bin/gcc and /usr/bin/g++ may invoke Clang.
                self.assertIn(result.stdout.strip(), ("clang", "gcc"))
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
