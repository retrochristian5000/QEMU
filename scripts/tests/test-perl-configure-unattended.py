#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Perl Configure's development-release and unattended execution contract."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "whp_perl_configure", ROOT / "scripts" / "ensure-perl.py"
)
assert SPEC and SPEC.loader
perl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(perl)


class PerlConfigureTests(unittest.TestCase):
    def configure(self, minor: int):
        with tempfile.TemporaryDirectory(prefix="whp-perl-configure-") as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text(
                f"#define PERL_REVISION 5\n#define PERL_VERSION\t{minor}\t/* epoch */\n"
                "#define PERL_SUBVERSION 5\n", encoding="utf-8"
            )
            return perl.configure_arguments(source, source / "prefix", "/usr/bin/cc")

    def test_odd_development_series_requires_explicit_consent(self):
        args = self.configure(45)
        self.assertIn("-des", args)
        self.assertIn("-Dusedevel", args)
        self.assertIn("-Uuseshrplib", args)

    def test_even_stable_series_does_not_enable_development(self):
        args = self.configure(44)
        self.assertIn("-des", args)
        self.assertNotIn("-Dusedevel", args)

    def test_unknown_source_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text("#define PERL_VERSION bad\n")
            with self.assertRaisesRegex(RuntimeError, "PERL_VERSION"):
                perl.configure_arguments(source, source / "prefix", "cc")

    def test_configure_cannot_read_interactive_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Configure").write_text(
                '#!/bin/sh\n'
                'if IFS= read -r answer; then\n'
                '  echo "interactive input accepted" >&2; exit 31\n'
                'fi\n'
                'printf "unattended\\n"\n',
                encoding="utf-8",
            )
            result = perl.run(
                ["/bin/sh", "./Configure", "-des"], cwd=source,
                unattended=True, capture=True, timeout=5,
            )
            self.assertEqual(result, "unattended\n")

    def test_subprocess_timeout_has_actionable_error(self):
        with mock.patch.object(
            perl.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(["/bin/sh", "Configure"], 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "exceeded 1s"):
                perl.run(["/bin/sh", "Configure"], unattended=True, timeout=1)

    def test_failed_configure_propagates_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Configure").write_text(
                '#!/bin/sh\nprintf "failed\\n" >&2\nexit 6\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "failed"):
                perl.run(["/bin/sh", "./Configure", "-des"], cwd=source,
                         unattended=True, capture=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
