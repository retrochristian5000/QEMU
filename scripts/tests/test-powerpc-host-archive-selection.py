#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Execute the real PowerPC host-tool resolver without source downloads."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "scripts/bootstrap-powerpc-toolchain.bash").read_text(
    encoding="utf-8"
)


def source_function(name: str) -> str:
    """Extract a top-level Bash function, not a copy of its selection policy."""
    start = SOURCE.index(f"{name}()\n{{\n")
    end = SOURCE.index("\n}\n", start) + 2
    return SOURCE[start:end]


BASH_HELPERS = (
    "set -euo pipefail\n"
    + source_function("set_command") + "\n"
    + source_function("resolve_host_tool") + "\n"
    + "resolve_host_tool TOOLCHAIN_HOST_AR ar\n"
    + "resolve_host_tool TOOLCHAIN_HOST_RANLIB ranlib\n"
    + 'printf "%s\\n%s\\n" "$TOOLCHAIN_HOST_AR" "$TOOLCHAIN_HOST_RANLIB"\n'
)


class HostArchiveSelection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-powerpc-ar-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.ar_build = self.executable("build-ar")
        self.ar_seed = self.executable("seed-ar")
        self.ar_explicit = self.executable("explicit-ar")
        self.ranlib_build = self.executable("build-ranlib")
        self.ranlib_seed = self.executable("seed-ranlib")
        self.ranlib_explicit = self.executable("explicit-ranlib")
        self.executable("ar")
        self.executable("ranlib")

    def executable(self, name):
        path = self.bin / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    def run_selection(self, **values):
        env = os.environ.copy()
        for name in (
            "AR", "RANLIB", "AR_FOR_BUILD", "RANLIB_FOR_BUILD",
            "WHP_AR_SEED", "WHP_RANLIB_SEED", "TOOLCHAIN_HOST_AR",
            "TOOLCHAIN_HOST_RANLIB", "AR_FOR_TARGET", "RANLIB_FOR_TARGET",
        ):
            env.pop(name, None)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "/usr/bin:/bin")
        env.update(values)
        return subprocess.run(
            ["/bin/bash", "-c", BASH_HELPERS],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )

    def assert_selected(self, expected_ar, expected_ranlib, **overrides):
        result = self.run_selection(**overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected_ar + "\n" + expected_ranlib + "\n")

    def test_inherits_existing_build_machine_pair(self):
        self.assert_selected(
            self.ar_build, self.ranlib_build,
            AR_FOR_BUILD=self.ar_build, RANLIB_FOR_BUILD=self.ranlib_build,
            AR=self.ar_explicit, RANLIB=self.ranlib_explicit,
            AR_FOR_TARGET=self.ar_explicit, RANLIB_FOR_TARGET=self.ranlib_explicit,
        )

    def test_seed_overrides_fallback_build_tools(self):
        self.assert_selected(
            self.ar_seed, self.ranlib_seed,
            WHP_AR_SEED=self.ar_seed, WHP_RANLIB_SEED=self.ranlib_seed,
            AR_FOR_BUILD=self.ar_build, RANLIB_FOR_BUILD=self.ranlib_build,
        )

    def test_explicit_toolchain_hosts_take_priority(self):
        self.assert_selected(
            self.ar_explicit, self.ranlib_explicit,
            TOOLCHAIN_HOST_AR=self.ar_explicit,
            TOOLCHAIN_HOST_RANLIB=self.ranlib_explicit,
            WHP_AR_SEED=self.ar_seed, WHP_RANLIB_SEED=self.ranlib_seed,
            AR_FOR_BUILD=self.ar_build, RANLIB_FOR_BUILD=self.ranlib_build,
        )

    def test_generic_discovery_only_if_no_host_role_is_defined(self):
        self.assert_selected(str(self.bin / "ar"), str(self.bin / "ranlib"),
                             AR=self.ar_explicit, RANLIB=self.ranlib_explicit)

    def test_relative_tool_names_are_locked_to_absolute_paths(self):
        self.assert_selected(str(self.bin / "ar"), str(self.bin / "ranlib"),
                             AR_FOR_BUILD="ar", RANLIB_FOR_BUILD="ranlib")

    def test_invalid_explicit_selection_does_not_fall_back(self):
        result = self.run_selection(AR_FOR_BUILD=str(self.root / "missing-ar"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command is not executable", result.stderr)
        result = self.run_selection(AR_FOR_BUILD=f"{self.ar_build} --bogus")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must name one executable", result.stderr)

    def test_configure_inherits_selected_identity(self):
        self.assertIn('"AR=$TOOLCHAIN_HOST_AR"', SOURCE)
        self.assertIn('"AR_FOR_BUILD=$TOOLCHAIN_HOST_AR"', SOURCE)
        self.assertIn('"RANLIB=$TOOLCHAIN_HOST_RANLIB"', SOURCE)
        self.assertIn('"RANLIB_FOR_BUILD=$TOOLCHAIN_HOST_RANLIB"', SOURCE)
        self.assertIn("-u AR_FOR_TARGET", SOURCE)
        self.assertIn("-u RANLIB_FOR_TARGET", SOURCE)


if __name__ == "__main__":
    unittest.main()
