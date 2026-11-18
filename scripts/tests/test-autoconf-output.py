#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check warning visibility, full stage logs and explicit verbose mode."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "whp_autoconf_output", ROOT / "scripts/ensure-autoconf.py"
)
assert SPEC and SPEC.loader
HELPER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(HELPER)


class AutoconfOutputTests(unittest.TestCase):
    def test_quiet_success_shows_warning_not_routine_make(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = Path(root) / "logs with spaces"
            messages = io.StringIO()
            script = (
                "print('ordinary compiler line')\n"
                "print('configure.ac:2: warning: obsolete macro')\n"
                "print('another ordinary line')\n"
            )
            with redirect_stderr(messages):
                HELPER.run_logged(
                    [sys.executable, "-c", script],
                    stage="configure", log_dir=log_dir,
                )
            report = messages.getvalue()
            self.assertIn("passed; 1 warning(s), 0 error(s)", report)
            self.assertIn("warning: obsolete macro", report)
            self.assertNotIn("ordinary compiler line", report)
            log = (log_dir / "configure.log").read_text()
            self.assertIn("ordinary compiler line", log)
            self.assertIn("another ordinary line", log)

    def test_failed_stage_shows_diagnostic_and_tail(self):
        with tempfile.TemporaryDirectory() as root:
            log_dir = Path(root) / "logs"
            messages = io.StringIO()
            script = (
                "import sys\n"
                "print('configure: error: selected M4 failed', flush=True)\n"
                "for n in range(75): print('installing file %d' % n)\n"
                "sys.exit(17)\n"
            )
            with redirect_stderr(messages):
                with self.assertRaisesRegex(
                    RuntimeError, r"Autoconf build failed \(exit 17\)"
                ):
                    HELPER.run_logged(
                        [sys.executable, "-c", script],
                        stage="build", log_dir=log_dir,
                    )
            report = messages.getvalue()
            self.assertIn("1 error(s)", report)
            self.assertIn("configure: error: selected M4 failed", report)
            self.assertIn("Last 24 log lines", report)
            self.assertNotIn("installing file 0", report)
            self.assertIn("installing file 74", report)
            self.assertIn("installing file 0",
                          (log_dir / "build.log").read_text())

    def test_verbose_streams_full_output(self):
        with tempfile.TemporaryDirectory() as root:
            messages = io.StringIO()
            script = (
                "print('configure: warning: observed')\n"
                "print('ordinary installation line')\n"
            )
            with redirect_stderr(messages):
                HELPER.run_logged(
                    [sys.executable, "-c", script],
                    stage="install", log_dir=Path(root), verbose=True,
                )
            self.assertIn("ordinary installation line", messages.getvalue())
            self.assertIn("1 warning(s)", messages.getvalue())
            self.assertIn(
                "ordinary installation line",
                (Path(root) / "install.log").read_text(),
            )

    def test_cli_and_environment_select_verbosity(self):
        for env, args in (
            ("1", ["--build-dir", "/tmp/example"]),
            ("0", ["--build-dir", "/tmp/example", "--verbose"]),
        ):
            with self.subTest(env=env, args=args):
                with (
                    mock.patch.object(
                        HELPER, "bootstrap", return_value=Path("/tmp/example")
                    ) as invoked,
                    mock.patch.dict(
                        HELPER.os.environ, {"WHP_AUTOCONF_VERBOSE": env}
                    ),
                    redirect_stdout(io.StringIO()),
                ):
                    self.assertEqual(HELPER.main(args), 0)
                    self.assertTrue(invoked.call_args.kwargs["verbose"])

    def test_log_stage_name_is_validated(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "invalid Autoconf log stage"):
                HELPER.run_logged(
                    [sys.executable, "-c", "pass"],
                    stage="../outside", log_dir=Path(root),
                )
            self.assertFalse((Path(root).parent / "outside.log").exists())


if __name__ == "__main__":
    unittest.main()
