#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Focused preflight, archive-signature and runtime guard regressions."""

from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "whp_ensure_autoconf_validation", ROOT / "scripts/ensure-autoconf.py"
)
assert SPEC and SPEC.loader
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class AutoconfPreflightTests(unittest.TestCase):
    def test_version_marker_ignores_leading_blank_lines(self):
        with mock.patch.object(HELPER, "run_text", return_value="\n\nThis is perl 5.40\n"):
            self.assertEqual(HELPER.first_line(["perl", "--version"]), "This is perl 5.40")
        with mock.patch.object(HELPER, "run_text", return_value="  \n\t\n"):
            with self.assertRaisesRegex(RuntimeError, "no text"):
                HELPER.first_line(["perl", "--version"])

    def test_parallel_jobs_preflight(self):
        with mock.patch.object(HELPER.os, "cpu_count", return_value=4):
            self.assertEqual(HELPER.parallel_jobs(None), 4)
            self.assertEqual(HELPER.parallel_jobs(""), 4)
        self.assertEqual(HELPER.parallel_jobs("2"), 2)
        for invalid in ("0", "-1", "2.5", "2 jobs", "not-a-number"):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(RuntimeError, "JOBS must"):
                    HELPER.parallel_jobs(invalid)

    def test_archive_signature_tracks_m4_and_perl_without_generated_noise(self):
        with tempfile.TemporaryDirectory(prefix="whp-autoconf-source-") as root:
            src = Path(root)
            for name in (
                "bootstrap", "configure.ac", "Makefile.am",
                "bin/autoconf.in", "bin/autom4te.in",
                "m4/m4.m4", "lib/m4sugar/m4sugar.m4",
                "lib/Autom4te/General.pm",
            ):
                p = src / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("source\n", encoding="utf-8")
            with mock.patch.object(HELPER, "SUBMODULE_DIR", src):
                baseline = HELPER.archive_source_signature()
                (src / "lib/autoconf").mkdir()
                (src / "lib/autoconf/new.m4").write_text("macro\n")
                self.assertNotEqual(HELPER.archive_source_signature(), baseline)
                baseline = HELPER.archive_source_signature()
                (src / "lib/Autom4te/General.pm").write_text("changed\n")
                self.assertNotEqual(HELPER.archive_source_signature(), baseline)
                baseline = HELPER.archive_source_signature()
                (src / "lib/autom4te.m4f").write_text("generated\n")
                self.assertEqual(HELPER.archive_source_signature(), baseline)

    def test_all_installed_commands_are_required(self):
        with tempfile.TemporaryDirectory(prefix="whp-autoconf-install-") as root:
            prefix = Path(root)
            bindir = prefix / "bin"
            bindir.mkdir()
            # Version commands need not execute a real Autoconf binary here.
            for name in HELPER.REQUIRED_BINARIES:
                tool = bindir / name
                tool.write_text(
                    "#!/bin/sh\n"
                    "if [ \"${1:-}\" = --version ]; then\n"
                    " printf '%s\\n' 'tool (GNU Autoconf) 2.72'\n"
                    " exit 0\n"
                    "fi\n"
                    "printf '#!/bin/sh\\nexit 0\\n' > configure\n",
                    encoding="utf-8",
                )
                tool.chmod(0o755)
            self.assertTrue(HELPER.suite_usable(prefix))
            for name in HELPER.REQUIRED_BINARIES:
                missing = bindir / name
                missing.rename(bindir / f"{name}.disabled")
                with redirect_stderr(io.StringIO()) as messages:
                    self.assertFalse(HELPER.suite_usable(prefix))
                self.assertIn(str(missing), messages.getvalue())
                (bindir / f"{name}.disabled").rename(missing)

    def test_wrong_version_is_diagnosed(self):
        with tempfile.TemporaryDirectory(prefix="whp-autoconf-version-") as root:
            bindir = Path(root) / "bin"
            bindir.mkdir()
            fake = bindir / HELPER.REQUIRED_BINARIES[0]
            fake.write_text("#!/bin/sh\nprintf 'wrong version\\n'\n", encoding="utf-8")
            fake.chmod(0o755)
            with redirect_stderr(io.StringIO()) as messages:
                self.assertFalse(HELPER.suite_usable(Path(root)))
            self.assertIn("wrong version", messages.getvalue())


if __name__ == "__main__":
    unittest.main()
