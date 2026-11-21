#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check optional native Zsh selection without building or replacing shells."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/zsh.sh"


class ZshSeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-zsh-seed-")
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.native = shutil.which("zsh")
        self.env = dict(os.environ)
        self.env.pop("WHP_ZSH_SEED", None)

    def run_seed(self, *args, override=None):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env=self.env if override is None else override,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )

    def test_explicit_bad_seed_never_falls_back(self):
        imitation = self.directory / "not-zsh"
        imitation.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        imitation.chmod(0o755)
        for candidate in (str(self.directory / "missing"), "zsh -f", "/bin/sh",
                          str(SEED), str(imitation)):
            with self.subTest(candidate=candidate):
                result = self.run_seed("--print-seed", override=dict(
                    self.env, WHP_ZSH_SEED=candidate))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("WHP_ZSH_SEED", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_copied_or_linked_adapter_cannot_recurse(self):
        copied = self.directory / "copied-zsh"
        copied.write_bytes(SEED.read_bytes())
        copied.chmod(0o755)
        alias = self.directory / "zsh-alias"
        alias.symlink_to(SEED)
        for candidate in (copied, alias):
            with self.subTest(candidate=str(candidate)):
                result = self.run_seed("--print-zsh", override=dict(
                    self.env, WHP_ZSH_SEED=str(candidate)))
                self.assertNotEqual(result.returncode, 0)

    def test_native_selection_and_argument_forwarding(self):
        if not self.native:
            self.skipTest("native Zsh is not installed")
        env = dict(self.env, WHP_ZSH_SEED=self.native)
        chosen = self.run_seed("--print-seed", override=env)
        self.assertEqual(chosen.returncode, 0, chosen.stderr)
        self.assertEqual(Path(chosen.stdout.strip()).resolve(),
                         Path(self.native).resolve())
        self.assertEqual(self.run_seed("--check", override=env).returncode, 0)
        cmd = 'items=(one two); print -rn -- "${items[1]}:$1"'
        run = self.run_seed("-c", cmd, "seed", "two words", override=env)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "one:two words")
        failure = self.run_seed("-c", "exit 19", override=env)
        self.assertEqual(failure.returncode, 19)

    def test_startup_hooks_do_not_control_selected_zsh(self):
        if not self.native:
            self.skipTest("native Zsh is not installed")
        dotdir = self.directory / "startup"
        dotdir.mkdir()
        (dotdir / ".zshenv").write_text("exit 79\n", encoding="utf-8")
        hook = self.directory / "shenv"
        hook.write_text("exit 79\n", encoding="utf-8")
        env = dict(self.env, WHP_ZSH_SEED=self.native,
                   ZDOTDIR=str(dotdir), ENV=str(hook))
        self.assertEqual(self.run_seed("--print-seed", override=env).returncode, 0)
        result = self.run_seed("-c", 'print -rn -- clean', override=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "clean")

    def test_invocation_options_fail_closed_without_tool_discovery(self):
        # These must fail at the seed boundary even when native Zsh is absent.
        # A later option can reverse -f or alter shell emulation.
        env = dict(self.env, WHP_ZSH_SEED="/bin/false")
        for args in (
            ("+f", "-c", "exit 0"),
            ("-o", "rcs", "-c", "exit 0"),
            ("--rcs", "-c", "exit 0"),
            ("+o", "norcs", "-c", "exit 0"),
            ("--emulate", "sh", "-c", "exit 0"),
            ("-i", "-c", "exit 0"),
            ("-l", "-c", "exit 0"),
            ("-r", "-c", "exit 0"),
            ("-fc", "exit 0"),
            ("+x", "-c", "exit 0"),
        ):
            with self.subTest(args=args):
                result = self.run_seed(*args, override=env)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("unsupported Zsh build-seed invocation option",
                              result.stderr)
                self.assertEqual(result.stdout, "")

        empty = self.run_seed("-c", override=env)
        self.assertEqual(empty.returncode, 2)
        self.assertIn("-c requires a command string", empty.stderr)

    def test_safe_invocation_options_and_positional_arguments(self):
        if not self.native:
            self.skipTest("native Zsh is not installed")
        env = dict(self.env, WHP_ZSH_SEED=self.native)
        # Native Zsh arrays and option state should survive the -f launch.
        command = (
            '[[ ! -o rcs ]] || exit 41; '
            '[[ ! -o shwordsplit ]] || exit 42; '
            'items=(one two); print -rn -- "${items[1]}:$1"'
        )
        output = self.run_seed("-c", command, "seed", "+f", override=env)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(output.stdout, "one:+f")

        # Syntax checks are nonexecuting and must remain available.
        parsed = self.run_seed("-n", "-c", "print -rn -- should-not-run",
                               override=env)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        self.assertEqual(parsed.stdout, "")

        script = self.directory / "native-script.zsh"
        script.write_text('print -rn -- "script:$1"\n', encoding="utf-8")
        script.chmod(0o600)
        executed = self.run_seed("--", str(script), "two words", override=env)
        self.assertEqual(executed.returncode, 0, executed.stderr)
        self.assertEqual(executed.stdout, "script:two words")

    def test_pipefail_option_requires_explicit_command(self):
        # Validate the seed-specific option before attempting Zsh discovery.
        env = dict(self.env, WHP_ZSH_SEED="/bin/false")
        no_command = self.run_seed("--pipefail", override=env)
        self.assertEqual(no_command.returncode, 2)
        self.assertIn("--pipefail requires", no_command.stderr)
        forbidden = self.run_seed("--pipefail", "+f", "-c", "exit 0",
                                  override=env)
        self.assertEqual(forbidden.returncode, 2)
        self.assertIn("unsupported Zsh build-seed invocation option",
                      forbidden.stderr)

    def test_pipeline_failures_opt_in_without_changing_default(self):
        if not self.native:
            self.skipTest("native Zsh is not installed")
        env = dict(self.env, WHP_ZSH_SEED=self.native)
        # With default Zsh semantics, only the last stage determines status.
        ordinary = self.run_seed("-c",
                                 '[[ ! -o pipe_fail ]] || exit 80; false | true',
                                 override=env)
        self.assertEqual(ordinary.returncode, 0, ordinary.stderr)

        # For bootstrap operations needing all stages, enable strict checks
        # explicitly; the same command must now report the producer failure.
        strict = self.run_seed("--pipefail", "-c",
                               '[[ -o pipe_fail ]] || exit 81; false | true',
                               override=env)
        self.assertEqual(strict.returncode, 1, strict.stderr)
        for command, expected in (
            ("true | true", 0),
            ("false | true | true", 1),
            ("true | false | true", 1),
            ("true | true | false", 1),
        ):
            with self.subTest(command=command):
                result = self.run_seed("--pipefail", "-c", command,
                                       override=env)
                self.assertEqual(result.returncode, expected, result.stderr)

        # pipestatus reports each stage regardless of PIPE_FAIL and must be
        # captured immediately after the pipeline it describes.
        statuses = self.run_seed(
            "-c",
            'false | true; print -rn -- "${pipestatus[1]}:${pipestatus[2]}"',
            override=env,
        )
        self.assertEqual(statuses.returncode, 0, statuses.stderr)
        self.assertEqual(statuses.stdout, "1:0")

        # A successful producer should preserve output byte-for-byte.
        result = self.run_seed("--pipefail", "-c",
                               'print -rn -- "pipe data" | cat', override=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "pipe data")

    def test_seed_is_a_posix_launcher(self):
        self.assertEqual(SEED.read_text(encoding="utf-8").splitlines()[0],
                         "#!/bin/sh")
        result = subprocess.run(["/bin/sh", "-n", str(SEED)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
