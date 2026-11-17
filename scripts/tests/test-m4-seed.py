#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline generic M4 tests: traditional macro operations and provider split."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/m4.sh"


class GenericM4SeedTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="whp-generic-m4-")
        self.addCleanup(self.work.cleanup)
        self.directory = Path(self.work.name)
        self.m4 = self.fake("m4")
        self.gm4 = self.fake("gm4")

    def fake(self, name, *, expansion="ready"):
        target = self.directory / name
        target.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = --identity ]; then printf "%s\n" "$0"; exit 0; fi\n'
            'if [ "$#" -eq 0 ]; then\n'
            f'    printf "%s\\n" "{expansion}"\n'
            '    exit 0\n'
            'fi\n'
            'exit 1\n', encoding="utf-8")
        target.chmod(0o755)
        return target

    def run_seed(self, *args, **overrides):
        env = os.environ.copy()
        for key in ("WHP_M4_SEED", "M4", "WHP_GNUM4_SEED", "GNUM4"):
            env.pop(key, None)
        env["PATH"] = str(self.directory)
        env.update(overrides)
        return subprocess.run(
            ["/bin/sh", str(SEED), *args], env=env,
            text=True, capture_output=True, check=False)

    def test_native_non_gnu_m4_is_acceptable(self):
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.m4))

    def test_fallback_to_other_compatible_m4(self):
        self.m4.unlink()
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gm4))

    def test_generic_explicit_selection_and_argument_forwarding(self):
        result = self.run_seed("--identity", WHP_M4_SEED=str(self.gm4),
                               M4=str(self.m4))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gm4))

    def test_invalid_explicit_fails_closed(self):
        result = self.run_seed("--print-seed",
                               WHP_M4_SEED=str(self.directory / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WHP_M4_SEED does not select", result.stderr)

    def test_non_expanding_m4_rejected(self):
        bad = self.fake("bad-m4", expansion="not expanded")
        result = self.run_seed("--print-seed", M4=str(bad))
        self.assertNotEqual(result.returncode, 0)

    def test_gnu_specific_adapter_not_a_generic_provider(self):
        result = self.run_seed("--print-seed", M4=str(ROOT / "seeds/gnum4.sh"))
        self.assertNotEqual(result.returncode, 0)

    def test_self_recursion_rejected(self):
        result = self.run_seed("--print-seed", M4=str(SEED))
        self.assertNotEqual(result.returncode, 0)

    def test_path_with_spaces_and_apostrophe(self):
        candidate = self.directory / "generic's M4 with spaces"
        self.m4.rename(candidate)
        result = self.run_seed("--print-seed", M4=str(candidate))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(candidate))

    def test_check_names_generic_role(self):
        result = self.run_seed("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP generic M4 seed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
