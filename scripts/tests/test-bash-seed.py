#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test the independent Bash seed without building Bash or QEMU."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/bash.sh"
HOST_TOOLS = ROOT / "scripts/whp-build/host-tools.sh"

class BashSeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-bash-seed-")
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.native = shutil.which("bash")
        if not self.native:
            self.skipTest("native Bash required")
        self.env = dict(os.environ)
        self.env.pop("WHP_BASH_SEED", None)

    def run_seed(self, *args, override=None):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env=override or self.env, capture_output=True, text=True,
            check=False, timeout=15,
        )

    def test_host_seed_and_forwarded_arguments(self):
        selected = self.run_seed("--print-seed")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertTrue(Path(selected.stdout.strip()).is_file())
        self.assertEqual(self.run_seed("--check").returncode, 0)
        env = dict(self.env, WHP_BASH_SEED=self.native)
        chosen = self.run_seed("--print-bash", override=env)
        self.assertEqual(chosen.returncode, 0, chosen.stderr)
        self.assertEqual(Path(chosen.stdout.strip()).resolve(),
                         Path(self.native).resolve())
        run = self.run_seed("--noprofile", "--norc", "-c",
                            'a=(one two); printf "%s:%s" "${#a[@]}" "$1"',
                            "seed", "two words", override=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "2:two words")

    def test_explicit_bad_seed_never_falls_back(self):
        weak = self.dir / "version-only-bash"
        weak.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        weak.chmod(0o755)
        for candidate in (str(self.dir / "missing"), "bash --noprofile",
                          str(SEED), str(weak)):
            with self.subTest(candidate=candidate):
                result = self.run_seed("--print-seed", override=dict(
                    self.env, WHP_BASH_SEED=candidate))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WHP_BASH_SEED", result.stderr)

    def test_copy_or_symlink_cannot_recurse(self):
        copied = self.dir / "copied-seed"
        copied.write_bytes(SEED.read_bytes())
        copied.chmod(0o755)
        symlink = self.dir / "bash-alias"
        symlink.symlink_to(copied)
        for candidate in (copied, symlink):
            with self.subTest(path=str(candidate)):
                result = self.run_seed("--print-seed", override=dict(
                    self.env, WHP_BASH_SEED=str(candidate)))
                self.assertNotEqual(result.returncode, 0)

    def test_startup_hooks_cannot_override_selection_or_execution(self):
        hook = self.dir / "startup"
        hook.write_text("exit 79\n", encoding="utf-8")
        env = dict(self.env, WHP_BASH_SEED=self.native, BASH_ENV=str(hook),
                   ENV=str(hook), POSIXLY_CORRECT="y")
        self.assertEqual(self.run_seed("--print-seed", override=env).returncode, 0)
        run = self.run_seed("-c", 'test -z "${BASH_ENV:-}" && printf clean',
                            override=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "clean")

    def test_handoff_preserves_public_shell_and_managed_bash(self):
        source = HOST_TOOLS.read_text(encoding="utf-8")
        self.assertIn('seeds/bash.sh" --print-seed', source)
        self.assertIn('WHP_BUILD_BASH_EXPLICIT', source)
        self.assertIn('scripts/ensure-bash.py', source)
        self.assertIn('CONFIG_SHELL="$WHP_BUILD_BASH"', source)
        self.assertLess(source.index('seeds/bash.sh" --print-seed'),
                        source.index('scripts/ensure-bash.py'))

if __name__ == "__main__":
    unittest.main()
