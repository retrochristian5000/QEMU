#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression tests for pre-Meson DTC wrap reconciliation."""

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


HELPER = Path(__file__).resolve().parents[1] / "ensure-dtc-subproject.py"
spec = importlib.util.spec_from_file_location("ensure_dtc", HELPER)
dtc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dtc)


def cmd(*argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.strip()


class EnsureDTCTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".git").mkdir()  # Mark the fixture as a source Git checkout.
        self.subprojects = self.root / "subprojects"
        self.subprojects.mkdir()
        self.repo = self.subprojects / "dtc"
        self.repo.mkdir()
        cmd("git", "init", "-q", str(self.repo))
        cmd("git", "config", "user.name", "Test", cwd=self.repo)
        cmd("git", "config", "user.email", "test@example.org", cwd=self.repo)
        options = self.repo / "meson_options.txt"
        options.write_text("option('tools', type: 'boolean', value: true)\n", encoding="utf-8")
        (self.repo / "meson.build").write_text(
            "project('dtc', 'c')\nsubdir('libfdt')\n", encoding="utf-8"
        )
        (self.repo / "libfdt").mkdir()
        (self.repo / "libfdt" / "meson.build").write_text(
            "# fixture libfdt\n", encoding="utf-8"
        )
        cmd("git", "add", "meson_options.txt", "meson.build", "libfdt/meson.build",
            cwd=self.repo)
        cmd("git", "commit", "-qm", "old DTC", cwd=self.repo)
        self.old = cmd("git", "rev-parse", "HEAD", cwd=self.repo)
        options.write_text("option('tests', type: 'boolean', value: true)\n", encoding="utf-8")
        cmd("git", "add", "meson_options.txt", cwd=self.repo)
        cmd("git", "commit", "-qm", "current DTC", cwd=self.repo)
        self.pin = cmd("git", "rev-parse", "HEAD", cwd=self.repo)
        self.initial_branch = cmd("git", "symbolic-ref", "--short", "HEAD", cwd=self.repo)
        self.remote = self.root / "fork.git"
        cmd("git", "clone", "--bare", str(self.repo), str(self.remote))
        self.target_url = self.remote.as_uri()
        self.legacy_url = (self.root / "legacy.git").as_uri()
        dtc.OLD_DTC_URLS.add(self.legacy_url)
        self.addCleanup(dtc.OLD_DTC_URLS.discard, self.legacy_url)
        cmd("git", "checkout", "--detach", self.old, cwd=self.repo)
        cmd("git", "remote", "add", "origin", self.legacy_url, cwd=self.repo)
        self.wrap = self.subprojects / "dtc.wrap"
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\n"
            f"revision = {self.pin}\ndepth = 1\n", encoding="utf-8"
        )
        self.cache = self.repo / ".meson-subproject-wrap-hash.txt"
        self.cache.write_text("old-wrap-hash\n", encoding="utf-8")

    def git(self, *args):
        return cmd("git", *args, cwd=self.repo)

    def test_reconciles_old_checkout_without_resetting_build(self):
        build = self.root / "build" / "meson-private"
        build.mkdir(parents=True)
        (build / "coredata.dat").write_text("untouched")
        self.assertTrue(dtc.ensure_dtc(self.root))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.git("remote", "get-url", "origin"), self.target_url)
        self.assertIn("option('tests'", (self.repo / "meson_options.txt").read_text())
        self.assertEqual(self.cache.read_text().strip(),
                         hashlib.sha256(self.wrap.read_text().encode()).hexdigest())
        self.assertEqual((build / "coredata.dat").read_text(), "untouched")

    def tracked_git(self):
        trace = self.root / "git-selection.log"
        wrapper = self.root / "selected-git"
        wrapper.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$WHP_DTC_GIT_TRACE"\n'
            'exec "$WHP_DTC_TEST_GIT" "$@"\n', encoding="utf-8"
        )
        wrapper.chmod(0o755)
        return {
            "GIT": str(wrapper),
            "WHP_DTC_GIT_TRACE": str(trace),
            "WHP_DTC_TEST_GIT": shutil.which("git"),
        }, trace

    def test_git_promotion_is_honored_for_revision_reconciliation(self):
        env, trace = self.tracked_git()
        with mock.patch.dict(os.environ, env):
            self.assertTrue(dtc.ensure_dtc(self.root))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertIn("fetch --depth=1", trace.read_text())

    def test_git_promotion_is_honored_for_fresh_prefetch(self):
        self.repo.rename(self.subprojects / "old-dtc")
        env, trace = self.tracked_git()
        with mock.patch.dict(os.environ, env):
            self.assertTrue(dtc.ensure_dtc(self.root, fetch_missing=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertIn("init -q", trace.read_text())
        self.assertIn("fetch --depth=1", trace.read_text())

    def test_matching_checkout_is_noop(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(hashlib.sha256(self.wrap.read_text().encode()).hexdigest())
        self.assertFalse(dtc.ensure_dtc(self.root))

    def test_dirty_checkout_is_preserved(self):
        (self.repo / "meson_options.txt").write_text("local changes\n")
        with self.assertRaisesRegex(dtc.DTCError, "local changes"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)
        self.assertEqual(self.git("remote", "get-url", "origin"), self.legacy_url)

    def test_attached_stale_branch_is_preserved(self):
        self.git("checkout", "-q", "-b", "stale-fixture", self.old)
        with self.assertRaisesRegex(dtc.DTCError, "development branch"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), "stale-fixture")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)

    def test_attached_pinned_branch_refreshes_only_wrap_marker(self):
        self.git("checkout", "-q", self.initial_branch)
        old_origin = self.git("remote", "get-url", "origin")
        self.assertTrue(dtc.ensure_dtc(self.root))
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), self.initial_branch)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.git("remote", "get-url", "origin"), old_origin)
        self.assertEqual(self.cache.read_text().strip(),
                         hashlib.sha256(self.wrap.read_bytes()).hexdigest())
        self.assertFalse(dtc.ensure_dtc(self.root))

    def test_offline_pinned_branch_refreshes_wrap_marker(self):
        self.git("checkout", "-q", self.initial_branch)
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), self.initial_branch)

    def test_pinned_branch_with_local_edits_is_preserved(self):
        self.git("checkout", "-q", self.initial_branch)
        (self.repo / "meson.build").write_text(
            "project('dtc', 'c')\nsubdir('libfdt')\n# user edit\n",
            encoding="utf-8"
        )
        with self.assertRaisesRegex(dtc.DTCError, "local changes"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), self.initial_branch)
        self.assertEqual(self.cache.read_text().strip(), "old-wrap-hash")

    def test_unknown_origin_is_preserved(self):
        self.git("remote", "set-url", "origin", "https://example.com/custom.git")
        with self.assertRaisesRegex(dtc.DTCError, "origin differs"):
            dtc.ensure_dtc(self.root)

    def test_offline_rejects_old_revision(self):
        with self.assertRaisesRegex(dtc.DTCError, "downloads are disabled"):
            dtc.ensure_dtc(self.root, no_download=True)

    def test_offline_can_refresh_cache_of_pinned_revision(self):
        self.git("checkout", "--detach", self.pin)
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))

    def test_git_fetch_failure_restores_original_url(self):
        unavailable = (self.root / "missing-fork.git").as_uri()
        self.wrap.write_text(
            f"[wrap-git]\nurl = {unavailable}\nrevision = {self.pin}\ndepth = 1\n"
        )
        with self.assertRaisesRegex(dtc.DTCError, "git fetch"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("remote", "get-url", "origin"), self.legacy_url)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)

    def test_non_repository_is_preserved(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.repo.mkdir()
        with self.assertRaisesRegex(dtc.DTCError, "not a standalone Git checkout"):
            dtc.ensure_dtc(self.root)

    def test_release_archive_vendored_source_is_not_changed(self):
        (self.root / ".git").rmdir()
        self.repo.rename(self.subprojects / "old-dtc")
        self.repo.mkdir()
        (self.repo / "meson_options.txt").write_text("vendored")
        self.assertFalse(dtc.ensure_dtc(self.root))
        self.assertEqual((self.repo / "meson_options.txt").read_text(), "vendored")

    def test_missing_checkout_git_prefetch_preserves_meson_layout(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.assertTrue(dtc.ensure_dtc(self.root, fetch_missing=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.git("remote", "get-url", "origin"), self.target_url)
        self.assertIn("option('tests'", (self.repo / "meson_options.txt").read_text())
        self.assertTrue((self.repo / "libfdt" / "meson.build").is_file())
        self.assertEqual(self.cache.read_text().strip(),
                         hashlib.sha256(self.wrap.read_bytes()).hexdigest())
        self.assertFalse(list(self.subprojects.glob(".dtc-fetch-*")))

    def test_git_prefetch_honors_no_download(self):
        self.repo.rename(self.subprojects / "old-dtc")
        with self.assertRaisesRegex(dtc.DTCError, "downloads are disabled"):
            dtc.ensure_dtc(self.root, no_download=True, fetch_missing=True)
        self.assertFalse(self.repo.exists())

    def test_failed_git_prefetch_leaves_no_partial_checkout(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.wrap.write_text(
            "[wrap-git]\nurl = " + (self.root / "missing.git").as_uri()
            + "\nrevision = " + self.pin + "\ndepth = 1\n"
        )
        with self.assertRaisesRegex(dtc.DTCError, "git fetch"):
            dtc.ensure_dtc(self.root, fetch_missing=True)
        self.assertFalse(self.repo.exists())
        self.assertFalse(list(self.subprojects.glob(".dtc-fetch-*")))

    def test_matching_pin_with_missing_tests_option_is_rejected(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(hashlib.sha256(self.wrap.read_bytes()).hexdigest())
        (self.repo / "meson_options.txt").write_text(
            "option('tools', type: 'boolean', value: true)\n"
        )
        with self.assertRaisesRegex(dtc.DTCError, "Meson 'tests' option"):
            dtc.ensure_dtc(self.root)

    def test_matching_pin_with_missing_libfdt_project_is_rejected(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(hashlib.sha256(self.wrap.read_bytes()).hexdigest())
        (self.repo / "libfdt" / "meson.build").unlink()
        with self.assertRaisesRegex(dtc.DTCError, "Meson libfdt project"):
            dtc.ensure_dtc(self.root)

    def test_missing_checkout_is_normal_meson_case(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.assertFalse(dtc.ensure_dtc(self.root))


if __name__ == "__main__":
    unittest.main()
