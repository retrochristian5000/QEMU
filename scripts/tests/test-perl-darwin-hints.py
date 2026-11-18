#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise pinned Perl Darwin hints with a POSIX shell, without building Perl."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HINTS = ROOT / "toolchains/perl/hints/darwin.sh"


class DarwinHintsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HINTS.is_file():
            raise RuntimeError("initialize pinned Perl submodule before Darwin hints tests")
        cls.source = HINTS.read_text(encoding="utf-8")
        beginning = cls.source.index("add_macosx_version_min () {")
        end = cls.source.index("\n# Perl bundles do not expect", beginning)
        cls.helpers = cls.source[beginning:end]
        beginning = cls.source.index('    if test -n "${MACOSX_DEPLOYMENT_TARGET-}"; then')
        end = cls.source.index("\n    darwin_major=", beginning)
        cls.target_rules = cls.source[beginning:end]
        cls.api_rules = cls.source[cls.source.index("# dup3() and pipe2()"):]

    def run_shell(self, script, **env):
        environment = dict(os.environ, **env)
        return subprocess.run(
            ["/bin/sh", "-c", "exec 4>/dev/null\n" + script],
            text=True, capture_output=True, check=False,
            env=environment, timeout=10,
        )

    def test_all_hints_have_posix_shell_syntax(self):
        result = subprocess.run(
            ["/bin/sh", "-n", str(HINTS)], text=True,
            capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_accepted_deployment_targets_preserve_arm64e_flags(self):
        for target in ("10.15", "11.0", "15.0", "26.3", "27.0", ""):
            with self.subTest(target=target):
                script = (
                    self.helpers +
                    '\nccflags="-O2 -arch arm64e"\n'
                    'ldflags="-Wl,-dead_strip"\n'
                    'lddlflags="-bundle"\n'
                    + self.target_rules +
                    '\nprintf "CC=%s\\nLD=%s\\nDL=%s\\n" "$ccflags" "$ldflags" "$lddlflags"\n'
                )
                result = self.run_shell(script, MACOSX_DEPLOYMENT_TARGET=target)
                self.assertEqual(result.returncode, 0, result.stderr)
                lines = result.stdout.splitlines()
                self.assertEqual(len(lines), 3, lines)
                self.assertIn("-arch arm64e", lines[0])
                for line in lines:
                    self.assertEqual(
                        line.count("-mmacosx-version-min="),
                        1 if target else 0,
                        line,
                    )
                    if target:
                        self.assertIn("-mmacosx-version-min=" + target, line)

    def test_rejects_malformed_and_shell_metacharacter_targets(self):
        with tempfile.TemporaryDirectory(prefix="whp-darwin-hints-") as directory:
            unexpected = Path(directory) / "injected"
            invalid = (
                "15.", "15..0", "15.0beta", ".15",
                "1.2", "15.0; touch " + str(unexpected),
                "15.0' ; touch '" + str(unexpected),
                "15.0\nmalformed",
            )
            script = (
                self.helpers +
                '\nccflags="-O2"\nldflags=""\nlddlflags=""\n'
                + self.target_rules + '\nprintf "accepted\\n"\n'
            )
            for value in invalid:
                with self.subTest(value=value):
                    result = self.run_shell(
                        script, MACOSX_DEPLOYMENT_TARGET=value
                    )
                    self.assertNotEqual(result.returncode, 0, value)
                    self.assertNotIn("accepted", result.stdout)
                    self.assertFalse(unexpected.exists())

    def test_existing_deployment_floor_is_not_duplicated(self):
        script = (
            self.helpers +
            '\nccflags="-O2 -mmacosx-version-min=14.0"\n'
            'add_macosx_version_min ccflags 15.0\n'
            'printf "%s\\n" "$ccflags"\n'
        )
        result = self.run_shell(script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "-O2 -mmacosx-version-min=14.0")

    def test_unknown_destination_is_rejected_without_eval(self):
        self.assertNotIn("eval ", self.helpers)
        self.assertNotIn("local ", self.helpers.split("\n", 2)[-1])
        script = self.helpers + "\nadd_macosx_version_min unexpected 15.0\n"
        result = self.run_shell(script)
        self.assertNotEqual(result.returncode, 0)

    def test_api_detection_uses_the_documented_darwin_27_floor(self):
        for kernel in ("24.6.0", "25.0.0", "26.0.0", "26.9.0",
                       "27.0.0", "28.0.0"):
            with self.subTest(kernel=kernel):
                script = (
                    'd_dup3=define\nd_pipe2=define\n'
                    + self.api_rules
                    + '\nprintf "%s:%s\\n" "$d_dup3" "$d_pipe2"\n'
                )
                result = self.run_shell(script, osvers=kernel)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout.strip(),
                    "undef:undef" if int(kernel.split(".")[0]) < 27
                    else "define:define",
                )


if __name__ == "__main__":
    unittest.main()
