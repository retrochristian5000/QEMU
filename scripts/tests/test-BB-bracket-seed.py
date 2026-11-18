#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Separate the BusyBox [ applet from the POSIX external [ and shell builtin."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds" / "BB[.sh"
GENERIC = ROOT / "seeds" / "[.sh"


class BusyBoxBracketTests(unittest.TestCase):
    def setUp(self) -> None:
        work = tempfile.TemporaryDirectory(prefix="whp-bb-bracket-test-")
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.native = next(
            (path for path in (Path("/usr/bin/["), Path("/bin/["))
             if path.is_file() and os.access(path, os.X_OK)),
            None,
        )
        if self.native is None:
            self.skipTest("standalone POSIX [ is unavailable")
        self.bin = self.root / "provider with spaces"
        self.bin.mkdir()
        self.fake = self.bin / "busybox"
        self.fake.write_text(
            r"""#!/bin/sh
case "${1:-}" in
    --help)
        printf '%s\n' "${TEST_BB_BANNER:-BusyBox v1.37.0 (test) multi-call binary.}"
        exit 0 ;;
    --list)
        printf '%s\n' "${TEST_BB_APPLETS:-[
sh}"
        exit 0 ;;
    '[')
        shift
        [ "${TEST_BB_ALWAYS_TRUE:-0}" != 1 ] || exit 0
        [ "${TEST_BB_BANNER_ONLY:-0}" != 1 ] || exit 2
        exec "$TEST_NATIVE_BRACKET" "$@" ;;
    *) exit 2 ;;
esac
""",
            encoding="utf-8",
        )
        self.fake.chmod(0o755)
        self.env = os.environ.copy()
        for name in (
            "WHP_BB_BRACKET_SEED", "WHP_BRACKET_SEED",
            "TEST_BB_BANNER", "TEST_BB_APPLETS", "TEST_BB_ALWAYS_TRUE",
            "TEST_BB_BANNER_ONLY",
        ):
            self.env.pop(name, None)
        self.env["TEST_NATIVE_BRACKET"] = str(self.native)
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")

    def invoke(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env={**self.env, **env},
            text=True, capture_output=True, check=False, timeout=30,
        )

    def test_provider_is_busybox_and_does_not_inherit_generic_bracket(self) -> None:
        result = self.invoke(
            "--print-seed", WHP_BB_BRACKET_SEED=str(self.fake),
            WHP_BRACKET_SEED="/not-a-provider/standalone-bracket",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.fake))
        report = self.invoke("--check", WHP_BB_BRACKET_SEED=str(self.fake))
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertIn("WHP BusyBox [ seed:", report.stdout)
        self.assertIn("WHP BusyBox [ -ef:", report.stdout)

    def test_predicates_preserve_false_and_syntax_error(self) -> None:
        provider = {"WHP_BB_BRACKET_SEED": str(self.fake)}
        self.assertEqual(self.invoke("-n", "value", "]", **provider).returncode, 0)
        self.assertEqual(self.invoke("-n", "", "]", **provider).returncode, 1)
        self.assertEqual(self.invoke("-n", "value", **provider).returncode, 2)
        self.assertEqual(self.invoke("-n", "value", "not-]", **provider).returncode, 2)
        self.assertEqual(self.invoke("]", "=", "]", "]", **provider).returncode, 0)

    def test_recursion_and_external_bracket_are_not_busybox(self) -> None:
        link = self.bin / "busybox-loop"
        link.symlink_to(SEED)
        for candidate in (SEED, link, GENERIC, self.native):
            with self.subTest(candidate=candidate):
                result = self.invoke(
                    "--print-seed", WHP_BB_BRACKET_SEED=str(candidate),
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid BusyBox [ seed", result.stderr)

    def test_invalid_explicit_override_never_falls_back(self) -> None:
        for path in ("/missing/busybox", str(self.bin / "missing")):
            with self.subTest(path=path):
                r = self.invoke("--print-seed", WHP_BB_BRACKET_SEED=path)
                self.assertNotEqual(r.returncode, 0)
                self.assertIn("WHP_BB_BRACKET_SEED", r.stderr)

    def test_version_and_applet_claim_require_actual_predicates(self) -> None:
        for variant in (
            {"TEST_BB_BANNER": "Not BusyBox v1.37 multi-call binary."},
            {"TEST_BB_APPLETS": "sh\\nash"},
            {"TEST_BB_ALWAYS_TRUE": "1"},
            {"TEST_BB_BANNER_ONLY": "1"},
        ):
            with self.subTest(variant=variant):
                r = self.invoke(
                    "--print-seed", WHP_BB_BRACKET_SEED=str(self.fake),
                    **variant,
                )
                self.assertNotEqual(r.returncode, 0)

    def test_default_busybox_discovery(self) -> None:
        r = self.invoke("--print-seed")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(self.fake))

    def test_generic_bracket_remains_independent(self) -> None:
        # The native adapter selects an external '[', never our BusyBox applet.
        if not GENERIC.is_file():
            self.skipTest("generic [ seed is absent from this fixture")
        r = subprocess.run(
            ["/bin/sh", str(GENERIC), "--print-seed"],
            env={**self.env, "WHP_BRACKET_SEED": str(self.native),
                 "WHP_BB_BRACKET_SEED": "/missing/busybox"},
            text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(self.native))

    def test_real_busybox_if_installed(self) -> None:
        real = shutil.which("busybox")
        if not real:
            self.skipTest("BusyBox executable not installed")
        r = self.invoke("--print-seed", WHP_BB_BRACKET_SEED=real)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(Path(r.stdout.strip()).is_file())


if __name__ == "__main__":
    unittest.main()
