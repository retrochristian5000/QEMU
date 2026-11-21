#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Focused host-only tests for optional managed Bash installation."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
INSTALLER = ROOT / "scripts" / "whp-build" / "install-runtime-bash.py"


@unittest.skipIf(platform.system() == "Windows", "POSIX host shell required")
class RuntimeBashInstallTests(unittest.TestCase):
    def setUp(self):
        self.bash = shutil.which("bash")
        if not self.bash:
            self.skipTest("a runnable native Bash is required")
        self.temp = tempfile.TemporaryDirectory(prefix="whp-runtime-bash-")
        self.addCleanup(self.temp.cleanup)
        work = Path(self.temp.name)
        self.build_dir = work / "build with spaces"
        self.prefix = work / "QEMU installation"
        self.cached = self.build_dir / "deps" / "bash"
        (self.cached / "bin").mkdir(parents=True)
        native_bash = self.cached / "bin" / "bash"
        shutil.copyfile(self.bash, native_bash)
        native_bash.chmod(0o755)
        self.native_bash = native_bash
        self.marker = self.cached / ".whp-bash-bootstrap"
        env = dict(os.environ)
        for key in ("BASH_ENV", "ENV", "POSIXLY_CORRECT", "SHELLOPTS", "BASHOPTS"):
            env.pop(key, None)
        machtype = subprocess.run(
            [self.bash, "--noprofile", "--norc", "-c",
             'printf "%s" "$MACHTYPE"'],
            capture_output=True, text=True, check=True, env=env,
        ).stdout
        self.marker.write_text(
            "BASH_GIT_COMMIT=test-fixture\n"
            f"HOST_SYSTEM={platform.system()}\n"
            f"HOST_MACHINE={platform.machine()}\n"
            f"BASH_HOST_TRIPLET={machtype}\n"
            "WHP_MACOS_ARCH=auto\n",
            encoding="utf-8",
        )

    def run_installer(self, action="--check", prefix=None):
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--build-dir", str(self.build_dir),
             "--prefix", str(prefix if prefix is not None else self.prefix),
             action],
            capture_output=True, text=True, check=False,
        )

    def test_check_is_read_only(self):
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.prefix.exists())

    def test_install_is_runnable_and_idempotent(self):
        for _ in range(2):
            result = self.run_installer("--install")
            self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.prefix / "bin" / "whp-qemu-bash"
        self.assertTrue(os.access(installed, os.X_OK))
        run = subprocess.run(
            [str(installed), "--noprofile", "--norc", "-c",
             "a=(one two); declare -p a | grep -q 'declare -a'"],
            check=False,
        )
        self.assertEqual(run.returncode, 0)

    def test_unmanaged_destination_is_preserved(self):
        dest = self.prefix / "bin" / "whp-qemu-bash"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"other owner's bash")
        check = self.run_installer()
        self.assertNotEqual(check.returncode, 0)
        self.assertEqual(dest.read_bytes(), b"other owner's bash")

    def test_tampered_managed_destination_is_preserved(self):
        self.assertEqual(self.run_installer("--install").returncode, 0)
        dest = self.prefix / "bin" / "whp-qemu-bash"
        dest.write_bytes(b"external change")
        check = self.run_installer()
        self.assertNotEqual(check.returncode, 0)
        self.assertEqual(dest.read_bytes(), b"external change")

    def test_bad_cache_or_host_identity_fails(self):
        self.marker.unlink()
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.marker.write_text(
            "BASH_GIT_COMMIT=other\nHOST_SYSTEM=WrongOS\n"
            f"HOST_MACHINE={platform.machine()}\n"
            "BASH_HOST_TRIPLET=x\nWHP_MACOS_ARCH=auto\n",
            encoding="utf-8",
        )
        self.assertNotEqual(self.run_installer().returncode, 0)

    def test_refuses_symlinked_bin_and_relative_prefix(self):
        other = Path(self.temp.name) / "unrelated"
        other.mkdir()
        self.prefix.mkdir()
        (self.prefix / "bin").symlink_to(other, target_is_directory=True)
        self.assertNotEqual(self.run_installer().returncode, 0)
        self.assertFalse((other / "whp-qemu-bash").exists())
        self.assertNotEqual(self.run_installer(prefix="relative").returncode, 0)

    def test_install_wiring_present_in_both_runners(self):
        bash_flow = (ROOT / "scripts" / "whp-build" /
                     "build-targets.bash").read_text(encoding="utf-8")
        portable = (ROOT / "scripts" / "whp-build" /
                    "portable-build.py").read_text(encoding="utf-8")
        schema = (ROOT / "scripts" / "whp-config" /
                  "menu-options.def").read_text(encoding="utf-8")
        config = (ROOT / "scripts" / "whp-config" /
                  "config.py").read_text(encoding="utf-8")
        self.assertIn("INSTALL_RUNTIME_BASH|Build behavior|", schema)
        self.assertIn("Option('INSTALL_RUNTIME_BASH'", config)
        self.assertIn("install-runtime-bash.py", bash_flow)
        self.assertIn("install-runtime-bash.py", portable)
        self.assertLess(bash_flow.index("--check || return 1"),
                        bash_flow.index('"$NINJA_CMD" -C "$BUILD_DIR" install'))
        self.assertLess(portable.index("'--check'], check=True)"),
                        portable.index("'install'], check=True)"))


if __name__ == "__main__":
    unittest.main()
