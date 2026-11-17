#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline GNU-only M4 tests: identity, legacy variables, traces and freeze."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/gnum4.sh"


class GNUM4SeedTest(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="whp-m4-seed-")
        self.addCleanup(self.work.cleanup)
        self.directory = Path(self.work.name)
        self.m4 = self.fake("m4")
        self.gm4 = self.fake("gm4")
        uname = self.directory / "uname"
        uname.write_text("#!/bin/sh\nprintf 'Linux\\n'\n", encoding="utf-8")
        uname.chmod(0o755)

    def fake(self, name, version="1.4.21", expansion="abXcd",
             trace="m4trace:stdin:3: -1- T(<traced>)", freeze=True):
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
            "if [ \"$1\" = --gnu ] && [ \"$2\" = --trace=T ]; then\n"
            f"    printf '%s\\n' '{trace}'\n"
            "    exit 0\n"
            "fi\n"
            "if [ \"$1\" = --gnu ] && [ \"$2\" = -F ]; then\n"
            f"    exit {0 if freeze else 1}\n"
            "fi\n"
            "if [ \"$1\" = --libs ]; then printf '%s\\n' \"$0\"; exit 0; fi\n"
            "exit 1\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *arguments, **overrides):
        env = os.environ.copy()
        for key in ("WHP_GNUM4_SEED", "GNUM4", "WHP_M4_SEED", "M4", "HOMEBREW_PREFIX"):
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

    def test_autoconf_trace_output_must_work(self):
        fake = self.fake("bad-trace-m4", trace="unexpected trace")
        result = self.run_seed("--print-seed", WHP_M4_SEED=str(fake))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Autoconf trace output is incompatible", result.stderr)

    def test_autoconf_frozen_state_must_work(self):
        fake = self.fake("bad-freeze-m4", freeze=False)
        result = self.run_seed("--print-seed", WHP_M4_SEED=str(fake))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Autoconf frozen-state probe failed", result.stderr)

    def test_recursive_override_rejected(self):
        result = self.run_seed("--print-seed", WHP_M4_SEED=str(SEED))
        self.assertNotEqual(result.returncode, 0)


    def test_gnu_specific_override_precedes_legacy(self):
        result = self.run_seed("--libs", WHP_GNUM4_SEED=str(self.gm4),
                               WHP_M4_SEED=str(self.m4))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gm4))

    def test_generic_adapter_cannot_be_a_gnu_provider(self):
        result = self.run_seed("--print-seed",
                               WHP_GNUM4_SEED=str(ROOT / "seeds/m4.sh"))
        self.assertNotEqual(result.returncode, 0)

    def test_generic_non_gnu_m4_skipped_during_discovery(self):
        self.m4.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.m4.chmod(0o755)
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gm4))

    def test_non_gnu_explicit_fails_without_fallback(self):
        self.m4.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        self.m4.chmod(0o755)
        result = self.run_seed("--print-seed", M4=str(self.m4))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("M4 does not select GNU M4", result.stderr)

    def test_gnu_path_containing_spaces_and_apostrophe(self):
        candidate = self.directory / "gnu's M4 with spaces"
        self.gm4.rename(candidate)
        result = self.run_seed("--print-seed", WHP_GNUM4_SEED=str(candidate))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(candidate))

    def test_keg_only_homebrew_m4_without_cross_prefix_search(self):
        # macOS is simulated to avoid requiring actual Homebrew on CI.
        uname = self.directory / "uname"
        uname.write_text("#!/bin/sh\nprintf 'Darwin\n'", encoding="utf-8")
        prefix = self.directory / "brew-prefix"
        installed = prefix / "opt/m4/bin/m4"
        installed.parent.mkdir(parents=True, exist_ok=True)
        installed.write_text(self.m4.read_text(encoding="utf-8"),
                             encoding="utf-8")
        installed.chmod(0o755)
        brew = prefix / "bin/brew"
        brew.parent.mkdir(parents=True)
        brew.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  --whp-brew-adapter-probe) exit 2 ;;\n'
            '  --version) printf "Homebrew 5.2.0\\n" ;;\n'
            '  --prefix)\n'
            '    if [ "$#" -eq 1 ]; then printf "%s\\n" "$HOMEBREW_PREFIX"; exit 0; fi\n'
            '    if [ "$2" = --installed ] && [ "$3" = m4 ]; then\n'
            '      printf "%s\\n" "$HOMEBREW_PREFIX/opt/m4"; exit 0\n'
            '    fi\n'
            '    exit 2 ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        brew.chmod(0o755)
        common = {
            "PATH": f"{self.directory}:/usr/bin:/bin",
            "HOMEBREW_PREFIX": str(prefix),
            "WHP_BREW_SEED": str(brew),
            "WHP_HOMEBREW_BREW": "",
        }
        selected = self.run_seed(
            "--print-seed", WHP_MACOS_DEPENDENCY_PROVIDER="homebrew", **common,
        )
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout.strip(), str(installed))
        # MacPorts must not auto-select an unrelated Homebrew keg.
        selected = self.run_seed(
            "--print-seed", WHP_MACOS_DEPENDENCY_PROVIDER="macports", **common,
        )
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout.strip(), str(self.m4))

    def test_user_facing_check(self):
        result = self.run_seed("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("WHP GNU M4 seed:", result.stdout)


if __name__ == "__main__":
    unittest.main()
