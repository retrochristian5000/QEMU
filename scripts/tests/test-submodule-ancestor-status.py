#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise POSIX submodule if/else exit status handling without network."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/whp-build/shell-functions.sh"
PIN = "a" * 40
CURRENT = "b" * 40

FAKE_GIT = r"""#!/bin/sh
printf '%s\n' "$*" >> "$TEST_TRACE"
case "$*" in
    *" ls-tree HEAD -- modules/a")
        printf '160000 commit %s\tmodules/a\n' "$TEST_PIN"
        exit 0 ;;
    *" rev-parse --show-toplevel")
        printf '%s\n' "$TEST_MODULE"
        exit 0 ;;
    *" rev-parse HEAD")
        cat "$TEST_HEAD"
        exit 0 ;;
    *" cat-file --batch-check="*)
        IFS= read -r object
        [ "$object" = "$TEST_PIN" ] || exit 88
        [ "$TEST_CAT_STATUS" = 0 ] || exit "$TEST_CAT_STATUS"
        case "$TEST_OBJECT" in
            missing)
                if grep -q ' fetch ' "$TEST_TRACE"; then
                    printf '%s commit\n' "$object"
                else
                    printf '%s missing\n' "$object"
                fi ;;
            *) printf '%s %s\n' "$object" "$TEST_OBJECT" ;;
        esac
        exit 0 ;;
    *" merge-base --is-ancestor "*)
        case "$TEST_MODE" in
            fatal_first) exit 128 ;;
            fatal_reverse)
                case "$*" in
                    *" $TEST_PIN $TEST_CURRENT") exit 1 ;;
                    *) exit 128 ;;
                esac ;;
            fatal_after_fetch)
                if grep -q ' fetch ' "$TEST_TRACE"; then exit 128; fi
                exit 1 ;;
            descendant)
                case "$*" in
                    *" $TEST_PIN $TEST_CURRENT") exit 0 ;;
                    *) exit 1 ;;
                esac ;;
            fast_forward)
                case "$*" in
                    *" $TEST_CURRENT $TEST_PIN") exit 0 ;;
                    *) exit 1 ;;
                esac ;;
            divergent) exit 1 ;;
        esac
        exit 99 ;;
    *" rev-parse --is-shallow-repository")
        printf 'true\n'
        exit 0 ;;
    *" fetch "*) exit 0 ;;
    *" status --porcelain --untracked-files=all") exit 0 ;;
    *" symbolic-ref -q HEAD") exit 1 ;;
    *" submodule update --init --no-fetch -- modules/a")
        printf '%s\n' "$TEST_PIN" > "$TEST_HEAD"
        exit 0 ;;
esac
printf 'unexpected fake Git call: %s\n' "$*" >&2
exit 88
"""


class SubmoduleAncestorStatusTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-git-if-status-")
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.parent = root / "parent with spaces"
        self.submodule = self.parent / "modules" / "a"
        self.submodule.mkdir(parents=True)
        (self.submodule / ".git").write_text("gitdir: fixture\n", encoding="utf-8")
        self.head = root / "submodule-head"
        self.head.write_text(CURRENT + "\n", encoding="utf-8")
        self.trace = root / "git-trace"
        self.wrapper = root / "fake-git"
        self.wrapper.write_text(FAKE_GIT, encoding="utf-8")
        self.wrapper.chmod(0o755)

    def run_prepare(self, mode, *, access="online", cat_status="0", object_type="commit"):
        env = os.environ.copy()
        env.update(
            TEST_TRACE=str(self.trace), TEST_PIN=PIN, TEST_CURRENT=CURRENT,
            TEST_MODULE=str(self.submodule), TEST_HEAD=str(self.head),
            TEST_MODE=mode, TEST_CAT_STATUS=cat_status, TEST_OBJECT=object_type,
        )
        result = subprocess.run(
            ["/bin/sh", "-c",
             '. "$1"; whp_git_submodule_prepare "$2" modules/a "$3" "$4"',
             "whp-submodule-status-test", str(HELPER), str(self.parent),
             str(self.wrapper), access],
            env=env, text=True, capture_output=True, timeout=10,
            check=False,
        )
        trace = self.trace.read_text(encoding="utf-8") if self.trace.exists() else ""
        return result, trace

    def assert_no_unsafe_actions(self, trace):
        self.assertNotIn(" fetch ", trace)
        self.assertNotIn("submodule update", trace)

    def test_git_ancestry_error_fails_before_fetch_or_checkout(self):
        result, trace = self.run_prepare("fatal_first")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git ancestry probe failed", result.stderr)
        self.assertIn("exit 128", result.stderr)
        self.assert_no_unsafe_actions(trace)
        self.assertEqual(self.head.read_text(encoding="utf-8").strip(), CURRENT)

    def test_reverse_ancestry_error_is_not_a_shallow_history_miss(self):
        result, trace = self.run_prepare("fatal_reverse")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git ancestry probe failed", result.stderr)
        self.assert_no_unsafe_actions(trace)

    def test_failed_cat_file_is_not_treated_as_missing_history(self):
        result, trace = self.run_prepare("descendant", cat_status="128")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot inspect pinned submodule commit", result.stderr)
        self.assertNotIn("merge-base", trace)
        self.assert_no_unsafe_actions(trace)

    def test_missing_pin_is_fetched_and_rechecked(self):
        result, trace = self.run_prepare("fast_forward", object_type="missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(trace.count(" fetch "), 1)
        self.assertEqual(trace.count(" cat-file --batch-check="), 2)
        self.assertEqual(self.head.read_text(encoding="utf-8").strip(), PIN)

    def test_missing_pin_offline_does_not_fetch(self):
        result, trace = self.run_prepare("fast_forward", access="offline",
                                         object_type="missing")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pin history missing for offline submodule", result.stderr)
        self.assert_no_unsafe_actions(trace)

    def test_non_commit_object_is_not_fetched(self):
        result, trace = self.run_prepare("fast_forward", object_type="blob")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unexpected pinned object record", result.stderr)
        self.assert_no_unsafe_actions(trace)

    def test_valid_descendant_is_preserved_without_fetch(self):
        result, trace = self.run_prepare("descendant", access="offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("preserving newer", result.stderr)
        self.assert_no_unsafe_actions(trace)
        self.assertEqual(self.head.read_text(encoding="utf-8").strip(), CURRENT)

    def test_valid_fast_forward_preserves_update_contract(self):
        result, trace = self.run_prepare("fast_forward", access="offline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("submodule update --init --no-fetch", trace)
        self.assertNotIn(" fetch ", trace)
        self.assertEqual(self.head.read_text(encoding="utf-8").strip(), PIN)

    def test_divergent_history_cannot_checkout(self):
        result, trace = self.run_prepare("divergent", access="offline")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("divergent or history is incomplete", result.stderr)
        self.assert_no_unsafe_actions(trace)

    def test_failed_ancestry_after_deepen_stops_repeated_fetches(self):
        result, trace = self.run_prepare("fatal_after_fetch")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Git ancestry probe failed", result.stderr)
        self.assertEqual(trace.count(" fetch "), 1)
        self.assertNotIn("submodule update", trace)


class RealGitPinTests(unittest.TestCase):
    def test_missing_pin_is_not_a_fatal_git_query(self):
        with tempfile.TemporaryDirectory(prefix="whp-real-pin-") as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            missing = "a" * 40
            result = subprocess.run(
                ["/bin/sh", "-c",
                 '. "$1"; whp_git_pin_presence git "$2" "$3"',
                 "pin-test", str(HELPER), str(repo), missing],
                text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), "missing")
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test",
                            "-c", "user.email=test@example.invalid", "commit",
                            "-qm", "fixture", "--allow-empty"], check=True)
            commit = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            result = subprocess.run(
                ["/bin/sh", "-c",
                 '. "$1"; whp_git_pin_presence git "$2" "$3"',
                 "pin-test", str(HELPER), str(repo), commit],
                text=True, capture_output=True, check=True)
            self.assertEqual(result.stdout.strip(), "present")


if __name__ == "__main__":
    unittest.main()
