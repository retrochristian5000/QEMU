#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test POSIX GNU Texinfo seed admission and dispatch without installed Texinfo."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds" / "makeinfo.sh"


class MakeinfoSeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-seed-makeinfo-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.tool = self.make_tool(self.bin / "makeinfo")
        self.env = os.environ.copy()
        for name in ("WHP_MAKEINFO_SEED", "MAKEINFO",
                     "WHP_AUTOMAKE_MAKEINFO_SEED"):
            self.env.pop(name, None)
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")

    def make_tool(self, path, banner="makeinfo (GNU texinfo) 7.2",
                  *, converts=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            f"  --version) printf '%s\\n' '{banner}' ;;\n"
            "  --whp-makeinfo-adapter-probe) exit 2 ;;\n"
            "  --no-split)\n"
            '    [ "$2" = -o ] || exit 11\n'
            + ('    printf "generated info\\n" > "$3"\n'
               if converts else '    exit 12\n')
            + "    ;;\n"
            '  *) printf "forward:%s\\n" "$1" ;;\n'
            "esac\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *args, overrides=None):
        env = self.env.copy()
        if overrides:
            env.update(overrides)
        return subprocess.run(
            ["/bin/sh", str(SEED), *args], env=env,
            text=True, capture_output=True, check=False, timeout=15,
        )

    def test_native_provider_lookup_and_exact_output(self):
        run = self.run_seed("--print-seed")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, str(self.tool) + "\n")

    def test_provider_identity_and_forwarding(self):
        run = self.run_seed("--check")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn(str(self.tool), run.stdout)
        self.assertIn("GNU texinfo", run.stdout)
        forwarded = self.run_seed("--custom-flag")
        self.assertEqual(forwarded.returncode, 0, forwarded.stderr)
        self.assertEqual(forwarded.stdout, "forward:--custom-flag\n")

    def test_explicit_path_with_spaces_keeps_invoked_symlink_name(self):
        directory = self.root / "external tools"
        actual = self.make_tool(directory / "texi2any",
                                "texi2any (GNU Texinfo) 7.2")
        alias = directory / "makeinfo"
        alias.symlink_to(actual.name)
        run = self.run_seed(
            "--print-seed", overrides={"WHP_MAKEINFO_SEED": str(alias)}
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, str(alias) + "\n")

    def test_generic_seed_beats_makeinfo_variable(self):
        run = self.run_seed("--print-seed", overrides={
            "WHP_MAKEINFO_SEED": str(self.tool),
            "MAKEINFO": str(self.root / "missing"),
        })
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, str(self.tool) + "\n")

    def test_explicit_missing_provider_never_falls_back(self):
        run = self.run_seed("--print-seed", overrides={
            "WHP_MAKEINFO_SEED": str(self.root / "missing"),
        })
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("invalid explicit", run.stderr)

    def test_explicit_command_with_arguments_is_rejected(self):
        run = self.run_seed("--print-seed", overrides={
            "WHP_MAKEINFO_SEED": "makeinfo --force",
        })
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("invalid explicit", run.stderr)

    def test_wrong_vendor_and_bad_converter_fail(self):
        for banner, converts, diagnostic in (
            ("Other docs generator 7.2", True, "not GNU Texinfo"),
            ("makeinfo (GNU texinfo) 7.2", False, "cannot convert"),
        ):
            with self.subTest(banner=banner, converts=converts):
                alternate = self.make_tool(
                    self.root / "other" / "makeinfo",
                    banner, converts=converts,
                )
                run = self.run_seed(
                    "--print-seed",
                    overrides={"WHP_MAKEINFO_SEED": str(alternate)},
                )
                self.assertNotEqual(run.returncode, 0)
                self.assertIn(diagnostic, run.stderr)

    def test_no_provider_reports_missing_tool(self):
        env = {"PATH": str(self.root / "empty-bin")}
        run = self.run_seed("--print-seed", overrides=env)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("GNU Texinfo makeinfo is required", run.stderr)

    def test_seed_cannot_select_itself_through_symlink(self):
        alias = self.root / "recursive" / "makeinfo"
        alias.parent.mkdir()
        alias.symlink_to(SEED)
        run = self.run_seed(
            "--print-seed", overrides={"WHP_MAKEINFO_SEED": str(alias)}
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("invalid explicit", run.stderr)

    def test_shell_syntax_remains_posix(self):
        checked = subprocess.run(
            ["/bin/sh", "-n", str(SEED)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
