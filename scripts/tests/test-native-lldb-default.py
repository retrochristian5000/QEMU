#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the actual native bootstrap's LLDB default/override negotiation.

Run only the pre-build policy prefix in a subprocess: no LLVM configure,
checkout, or compilation, and no second copy of the defaults to drift.
"""

from pathlib import Path
import os
import subprocess
import unittest


BOOTSTRAP = Path(__file__).resolve().parents[1] / "bootstrap-native-clang.bash"
BOUNDARY = '\ncase "$host_arch" in\n'


class LldbDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = BOOTSTRAP.read_text(encoding="utf-8")
        if source.count(BOUNDARY) != 1:
            raise RuntimeError("cannot isolate the pre-build host/LLDB policy")
        cls.prebuild = source.split(BOUNDARY, 1)[0]
        # bash -c has no BASH_SOURCE[0]. The isolated policy must resolve
        # the same real scripts directory without pretending that this
        # synthetic snippet was executed from bootstrap-native-clang.bash.
        entry = 'SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"'
        if cls.prebuild.count(entry) != 1:
            raise RuntimeError("cannot identify the native LLVM script path")
        cls.prebuild = cls.prebuild.replace(
            entry, 'SCRIPT_DIR="${WHP_TEST_NATIVE_LLVM_SCRIPT_DIR:?}"', 1
        )
        cls.prebuild += (
            '\nprintf "WHP_LLDB_RESULT=%s:%s\\n" '
            '"$NATIVE_LLVM_ENABLE_LLDB" "$NATIVE_LLVM_ASAN_AUTO_DEBUG" >&2\n'
        )

    def check_policy(self, host, enabled=None, auto_debug=None):
        env = dict(os.environ)
        env["WHP_HOST_OS"] = host
        env["WHP_TEST_NATIVE_LLVM_SCRIPT_DIR"] = str(BOOTSTRAP.parent)
        env["WHP_HOST_ARCH"] = "aarch64"
        env["NATIVE_LLVM_ASAN_AUTO_DEBUG"] = "0" if auto_debug is None else auto_debug
        if enabled is None:
            env.pop("NATIVE_LLVM_ENABLE_LLDB", None)
        else:
            env["NATIVE_LLVM_ENABLE_LLDB"] = enabled
        return subprocess.run(
            ["bash", "-c", self.prebuild], env=env,
            capture_output=True, text=True, check=False,
        )

    def test_macos_defaults_to_fork_lldb_without_auto_replay(self):
        result = self.check_policy("macos")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP_LLDB_RESULT=1:0", result.stderr)

    def test_linux_keeps_lightweight_default(self):
        result = self.check_policy("linux")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP_LLDB_RESULT=0:0", result.stderr)

    def test_explicit_macos_opt_out_is_preserved(self):
        result = self.check_policy("macos", "0")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP_LLDB_RESULT=0:0", result.stderr)

    def test_macos_auto_debug_uses_default_debugger(self):
        result = self.check_policy("macos", auto_debug="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP_LLDB_RESULT=1:1", result.stderr)

    def test_explicit_opt_out_conflicts_with_auto_debug(self):
        result = self.check_policy("macos", "0", "1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("auto-debug requires", result.stderr)

    def test_linux_explicit_on_requires_later_host_capability_check(self):
        result = self.check_policy("linux", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP_LLDB_RESULT=1:0", result.stderr)

    def test_invalid_setting_is_rejected(self):
        result = self.check_policy("macos", "yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("NATIVE_LLVM_ENABLE_LLDB must be", result.stderr)


if __name__ == "__main__":
    unittest.main()
