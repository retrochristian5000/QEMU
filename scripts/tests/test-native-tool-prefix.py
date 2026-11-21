#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""No-build coverage for native tool prefix discovery and shell handoff."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "whp-build" / "native-tool-prefix.sh"
HOST_TOOLS = ROOT / "scripts" / "whp-build" / "host-tools.sh"


class NativePrefixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-native-prefix-")
        self.addCleanup(self.temp.cleanup)
        self.build_dir = Path(self.temp.name) / "build dir"
        self.build_dir.mkdir()
        self.env = dict(os.environ, BUILD_DIR=str(self.build_dir))
        self.env.pop("WHP_NATIVE_TOOL_PREFIX", None)

    def run_audit(self, prefix=None):
        env = self.env.copy()
        if prefix is not None:
            env["WHP_NATIVE_TOOL_PREFIX"] = str(prefix)
        return subprocess.run(
            ["/bin/sh", str(HELPER), "--audit"],
            env=env, text=True, capture_output=True, check=False,
        )

    def test_default_scans_only_build_machine_deps(self):
        path = self.build_dir / "deps" / "bash" / "bin" / "bash"
        path.parent.mkdir(parents=True)
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        audit = self.run_audit()
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn(f"bash: candidate (unverified): {path}", audit.stdout)
        self.assertIn("ninja: absent", audit.stdout)
        self.assertNotIn("/usr/bin/bash", audit.stdout)

    def test_explicit_prefix_bin_and_invalid_relative_path(self):
        prefix = Path(self.temp.name) / "native tools"
        binary = prefix / "bin" / "ninja"
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
        audit = self.run_audit(prefix)
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn(str(binary), audit.stdout)
        bad = self.run_audit("relative-prefix")
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("must be absolute", bad.stderr)

    def test_nonexecutables_are_not_promoted(self):
        prefix = Path(self.temp.name) / "plain"
        file = prefix / "bin" / "bash"
        file.parent.mkdir(parents=True)
        file.write_text("no executable\n", encoding="utf-8")
        audit = self.run_audit(prefix)
        self.assertEqual(audit.returncode, 0)
        self.assertIn("bash: absent", audit.stdout)

    def test_host_handoff_preserves_policy(self):
        host_tools = HOST_TOOLS.read_text(encoding="utf-8")
        self.assertIn('native-tool-prefix.sh"', host_tools)
        self.assertIn("whp_native_tool_prefix_init || exit 1", host_tools)
        self.assertIn("whp_native_tool_prefix_find ninja", host_tools)
        self.assertIn("whp_native_tool_prefix_find bash", host_tools)
        self.assertLess(
            host_tools.index("whp_native_tool_prefix_init || exit 1"),
            host_tools.index("BOOTSTRAP_NINJA=$("),
        )
        self.assertLess(
            host_tools.index("BOOTSTRAP_BASH=$("),
            host_tools.index("whp_native_tool_prefix_find bash"),
        )


if __name__ == "__main__":
    unittest.main()
