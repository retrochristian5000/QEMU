#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check optional native Zsh selection without building or replacing shells."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/zsh.sh"


class ZshSeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-zsh-seed-")
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.native = shutil.which("zsh")
        self.env = dict(os.environ)
        self.env.pop("WHP_ZSH_SEED", None)

    def run_seed(self, *args, override=None):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env=self.env if override is None else override,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

    def test_explicit_bad_seed_never_falls_back(self):
        imitation = self.directory / "not-zsh"
        imitation.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        imitation.chmod(0o755)
        for candidate in (str(self.directory / "missing"), "zsh -f", "/bin/sh",
                          str(SEED), str(imitation)):
            with self.subTest(candidate=candidate):
                result = self.run_seed("--print-seed", override=dict(
                    self.env, WHP_ZSH_SEED=candidate))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WHP_ZSH_SEED", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_copied_or_linked_adapter_cannot_recurse(self):
        copied = self.directory / "copied-zsh"
        copied.write_bytes(SEED.read_bytes())
        copied.chmod(0o755)
        alias = self.directory / "zsh-alias"
        alias.symlink_to(SEED)
        for candidate in (copied, alias):
            with self.subTest(candidate=str(candidate)):
                result = self.run_seed("--print-zsh", override=dict(
                    self.env, WHP_ZSH_SEED=str(candidate)))
                self.assertNotEqual(result.returncode, 0)

    def test_native_selection_and_argument_forwarding(self):
        if not self.native:
            self.skipTest("native Zsh is not installed")
        env = dict(self.env, WHP_ZSH_SEED=self.native)
        chosen = self.run_seed("--print-seed", override=env)
        self.assertEqual(chosen.returncode, 0, chosen.stderr)
        self.assertEqual(Path(chosen.stdout.strip()).resolve(),
                         Path(self.native).resolve())
        self.assertEqual(self.run_seed("--check", override=env).returncode, 0)
        cmd = 'items=(one two); print -rn -- "${items[1]}:$1"'
        run = self.run_seed("-c", cmd, "seed", "two words", override=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "one:two words")
        failure = self.run_seed("-c", "exit 19", override=env)
        self.assertEqual(failure.returncode, 19)

    def test_startup_hooks_do_not_control_selected_zsh(self):
        if not self.native:
            self.skipTest("native Zsh is not installed")
        dotdir = self.directory / "startup"
        dotdir.mkdir()
        (dotdir / ".zshenv").write_text("exit 79\n", encoding="utf-8")
        hook = self.directory / "shenv"
        hook.write_text("exit 79\n", encoding="utf-8")
        env = dict(self.env, WHP_ZSH_SEED=self.native,
                   ZDOTDIR=str(dotdir), ENV=str(hook))
        self.assertEqual(self.run_seed("--print-seed", override=env).returncode, 0)
        result = self.run_seed("-c", 'print -rn -- clean', override=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "clean")

    def test_seed_is_a_posix_launcher(self):
        self.assertEqual(SEED.read_text(encoding="utf-8").splitlines()[0],
                         "#!/bin/sh")
        result = subprocess.run(["/bin/sh", "-n", str(SEED)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
