#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise Perl's pinned make_ext.pl extension and legacy cleanup paths.

The tests use the validated host Perl seed and a fake Make executable. They
must run before compiling the fork and must never modify its source checkout.
"""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MAKE_EXT = ROOT / "toolchains/perl/make_ext.pl"
PERL_SEED = ROOT / "seeds/perl.sh"


def native_perl() -> str:
    result = subprocess.run(
        ["/bin/sh", str(PERL_SEED), "--print-seed"],
        capture_output=True, text=True, timeout=20, check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(
            "native Perl seed unavailable: " + result.stderr.strip()
        )
    return result.stdout.strip()


class PerlMakeExtCompatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not MAKE_EXT.is_file():
            raise RuntimeError("initialize pinned toolchains/perl first")
        cls.perl = native_perl()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-perl-make-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "Perl build with ' quote & spaces"
        self.root.mkdir()
        self.ext = self.root / "ext" / "Sample"
        self.ext.mkdir(parents=True)
        self.log = self.root / "make-calls.log"
        self.fake_make = self.root / "build tools with ' quote" / "GNU make"
        self.fake_make.parent.mkdir()
        self.fake_make.write_text(
            "#!/bin/sh\n"
            'printf "begin\\n" >> "$WHP_TEST_MAKE_LOG"\n'
            'for arg do printf "%s\\n" "$arg" >> "$WHP_TEST_MAKE_LOG"; done\n'
            'printf "end\\n" >> "$WHP_TEST_MAKE_LOG"\n'
            "exit 0\n",
            encoding="utf-8",
        )
        self.fake_make.chmod(0o755)
        (self.root / "miniperl").write_text(
            "#!/bin/sh\n"
            'exec "$WHP_TEST_PERL" "$@"\n', encoding="utf-8",
        )
        (self.root / "miniperl").chmod(0o755)
        (self.ext / "Makefile.PL").write_text(
            "use strict;\n"
            "use warnings;\n"
            "open my $fh, '>', 'Makefile' or die $!;\n"
            "print {$fh} \"all:\\n\\t\\@true\\n\";\n"
            "close $fh or die $!;\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["WHP_TEST_MAKE_LOG"] = str(self.log)
        self.env["WHP_TEST_PERL"] = self.perl

    def run_extension(self, make_string=None):
        selected = str(self.fake_make) if make_string is None else make_string
        return subprocess.run(
            [self.perl, str(MAKE_EXT), "--target=all",
             "Sample", "MAKE=" + selected],
            cwd=self.root, env=self.env, capture_output=True,
            text=True, check=False, timeout=20,
        )

    def run_cleanup(self, name):
        return subprocess.run(
            ["/bin/sh", str(self.root / (name + ".sh"))],
            cwd=self.root, env=self.env, capture_output=True,
            text=True, check=False, timeout=20,
        )

    def calls(self):
        if not self.log.is_file():
            return []
        data = self.log.read_text(encoding="utf-8").splitlines()
        groups, current = [], []
        for line in data:
            if line == "begin":
                self.assertFalse(current)
            elif line == "end":
                groups.append(current)
                current = []
            else:
                current.append(line)
        self.assertFalse(current)
        return groups

    def test_main_extension_build_preserves_make_path_with_spaces(self):
        result = self.run_extension()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.calls()[0][:2], ["all", "PERL_CORE=1"])
        self.assertTrue((self.root / "realclean.sh").is_file())

    def test_old_makefile_cleanup_uses_exact_selected_make(self):
        result = self.run_extension()
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.ext / "Makefile").rename(self.ext / "Makefile.old")
        cleaned = self.run_cleanup("realclean")
        self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
        self.assertIn("Note: Using Makefile.old", cleaned.stdout)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][:4], [
            "-f", "Makefile.old", "realclean", "MAKE=" + str(self.fake_make),
        ])
        self.assertIn("PERL_CORE=1", calls[1])

    def test_normal_makefile_cleanup_has_no_fallback_rediscovery(self):
        result = self.run_extension()
        self.assertEqual(result.returncode, 0, result.stderr)
        cleaned = self.run_cleanup("veryclean")
        self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
        calls = self.calls()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][:2], [
            "veryclean", "MAKE=" + str(self.fake_make),
        ])

    def test_legacy_make_with_flags_still_passes_flags(self):
        # Legacy platforms may pass "nmake -nologo" as a single MAKE value.
        plain = self.root / "plain-make"
        plain.symlink_to(self.fake_make)
        selection = str(plain) + " -s"
        result = self.run_extension(selection)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[0][:2], ["-s", "all"])
        cleaned = self.run_cleanup("veryclean")
        self.assertEqual(cleaned.returncode, 0, cleaned.stderr)
        self.assertEqual(self.calls()[1][:3], [
            "-s", "veryclean", "MAKE=" + selection,
        ])

    def test_cleanup_script_quotes_values_and_guards_cd(self):
        result = self.run_extension()
        self.assertEqual(result.returncode, 0, result.stderr)
        script = (self.root / "realclean.sh").read_text(encoding="utf-8")
        self.assertIn("cd 'ext/Sample' || exit 1", script)
        self.assertIn("cd '../..' || exit 1", script)
        self.assertNotIn("\n    make -f Makefile.old", script)
        self.assertIn("if test ! -f Makefile && test -f Makefile.old", script)

    def test_missing_extension_directory_cannot_run_unrelated_make(self):
        result = self.run_extension()
        self.assertEqual(result.returncode, 0, result.stderr)
        # The fallback cleanup script must abort when run from another tree
        # rather than execute a tool against an unrelated Makefile.
        other = self.root / "unrelated"
        other.mkdir()
        result = subprocess.run(
            ["/bin/sh", str(self.root / "realclean.sh")],
            cwd=other, env=self.env, capture_output=True, text=True,
            check=False, timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls()), 1)


if __name__ == "__main__":
    unittest.main()
