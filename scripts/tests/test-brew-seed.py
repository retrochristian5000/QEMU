#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline checks for native Homebrew selection and explicit installation."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/brew.sh"


class BrewSeedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-brew-seed-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / "native"
        self.bin = self.prefix / "bin"
        self.bin.mkdir(parents=True)
        self.brew = self.make_brew(self.bin / "brew")
        self.log = self.root / "brew.log"
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "HOMEBREW_PREFIX": str(self.prefix),
            "WHP_TEST_BREW_PREFIX": str(self.prefix),
            "WHP_TEST_BREW_LOG": str(self.log),
        }

    def make_brew(self, path, version="Homebrew 5.2.0"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/sh\n"
            'case "${1:-}" in\n'
            '  --whp-brew-adapter-probe) exit 2 ;;\n'
            f'  --version) printf "%s\\n" "{version}" ;;\n'
            '  --prefix) printf "%s\\n" "$WHP_TEST_BREW_PREFIX" ;;\n'
            '  list) printf "pkg 1.0\\n" ;;\n'
            '  install) printf "%s\\n" "$*" >> "$WHP_TEST_BREW_LOG" ;;\n'
            '  *) exit 7 ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *args, **changes):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env={**self.env, **changes}, text=True,
            capture_output=True, check=False, timeout=10,
        )

    def test_prefix_first_and_check_without_install(self):
        selected = self.run_seed("--print-seed")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout, str(self.brew) + "\n")
        check = self.run_seed("--check")
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn(str(self.prefix), check.stdout)
        self.assertFalse(self.log.exists())

    def test_forwarding_is_explicit(self):
        result = self.run_seed("list", "--formula", "--versions")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "pkg 1.0\n")
        self.assertFalse(self.log.exists())
        result = self.run_seed("install", "glib", "pixman")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(), "install glib pixman\n")
        result = self.run_seed("nonexistent")
        self.assertEqual(result.returncode, 7)

    def test_invalid_explicit_never_falls_back(self):
        result = self.run_seed("--print-seed", WHP_BREW_SEED=str(self.root / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WHP_BREW_SEED", result.stderr)

    def test_existing_lock_and_conflicting_override(self):
        other = self.make_brew(self.root / "other-brew")
        result = self.run_seed("--print-seed", WHP_HOMEBREW_BREW=str(other))
        self.assertEqual(result.stdout, str(other) + "\n")
        result = self.run_seed("--print-seed", WHP_BREW_SEED=str(self.brew),
                               WHP_HOMEBREW_BREW=str(other))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("conflicts", result.stderr)
        result = self.run_seed("--print-seed", WHP_BREW_SEED=str(self.brew),
                               WHP_HOMEBREW_BREW=str(self.brew))
        self.assertEqual(result.stdout, str(self.brew) + "\n")

    def test_wrong_prefix_is_not_silently_accepted(self):
        result = self.run_seed("--check", WHP_BREW_SEED=str(self.brew),
                               HOMEBREW_PREFIX=str(self.root / "incorrect"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WHP_BREW_SEED", result.stderr)

    def test_rejects_non_homebrew_and_recursion(self):
        not_brew = self.make_brew(self.root / "not-brew", "NotBrew 5.2.0")
        result = self.run_seed("--print-seed", WHP_BREW_SEED=str(not_brew))
        self.assertNotEqual(result.returncode, 0)
        result = self.run_seed("--print-seed", WHP_BREW_SEED=str(SEED))
        self.assertNotEqual(result.returncode, 0)
        adapter_link = self.root / "brew-link"
        adapter_link.symlink_to(SEED)
        result = self.run_seed("--print-seed", WHP_BREW_SEED=str(adapter_link))
        self.assertNotEqual(result.returncode, 0)

    def test_provider_integration(self):
        prepare = (ROOT / "scripts/whp-build/prepare-build.bash").read_text()
        refresh = (ROOT / "scripts/whp-build/homebrew-deps.bash").read_text()
        self.assertIn('seeds/brew.sh" --print-seed', prepare)
        self.assertIn('WHP_HOMEBREW_BREW="$selected_brew"', prepare)
        self.assertIn('"$selected_brew" --prefix', prepare)
        self.assertIn('export WHP_HOMEBREW_BREW HOMEBREW_PREFIX', prepare)
        self.assertIn('manager="$(whp_homebrew_brew_command)" || return 1', refresh)


if __name__ == "__main__":
    unittest.main()
