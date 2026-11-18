#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Focused preflight, archive-signature and runtime guard regressions."""

from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
import subprocess
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
                "bootstrap", "configure.ac", "Makefile.am", "GNUmakefile",
                "bin/autoconf.in", "bin/autom4te.in",
                "doc/local.mk", "man/local.mk", "tests/local.mk",
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
                for name in ("GNUmakefile", "doc/local.mk",
                             "man/local.mk", "tests/local.mk"):
                    source = src / name
                    baseline = HELPER.archive_source_signature()
                    source.write_text("changed Makefile rules\n", encoding="utf-8")
                    self.assertNotEqual(
                        HELPER.archive_source_signature(), baseline, name
                    )

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

    def test_seed_git_is_used_for_submodule_reconciliation(self):
        with mock.patch.object(HELPER, "reconcile_submodule", return_value="rev") as called:
            self.assertEqual(HELPER.ensure_source("/validated/git"), "rev")
            called.assert_called_once_with(
                HELPER.ROOT, HELPER.SUBMODULE_REL, git="/validated/git"
            )

    def test_git_seed_override_is_authoritative(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".git").mkdir()
            with (
                mock.patch.object(HELPER, "ROOT", Path(tmp)),
                mock.patch.dict(HELPER.os.environ, {"WHP_GIT_SEED": "/seed/git"}),
                mock.patch.object(HELPER, "executable", return_value="/seed/git"),
                mock.patch.object(HELPER, "run_text", return_value="git version 2.48"),
            ):
                self.assertEqual(HELPER.select_bootstrap_git(), "/seed/git")
            with (
                mock.patch.object(HELPER, "ROOT", Path(tmp)),
                mock.patch.dict(HELPER.os.environ, {"WHP_GIT_SEED": "/bad/git"}),
                mock.patch.object(HELPER, "executable", return_value=None),
            ):
                with self.assertRaisesRegex(RuntimeError, "not executable"):
                    HELPER.select_bootstrap_git()

    def test_missing_seed_fails_before_source_reconciliation(self):
        with (
            mock.patch.object(HELPER, "select_automake_pair",
                              side_effect=RuntimeError("missing Automake seed")),
            mock.patch.object(HELPER, "ensure_source",
                              side_effect=AssertionError("source was accessed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "missing Automake seed"):
                HELPER.bootstrap(Path("/not-a-real-build-dir"))

    def test_installed_runtime_uses_selected_m4(self):
        with tempfile.TemporaryDirectory() as tmp:
            prefix = Path(tmp)
            bindir = prefix / "bin"
            bindir.mkdir()
            for name in HELPER.REQUIRED_BINARIES:
                path = bindir / name
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            observed = []
            def fake_run(argv, **kwargs):
                if argv[-1] == "--version":
                    return subprocess.CompletedProcess(
                        argv, 0, "tool (GNU Autoconf) 2.72\n", ""
                    )
                observed.append(kwargs["env"].get("M4"))
                self.assertNotIn("AUTOCONF", kwargs["env"])
                self.assertNotIn("PERL5OPT", kwargs["env"])
                self.assertNotIn("PERL5LIB", kwargs["env"])
                (kwargs["cwd"] / "configure").write_text("#!/bin/sh\n")
                return subprocess.CompletedProcess(argv, 0, "", "")
            with (
                mock.patch.object(HELPER.subprocess, "run", side_effect=fake_run),
                mock.patch.dict(HELPER.os.environ, {"M4": "/poison/m4",
                                                  "AUTOCONF": "/poison/autoconf",
                                                  "PERL5OPT": "-MUntrustedModule",
                                                  "PERL5LIB": "/other/perl/lib"}),
            ):
                self.assertTrue(HELPER.suite_usable(prefix, m4="/seed/m4"))
            self.assertEqual(observed, ["/seed/m4"])

    def test_text_tool_seed_admission(self):
        with tempfile.TemporaryDirectory(prefix="whp-autoconf-text-") as tmp:
            native = Path(tmp) / "selected-tool"
            native.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            native.chmod(0o755)
            good = subprocess.CompletedProcess(["seed"], 0, str(native) + "\n", "")
            with mock.patch.object(HELPER.subprocess, "run", return_value=good):
                self.assertEqual(HELPER.select_bootstrap_text_tool("awk"), str(native))
                self.assertEqual(HELPER.select_bootstrap_text_tool("grep"), str(native))
            bad = subprocess.CompletedProcess(["seed"], 0, "/nonexistent/tool\n", "")
            with mock.patch.object(HELPER.subprocess, "run", return_value=bad):
                with self.assertRaisesRegex(RuntimeError, "grep seed handshake failed"):
                    HELPER.select_bootstrap_text_tool("grep")
            with self.assertRaisesRegex(ValueError, "unsupported"):
                HELPER.select_bootstrap_text_tool("m4")

    def test_ln_seed_is_checked_before_source_access(self):
        with tempfile.TemporaryDirectory(prefix="whp-autoconf-ln-") as tmp:
            selected = Path(tmp) / "native-ln"
            selected.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            selected.chmod(0o755)
            good = subprocess.CompletedProcess(["ln-seed"], 0, str(selected) + "\n", "")
            with mock.patch.object(HELPER.subprocess, "run", return_value=good):
                self.assertEqual(HELPER.select_seed_ln(), str(selected))
            bad = subprocess.CompletedProcess(["ln-seed"], 1, "", "ln probe rejected")
            with mock.patch.object(HELPER.subprocess, "run", return_value=bad):
                with self.assertRaisesRegex(RuntimeError, "ln seed handshake failed"):
                    HELPER.select_seed_ln()

    def test_text_seed_paths_invalidate_autoconf_marker(self):
        with (
            mock.patch.object(HELPER, "first_line", return_value="version"),
            mock.patch.object(HELPER, "gnu_m4_version", return_value="GNU M4 1.4.19"),
        ):
            args = ("rev", "automake", "aclocal", "m4", "perl", "make", "sed")
            initial = HELPER.marker_text(*args, "/seed/awk", "/seed/grep", "/seed/ln", "cc", "sh")
            new_awk = HELPER.marker_text(*args, "/managed/gawk", "/seed/grep", "/seed/ln", "cc", "sh")
            new_grep = HELPER.marker_text(*args, "/seed/awk", "/other/grep", "/seed/ln", "cc", "sh")
            new_ln = HELPER.marker_text(*args, "/seed/awk", "/seed/grep", "/other/ln", "cc", "sh")
        self.assertIn("AWK=/seed/awk\n", initial)
        self.assertIn("GREP=/seed/grep\n", initial)
        self.assertIn("LN=/seed/ln\n", initial)
        self.assertNotEqual(initial, new_awk)
        self.assertNotEqual(initial, new_grep)
        self.assertNotEqual(initial, new_ln)

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
