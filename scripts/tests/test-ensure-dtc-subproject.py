#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression tests for pre-Meson DTC wrap reconciliation."""

import hashlib
from io import StringIO
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
            "project('dtc', 'c', version: '1.6.0')\nsubdir('libfdt')\n",
            encoding="utf-8"
        )
        (self.repo / "libfdt").mkdir()
        (self.repo / "libfdt" / "meson.build").write_text(
            "libfdt_dep = declare_dependency()\n", encoding="utf-8"
        )
        cmd("git", "add", "meson_options.txt", "meson.build", "libfdt/meson.build",
            cwd=self.repo)
        cmd("git", "commit", "-qm", "old DTC", cwd=self.repo)
        self.old = cmd("git", "rev-parse", "HEAD", cwd=self.repo)
        options.write_text(
            "option('tools', type: 'boolean', value: true)\n"
            "option('yaml', type: 'feature', value: 'auto')\n"
            "option('python', type: 'feature', value: 'auto')\n"
            "option('tests', type: 'boolean', value: true)\n",
            encoding="utf-8"
        )
        (self.repo / "VERSION.txt").write_text("1.8.1\n", encoding="utf-8")
        (self.repo / "meson.build").write_text(
            "project('dtc', 'c', version: files('VERSION.txt'))\n"
            "subdir('libfdt')\n", encoding="utf-8"
        )
        cmd("git", "add", "meson_options.txt", "meson.build",
            "VERSION.txt", cwd=self.repo)
        cmd("git", "commit", "-qm", "current DTC", cwd=self.repo)
        self.pin = cmd("git", "rev-parse", "HEAD", cwd=self.repo)
        self.initial_branch = cmd("git", "symbolic-ref", "--short", "HEAD", cwd=self.repo)
        self.remote = self.root / "fork.git"
        cmd("git", "clone", "--bare", str(self.repo), str(self.remote))
        self.target_url = self.remote.as_uri()
        self.legacy_url = (self.root / "legacy.git").as_uri()
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
        self.assertEqual(self.git("remote", "get-url", "origin"), self.legacy_url)
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
        self.assertIn("cat-file -e", trace.read_text())
        self.assertIn("checkout --detach", trace.read_text())
        self.assertNotIn("fetch --depth=1", trace.read_text())

    def test_git_promotion_is_honored_for_fresh_prefetch(self):
        self.repo.rename(self.subprojects / "old-dtc")
        env, trace = self.tracked_git()
        with mock.patch.dict(os.environ, env):
            self.assertTrue(dtc.ensure_dtc(self.root, fetch_missing=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertIn("init -q", trace.read_text())
        self.assertIn("fetch --depth=1", trace.read_text())

    def test_diagnostic_exposes_git_boundary_without_changes(self):
        buffer = StringIO()
        dtc.diagnose_dtc(self.root, stream=buffer)
        out = buffer.getvalue()
        self.assertIn("phase=pre-Meson", out)
        self.assertIn("Git command:", out)
        self.assertIn("Wrap revision: " + self.pin, out)
        self.assertIn("Minimum DTC version: 1.8.1", out)
        self.assertIn("HEAD: " + self.old, out)
        self.assertIn("Git revision vs wrap: different", out)
        self.assertIn("HEAD tree SHA: " + self.git("rev-parse", "HEAD^{tree}"), out)
        self.assertIn("Pinned tree SHA: " + self.git("rev-parse", self.pin + "^{tree}"), out)
        self.assertIn("DTC Meson interface: incompatible or unreadable", out)
        self.assertIn("Meson 'yaml' option", out)
        self.assertIn("Meson wrap marker: stale", out)
        self.assertIn("Expected wrap SHA256 (Meson text): " +
                      hashlib.sha256(self.wrap.read_text().encode()).hexdigest(), out)
        self.assertIn("Stored wrap SHA256: old-wrap-hash", out)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)
        self.assertEqual(self.cache.read_text().strip(), "old-wrap-hash")

    def test_matching_marker_does_not_mask_modified_dtc_source(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / "libfdt" / "meson.build").write_text(
            "libfdt_dep = declare_dependency()\n# modified library build\n",
            encoding="utf-8"
        )
        marker_before = self.cache.read_bytes()
        head_before = self.git("rev-parse", "HEAD")
        with self.assertRaisesRegex(dtc.DTCError, "local changes"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("rev-parse", "HEAD"), head_before)
        self.assertEqual(self.cache.read_bytes(), marker_before)
        out = StringIO()
        dtc.diagnose_dtc(self.root, stream=out)
        self.assertIn("Git revision vs wrap: pinned", out.getvalue())
        self.assertIn("Local changes: 1", out.getvalue())
        self.assertIn("Changed source:  M libfdt/meson.build", out.getvalue())
        self.assertIn("Meson wrap marker: current", out.getvalue())

    def test_porcelain_status_preserves_leading_xy_columns(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / "libfdt" / "meson.build").write_text(
            "libfdt_dep = declare_dependency()\n# dirty file\n", encoding="utf-8"
        )
        actual = dtc.git(self.repo, "status", "--porcelain", "--untracked-files=all")
        self.assertTrue(actual.startswith(" M libfdt/meson.build"), repr(actual))
        out = StringIO()
        dtc.diagnose_dtc(self.root, stream=out)
        self.assertIn("Changed source:  M libfdt/meson.build", out.getvalue())

    def test_matching_marker_ignores_generated_dtc_build_files(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / ".git" / "info" / "exclude").write_text("build/\n")
        build = self.repo / "build"
        build.mkdir()
        (build / "libfdt.o").write_text("generated\n")
        self.assertFalse(dtc.ensure_dtc(self.root))
        out = StringIO()
        dtc.diagnose_dtc(self.root, stream=out)
        self.assertIn("Git revision vs wrap: pinned", out.getvalue())
        self.assertIn("Local changes: 0", out.getvalue())
        self.assertIn("Meson wrap marker: current", out.getvalue())
        self.assertEqual((build / "libfdt.o").read_text(), "generated\n")

    def test_diagnostic_reports_dtc_version_independent_of_wrap_hash(self):
        (self.repo / "VERSION.txt").write_text("1.8.1\n")
        out = StringIO()
        dtc.diagnose_dtc(self.root, stream=out)
        self.assertIn("DTC VERSION.txt: 1.8.1", out.getvalue())
        self.assertIn("Meson wrap marker: stale", out.getvalue())
        self.assertIn("Git revision vs wrap: different", out.getvalue())

    def test_crlf_wrap_marker_matches_mesons_text_hash(self):
        # Meson reads the wrap as UTF-8 text and normalizes CRLF, whereas
        # hashing raw bytes would incorrectly claim its own marker is stale.
        raw = self.wrap.read_bytes().replace(b"\n", b"\r\n")
        self.wrap.write_bytes(raw)
        expected = hashlib.sha256(self.wrap.read_text(encoding="utf-8").encode()).hexdigest()
        self.assertNotEqual(hashlib.sha256(raw).hexdigest(), expected)
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(expected + "\n")
        out = StringIO()
        dtc.diagnose_dtc(self.root, stream=out)
        self.assertIn("Meson wrap marker: current", out.getvalue())
        self.assertIn("Wrap line endings: text-normalized hash differs", out.getvalue())
        self.assertFalse(dtc.ensure_dtc(self.root))
        self.assertEqual(self.cache.read_text().strip(), expected)

    def test_crlf_stale_marker_repairs_without_git_update(self):
        raw = self.wrap.read_bytes().replace(b"\n", b"\r\n")
        self.wrap.write_bytes(raw)
        self.git("checkout", "--detach", self.pin)
        self.assertTrue(dtc.ensure_dtc(self.root))
        expected = hashlib.sha256(self.wrap.read_text(encoding="utf-8").encode()).hexdigest()
        self.assertEqual(self.cache.read_text().strip(), expected)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.git("remote", "get-url", "origin"), self.legacy_url)
        out = StringIO()
        dtc.diagnose_dtc(self.root, stream=out)
        self.assertIn("Meson wrap marker: current", out.getvalue())

    def test_diagnostic_handles_missing_checkout_without_git_fetch(self):
        self.repo.rename(self.subprojects / "old-dtc")
        buffer = StringIO()
        dtc.diagnose_dtc(self.root, stream=buffer)
        self.assertIn("Checkout: missing", buffer.getvalue())
        self.assertFalse(self.repo.exists())

    def test_diagnostic_handles_broken_git_selection(self):
        buffer = StringIO()
        with mock.patch.dict(os.environ, {"GIT": "does-not-exist-git"}):
            dtc.diagnose_dtc(self.root, stream=buffer)
        self.assertIn("HEAD: unavailable", buffer.getvalue())
        self.assertIn("Wrap revision: " + self.pin, buffer.getvalue())

    def test_legacy_1_6_0_is_rejected_even_with_current_options(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / "VERSION.txt").write_text("1.6.0\n", encoding="utf-8")
        with self.assertRaisesRegex(dtc.DTCError, r"DTC 1\.6\.0 is older than QEMU's required DTC 1\.8\.1"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)

    def test_later_1_9_0_dtc_version_can_be_pinned(self):
        self.git("checkout", "--detach", self.pin)
        (self.repo / "VERSION.txt").write_text("1.9.0\n", encoding="utf-8")
        self.git("add", "VERSION.txt")
        self.git("commit", "-qm", "future DTC release 1.9.0")
        next_pin = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.pin)
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\nrevision = {next_pin}\ndepth = 1\n"
        )
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), next_pin)
        self.assertEqual(self.cache.read_text().strip(), dtc.meson_wrap_hash(self.wrap))

    def test_future_legacy_version_preflight_preserves_head_and_marker(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        saved_marker = self.cache.read_bytes()
        (self.repo / "VERSION.txt").write_text("1.6.0\n", encoding="utf-8")
        self.git("add", "VERSION.txt")
        self.git("commit", "-qm", "incompatible old version in new candidate")
        incompatible = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.pin)
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\nrevision = {incompatible}\ndepth = 1\n"
        )
        with self.assertRaisesRegex(dtc.DTCError, r"older than QEMU's required DTC 1\.8\.1"):
            dtc.ensure_dtc(self.root, no_download=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.cache.read_bytes(), saved_marker)

    def test_unverifiable_version_fails_closed(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / "VERSION.txt").write_text("unknown\n", encoding="utf-8")
        with self.assertRaisesRegex(dtc.DTCError, "unrecognized DTC Meson version"):
            dtc.ensure_dtc(self.root)

    def test_expected_hash_is_live_for_metadata_only_wrap_changes(self):
        self.git("checkout", "--detach", self.pin)
        before = dtc.meson_wrap_hash(self.wrap)
        self.cache.write_text(before + "\n", encoding="utf-8")
        original = self.wrap.read_text(encoding="utf-8")
        self.wrap.write_text(original.replace("depth = 1", "depth = 2"),
                             encoding="utf-8")
        after = dtc.meson_wrap_hash(self.wrap)
        self.assertNotEqual(after, before)
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.cache.read_text().strip(), after)
        self.assertFalse(dtc.ensure_dtc(self.root, no_download=True))

    def test_missing_marker_is_recreated_from_current_wrap(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.unlink()
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.cache.read_text(encoding="utf-8").strip(),
                         dtc.meson_wrap_hash(self.wrap))
        self.assertFalse(dtc.ensure_dtc(self.root, no_download=True))

    def test_refuses_to_install_checksum_from_previous_wrap_snapshot(self):
        original = dtc.meson_wrap_hash(self.wrap)
        self.wrap.write_text(self.wrap.read_text().replace("depth = 1",
                                                          "depth = 2"))
        before = self.cache.read_bytes()
        with self.assertRaisesRegex(dtc.DTCError, "wrap changed during reconciliation"):
            dtc.refresh_wrap_cache(self.cache, original, self.wrap)
        self.assertEqual(self.cache.read_bytes(), before)
        self.assertNotEqual(dtc.meson_wrap_hash(self.wrap), original)

    def test_live_hash_uses_mesons_utf8_text_normalization(self):
        text = self.wrap.read_text(encoding="utf-8")
        self.wrap.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(dtc.meson_wrap_hash(self.wrap, text),
                         dtc.meson_wrap_hash(self.wrap))
        self.assertNotEqual(hashlib.sha256(self.wrap.read_bytes()).hexdigest(),
                            dtc.meson_wrap_hash(self.wrap))

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
            "project('dtc', 'c', version: files('VERSION.txt'))\n"
            "subdir('libfdt')\n# user edit\n",
            encoding="utf-8"
        )
        with self.assertRaisesRegex(dtc.DTCError, "local changes"):
            dtc.ensure_dtc(self.root)
        self.assertEqual(self.git("symbolic-ref", "--short", "HEAD"), self.initial_branch)
        self.assertEqual(self.cache.read_text().strip(), "old-wrap-hash")

    def test_custom_origin_kept_while_fetching_exact_wrap_revision(self):
        self.git("remote", "set-url", "origin", "https://example.com/custom.git")
        self.assertTrue(dtc.ensure_dtc(self.root))
        self.assertEqual(self.git("remote", "get-url", "origin"),
                         "https://example.com/custom.git")
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)

    def test_missing_origin_does_not_block_pinned_wrap_fetch(self):
        self.git("remote", "remove", "origin")
        self.assertTrue(dtc.ensure_dtc(self.root))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertFalse(self.git("remote"))

    def test_offline_reuses_present_pinned_commit_with_old_wrap_marker(self):
        # This checkout and its ignored build artifacts are independent of
        # the parent QEMU Git source updater and require no stash.
        (self.repo / ".git" / "info" / "exclude").write_text(
            "build/\n", encoding="utf-8"
        )
        build = self.repo / "build"
        build.mkdir()
        (build / "libfdt.o").write_text("ignored generated artifact\n")
        before = self.git("remote", "get-url", "origin")
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.git("remote", "get-url", "origin"), before)
        self.assertEqual((build / "libfdt.o").read_text(), "ignored generated artifact\n")
        self.assertEqual(self.cache.read_text().strip(),
                         dtc.meson_wrap_hash(self.wrap))

    def test_offline_rejects_missing_pinned_commit(self):
        missing = "f" * 40
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\n"
            f"revision = {missing}\ndepth = 1\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(dtc.DTCError, "not available locally"):
            dtc.ensure_dtc(self.root, no_download=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)
        self.assertEqual(self.cache.read_text().strip(), "old-wrap-hash")

    def test_offline_can_refresh_cache_of_pinned_revision(self):
        self.git("checkout", "--detach", self.pin)
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))

    def test_git_fetch_failure_preserves_original_url(self):
        unavailable = (self.root / "missing-fork.git").as_uri()
        missing = "f" * 40
        self.wrap.write_text(
            f"[wrap-git]\nurl = {unavailable}\nrevision = {missing}\ndepth = 1\n"
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
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap))
        (self.repo / "meson_options.txt").write_text(
            "option('tools', type: 'boolean', value: true)\n"
            "option('yaml', type: 'feature', value: 'auto')\n"
            "option('python', type: 'feature', value: 'auto')\n"
        )
        with self.assertRaisesRegex(dtc.DTCError, "Meson 'tests' option"):
            dtc.ensure_dtc(self.root)

    def test_matching_pin_with_missing_libfdt_project_is_rejected(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(hashlib.sha256(self.wrap.read_bytes()).hexdigest())
        (self.repo / "libfdt" / "meson.build").unlink()
        with self.assertRaisesRegex(dtc.DTCError, "Meson libfdt project"):
            dtc.ensure_dtc(self.root)

    def test_new_dtc_pin_upgrades_offline_without_build_reset(self):
        build = self.root / "build" / "meson-private"
        build.mkdir(parents=True)
        (build / "coredata.dat").write_text("incremental-build-data")
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / "libfdt" / "meson.build").write_text(
            "libfdt_dep = declare_dependency()\n# upgraded DTC\n", encoding="utf-8"
        )
        self.git("add", "libfdt/meson.build")
        self.git("commit", "-qm", "new compatible DTC release")
        next_pin = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.pin)
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\nrevision = {next_pin}\ndepth = 1\n"
        )
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), next_pin)
        self.assertEqual(self.cache.read_text().strip(), dtc.meson_wrap_hash(self.wrap))
        self.assertEqual((build / "coredata.dat").read_text(), "incremental-build-data")

    def test_future_incompatible_dtc_pin_cannot_change_checkout(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        old_cache = self.cache.read_bytes()
        (self.repo / "meson_options.txt").write_text(
            "option('tools', type: 'boolean', value: true)\n",
            encoding="utf-8"
        )
        self.git("add", "meson_options.txt")
        self.git("commit", "-qm", "incompatible DTC release")
        incompatible = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.pin)
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\nrevision = {incompatible}\ndepth = 1\n"
        )
        with self.assertRaisesRegex(dtc.DTCError, "Meson 'yaml' option"):
            dtc.ensure_dtc(self.root, no_download=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.cache.read_bytes(), old_cache)

    def test_upgrade_accepts_new_meson_options_filename(self):
        self.git("checkout", "--detach", self.pin)
        self.git("mv", "meson_options.txt", "meson.options")
        self.git("commit", "-qm", "move Meson options file")
        next_pin = self.git("rev-parse", "HEAD")
        self.git("checkout", "--detach", self.pin)
        self.wrap.write_text(
            f"[wrap-git]\nurl = {self.target_url}\nrevision = {next_pin}\ndepth = 1\n"
        )
        self.assertTrue(dtc.ensure_dtc(self.root, no_download=True))
        self.assertEqual(self.git("rev-parse", "HEAD"), next_pin)
        self.assertTrue((self.repo / "meson.options").is_file())
        self.assertEqual(self.cache.read_text().strip(), dtc.meson_wrap_hash(self.wrap))

    def test_pinned_source_missing_libfdt_dep_is_rejected(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(dtc.meson_wrap_hash(self.wrap) + "\n")
        (self.repo / "libfdt" / "meson.build").write_text(
            "# removed dependency variable\n", encoding="utf-8"
        )
        with self.assertRaisesRegex(dtc.DTCError, "no longer exports"):
            dtc.ensure_dtc(self.root)

    def test_missing_checkout_is_normal_meson_case(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.assertFalse(dtc.ensure_dtc(self.root))


if __name__ == "__main__":
    unittest.main()
