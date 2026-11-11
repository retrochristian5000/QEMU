#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline GNU M4 seed tests: native variant choice and fail-closed semantics."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/m4.sh"


class M4SeedTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="whp-m4-seed-")
        self.addCleanup(self.work.cleanup)
        self.directory = Path(self.work.name)
        self.m4 = self.fake("m4")
        self.gm4 = self.fake("gm4")
        uname = self.directory / "uname"
        uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n", encoding="utf-8")
        uname.chmod(0o755)

    def fake(self, name, version="1.4.21", expansion="abXcd"):
        path = self.directory / name
        path.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = --gnu ] && [ \"$2\" = --version ]; then\n"
            f"    printf '%s\\n' 'm4 (GNU M4) {version}'\n"
            "    exit 0\n"
            "fi\n"
            "if [ \"$1\" = --gnu ] && [ \"$2\" = --fatal-warnings ]; then\n"
            f"    printf '%s\\n' '{expansion}'\n"
            "    exit 0\n"
            "fi\n"
            "if [ \"$1\" = --libs ]; then printf '%s\\n' \"$0\"; exit 0; fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *arguments, **overrides):
        env = os.environ.copy()
        for key in ("WHP_M4_SEED", "M4", "HOMEBREW_PREFIX"):
            env.pop(key, None)
        env["PATH"] = str(self.directory)
        env.update(overrides)
        return subprocess.run(
            ["/bin/sh", str(SEED), *arguments],
            env=env, text=True, capture_output=True, check=False,
        )

    def test_prefers_native_m4(self):
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.m4))

    def test_falls_back_to_gm4(self):
        self.m4.unlink()
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gm4))

    def test_explicit_selection_and_forwarding(self):
        result = self.run_seed("--libs", WHP_M4_SEED=str(self.gm4),
                               M4=str(self.m4))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gm4))

    def test_invalid_explicit_fails_closed(self):
        result = self.run_seed("--print-seed", M4=str(self.directory / "absent"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("M4 does not select", result.stderr)

    def test_old_m4_rejected(self):
        old = self.fake("old-m4", version="1.4.15")
        result = self.run_seed("--print-seed", WHP_M4_SEED=str(old))
        self.assertNotEqual(result.returncode, 0)

    def test_bad_macro_rejected_even_with_new_version(self):
        fake = self.fake("bad-m4", version="99.99", expansion="not-expanded")
        result = self.run_seed("--print-seed", WHP_M4_SEED=str(fake))
        self.assertNotEqual(result.returncode, 0)

    def test_recursive_override_rejected(self):
        result = self.run_seed("--print-seed", WHP_M4_SEED=str(SEED))
        self.assertNotEqual(result.returncode, 0)

    def test_user_facing_check(self):
        result = self.run_seed("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP GNU M4 seed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
