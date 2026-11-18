#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline contract for the native Autoconf entry and shared autom4te pair."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/autoconf.sh"
PARTNER = ROOT / "seeds/autom4te.sh"
HOST_TOOLS = ROOT / "scripts/whp-build/host-tools.sh"


def fake(path: Path, version="2.72", family="GNU Autoconf"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        f'  --version) printf "%s\\n" "{path.name} ({family}) {version}" ;;\n'
        '  --whp-autom4te-adapter-probe|--whp-autoconf-adapter-probe) exit 2 ;;\n'
        '  *) printf "called:%s" "' + path.name + '"; '
        'for arg do printf ":%s" "$arg"; done; printf "\\n" ;;\n'
        'esac\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


class AutoconfSeedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="whp-autoconf-seed-")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.first = root / "first"
        self.second = root / "second"
        self.ac = self.first / "autoconf"
        self.am4 = self.first / "autom4te"
        self.other_ac = self.second / "autoconf"
        fake(self.ac)
        fake(self.am4)
        fake(self.other_ac, "2.71")
        self.env = {**os.environ,
                    "PATH": f"{self.first}{os.pathsep}{self.second}{os.pathsep}/usr/bin:/bin"}
        for name in ("WHP_AUTOCONF_SEED", "WHP_AUTOM4TE_SEED", "AUTOCONF", "AUTOM4TE"):
            self.env.pop(name, None)

    def run_seed(self, *args, **settings):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args], env={**self.env, **settings},
            text=True, capture_output=True, check=False, timeout=8,
        )

    def test_selects_autoconf_not_autom4te(self):
        selected = self.run_seed("--print-seed")
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(selected.stdout, str(self.ac) + "\n")
        self.assertEqual(self.run_seed("--print-autom4te").stdout, str(self.am4) + "\n")
        result = self.run_seed("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(self.ac), result.stdout)
        self.assertIn(str(self.am4), result.stdout)
        self.assertEqual(self.run_seed("--help", "--warn=all").stdout,
                         "called:autoconf:--help:--warn=all\n")

    def test_explicit_autoconf_uses_its_sibling(self):
        explicit_dir = self.second / "extra"
        ac = explicit_dir / "autoconf"
        am4 = explicit_dir / "autom4te"
        fake(ac, "2.73")
        fake(am4, "2.73")
        result = self.run_seed("--print-seed", WHP_AUTOCONF_SEED=str(ac))
        self.assertEqual(result.stdout, str(ac) + "\n", result.stderr)
        result = self.run_seed("--print-autom4te", WHP_AUTOCONF_SEED=str(ac))
        self.assertEqual(result.stdout, str(am4) + "\n", result.stderr)

    def test_explicit_split_pair_is_validated(self):
        self.ac.unlink()
        fake(self.other_ac)
        result = self.run_seed("--print-seed")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("adjacent", result.stderr)
        explicit = {"WHP_AUTOCONF_SEED": str(self.other_ac),
                    "WHP_AUTOM4TE_SEED": str(self.am4)}
        result = self.run_seed("--print-seed", **explicit)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.other_ac) + "\n")
        fake(self.other_ac, "2.71")
        result = self.run_seed("--print-seed", **explicit)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("mismatch", result.stderr)

    def test_invalid_override_never_falls_back(self):
        bad = str(self.second / "absent-autoconf")
        result = self.run_seed("--print-seed", WHP_AUTOCONF_SEED=bad)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid explicit", result.stderr)
        fake(self.other_ac, family="GNU automake")
        result = self.run_seed("--print-seed", WHP_AUTOCONF_SEED=str(self.other_ac))
        self.assertNotEqual(result.returncode, 0)

    def test_adapter_self_override_and_symlink_fail_without_recursion(self):
        for name in ("WHP_AUTOCONF_SEED", "AUTOCONF"):
            result = self.run_seed("--print-seed", **{name: str(SEED)})
            self.assertNotEqual(result.returncode, 0)
        linked = self.second / "autoconf-wrapper"
        linked.symlink_to(SEED)
        result = self.run_seed("--print-seed", WHP_AUTOCONF_SEED=str(linked))
        self.assertNotEqual(result.returncode, 0)
        assert self.run_seed("--whp-autom4te-adapter-probe").stdout == (
            "whp-qemu-autoconf-seed-adapter\n")

    def test_symlink_launcher_preserves_checkout_root(self):
        linked = self.second / "autoconf-entry"
        linked.symlink_to(SEED)
        result = subprocess.run(
            ["/bin/sh", str(linked), "--print-seed"], env=self.env,
            text=True, capture_output=True, check=False, timeout=8,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.ac) + "\n")

    def run_host_pair(self, first: Path, second: Path):
        # Test the real POSIX helper functions without launching QEMU build.sh.
        source = HOST_TOOLS.read_text(encoding="utf-8")
        start = source.index("whp_gnu_tool_version()\n")
        end = source.index("whp_automake_pair_usable()\n", start)
        functions = source[start:end]
        return subprocess.run(
            ["/bin/sh", "-c",
             functions + '\nwhp_gnu_tool_pair_usable "$1" "$2" "$3"\n',
             "test-host-tool-pair", str(first), str(second), "GNU Autoconf"],
            env=self.env, text=True, capture_output=True, check=False, timeout=8,
        )

    def test_pinned_git_revision_accepted_by_both_checks(self):
        release = "2.73.git-6a5081d00dfc"
        fake(self.ac, release)
        fake(self.am4, release)
        result = self.run_seed("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_host_pair(self.ac, self.am4)
        self.assertEqual(result.returncode, 0, result.stderr)

        fake(self.am4, "2.73.git-000000000000")
        self.assertNotEqual(self.run_seed("--check").returncode, 0)
        self.assertNotEqual(self.run_host_pair(self.ac, self.am4).returncode, 0)

    def test_pinned_archive_and_malformed_banners(self):
        archive = "2.73.archive-abcdef123456"
        fake(self.ac, archive)
        fake(self.am4, archive)
        self.assertEqual(self.run_seed("--check").returncode, 0)
        self.assertEqual(self.run_host_pair(self.ac, self.am4).returncode, 0)
        for value in (
            "2.73.git-", "2.73.git-short", "2.73.git-abcdef12345g",
            "2.73.archive-abcdef12345g", "2.73.other-abcdef123456",
            "2.73.git-abcdef123456-extra", "2.73.",
        ):
            with self.subTest(version=value):
                fake(self.ac, value)
                fake(self.am4, value)
                self.assertNotEqual(self.run_seed("--check").returncode, 0)
                self.assertNotEqual(
                    self.run_host_pair(self.ac, self.am4).returncode, 0
                )

    def test_explicit_path_with_spaces_is_one_executable(self):
        directory = self.second / "Autoconf tools with spaces"
        autoconf = directory / "autoconf"
        autom4te = directory / "autom4te"
        fake(autoconf, "2.73.git-6a5081d00dfc")
        fake(autom4te, "2.73.git-6a5081d00dfc")
        result = self.run_seed("--check", WHP_AUTOCONF_SEED=str(autoconf))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(autoconf), result.stdout)
        self.assertEqual(self.run_host_pair(autoconf, autom4te).returncode, 0)

    def test_host_selection_uses_dedicated_seed(self):
        source = HOST_TOOLS.read_text(encoding="utf-8")
        self.assertIn('seeds/autoconf.sh" --print-seed', source)
        self.assertIn('seeds/autom4te.sh" --print-seed', source)
        self.assertNotIn('seeds/autom4te.sh" --print-autoconf', source)


if __name__ == "__main__":
    unittest.main()
