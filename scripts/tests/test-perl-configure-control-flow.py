#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline POSIX control-flow tests for the pinned Perl Configure fork."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PERL = ROOT / "toolchains/perl"


class PerlShellControlFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for name in ("Configure", "configure.gnu"):
            if not (PERL / name).is_file():
                raise RuntimeError(f"initialize the pinned Perl submodule first: {name}")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-perl-if-while-")
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name) / "work dir"
        self.work.mkdir()
        self.argv_log = self.work / "argv"
        (self.work / "Configure").write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$@" > "$WHP_TEST_ARGV"\n',
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        for key in ("CC", "CFLAGS", "DEFS", "LDFLAGS"):
            self.env.pop(key, None)
        self.env["WHP_TEST_ARGV"] = str(self.argv_log)

    def frontend(self, *args, env=None):
        return subprocess.run(
            ["/bin/sh", str(PERL / "configure.gnu"), *args],
            cwd=self.work,
            env=env or self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )

    def test_while_loop_preserves_options_and_quoted_values(self):
        prefix = str(self.work / "install path's files")
        result = self.frontend(
            "--verbose", "--no-create", "--cache-file", "ignored.cache",
            "--prefix", prefix, "bare'argument", "--version",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.argv_log.read_text(encoding="utf-8").splitlines(), [
            "-V", "-d", "-E", "-Dprefix=" + prefix, "bare'argument",
        ])

    def test_split_and_joined_prefix_are_equivalent(self):
        for args in (("--prefix=dir with spaces",),
                     ("--prefix", "dir with spaces")):
            with self.subTest(args=args):
                result = self.frontend(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    self.argv_log.read_text(encoding="utf-8").splitlines(),
                    ["-ds", "-e", "-Dprefix=dir with spaces"],
                )

    def test_missing_option_values_cannot_consume_next_option(self):
        for args in (("--prefix",), ("--prefix=",),
                     ("--prefix", "--verbose"), ("--cache-file",),
                     ("--cache-file", "--verbose"), ("--unsupported",)):
            with self.subTest(args=args):
                self.argv_log.unlink(missing_ok=True)
                result = self.frontend(*args)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(self.argv_log.exists())

    def test_environment_values_are_not_evaluated_as_shell_code(self):
        injected = self.work / "unexpected-file"
        env = self.env.copy()
        env.update({
            "CC": f"cc'; touch '{injected}'; echo '",
            "DEFS": "-DCORE=1",
            "CFLAGS": "-O2 -DNAME='some value'",
            "LDFLAGS": "-Wl,-rpath,$(touch impossible)",
        })
        result = self.frontend("--prefix", "path' with spaces", env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(injected.exists())
        self.assertEqual(self.argv_log.read_text(encoding="utf-8").splitlines(), [
            "-ds", "-e", "-Dprefix=path' with spaces",
            "-Dcc=" + env["CC"],
            "-Dccflags=-DCORE=1 -O2 -DNAME='some value'",
            "-Dldflags=" + env["LDFLAGS"],
        ])

    def configure_early_stage(self):
        source = (PERL / "Configure").read_text(encoding="utf-8")
        _, anchor, _ = source.partition("\nccname=''\n")
        self.assertTrue(anchor, "Configure's early directory boundary moved")
        return source.split(anchor, 1)[0] + (
            "\nprintf 'entered UU\\n' > ./whp-stage-marker\n"
        )

    def test_configure_if_branch_fails_closed_on_bad_uu(self):
        (self.work / "UU").write_text("not a directory", encoding="utf-8")
        result = subprocess.run(
            ["/bin/sh", "-c", self.configure_early_stage()],
            cwd=self.work, env=self.env, capture_output=True, text=True,
            check=False, timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot create UU working directory", result.stderr)
        self.assertFalse((self.work / "whp-stage-marker").exists())

    def test_configure_changes_to_uu_before_running_next_stage(self):
        result = subprocess.run(
            ["/bin/sh", "-c", self.configure_early_stage()],
            cwd=self.work, env=self.env, capture_output=True, text=True,
            check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.work / "whp-stage-marker").exists())
        self.assertEqual(
            (self.work / "UU" / "whp-stage-marker").read_text(encoding="utf-8"),
            "entered UU\n",
        )

    def test_both_shell_entrypoints_pass_posix_syntax_check(self):
        for name in ("Configure", "configure.gnu"):
            with self.subTest(name=name):
                syntax = subprocess.run(
                    ["/bin/sh", "-n", str(PERL / name)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(syntax.returncode, 0, syntax.stderr)


if __name__ == "__main__":
    unittest.main()
