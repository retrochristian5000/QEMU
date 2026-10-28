#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression tests for pre-Meson DTC wrap reconciliation."""

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


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
        cmd("git", "add", "meson_options.txt", cwd=self.repo)
        cmd("git", "commit", "-qm", "old DTC", cwd=self.repo)
        self.old = cmd("git", "rev-parse", "HEAD", cwd=self.repo)
        options.write_text("option('tests', type: 'boolean', value: true)\n", encoding="utf-8")
        cmd("git", "add", "meson_options.txt", cwd=self.repo)
        cmd("git", "commit", "-qm", "current DTC", cwd=self.repo)
        self.pin = cmd("git", "rev-parse", "HEAD", cwd=self.repo)
        cmd("git", "checkout", "--detach", self.old, cwd=self.repo)
        cmd("git", "remote", "add", "origin", "https://gitlab.com/qemu-project/dtc.git", cwd=self.repo)
        self.wrap = self.subprojects / "dtc.wrap"
        self.wrap.write_text(
            "[wrap-git]\nurl = https://github.com/retrochristian5000/dtc.git\n"
            f"revision = {self.pin}\ndepth = 1\n", encoding="utf-8"
        )
        self.cache = self.repo / ".meson-subproject-wrap-hash.txt"
        self.cache.write_text("old-wrap-hash\n", encoding="utf-8")
        self.meson = self.root / "fake-meson"
        self.meson.write_text("""#!/usr/bin/env python3
import hashlib
from pathlib import Path
import subprocess
import sys
if len(sys.argv) != 6 or sys.argv[1:4] != ['subprojects', 'update', '--sourcedir'] or sys.argv[5] != 'dtc':
    sys.exit(12)
source = Path(sys.argv[4])
wrap = source / 'subprojects/dtc.wrap'
pin = next(line.split('=', 1)[1].strip() for line in wrap.read_text().splitlines() if line.startswith('revision'))
repo = source / 'subprojects/dtc'
if subprocess.run(['git', '-C', str(repo), 'remote', 'get-url', 'origin'], capture_output=True, text=True).stdout.strip() != 'https://github.com/retrochristian5000/dtc.git':
    sys.exit(13)
subprocess.run(['git', '-C', str(repo), 'checkout', '--detach', pin], check=True, stdout=subprocess.DEVNULL)
(repo / '.meson-subproject-wrap-hash.txt').write_text(hashlib.sha256(wrap.read_text().encode()).hexdigest() + '\\n')
""", encoding="utf-8")
        self.meson.chmod(0o755)

    def git(self, *args):
        return cmd("git", *args, cwd=self.repo)

    def test_reconciles_old_checkout_without_resetting_build(self):
        build = self.root / "build" / "meson-private"
        build.mkdir(parents=True)
        (build / "coredata.dat").write_text("untouched")
        self.assertTrue(dtc.ensure_dtc(self.root, self.meson))
        self.assertEqual(self.git("rev-parse", "HEAD"), self.pin)
        self.assertEqual(self.git("remote", "get-url", "origin"),
                         "https://github.com/retrochristian5000/dtc.git")
        self.assertIn("option('tests'", (self.repo / "meson_options.txt").read_text())
        self.assertEqual(self.cache.read_text().strip(),
                         hashlib.sha256(self.wrap.read_text().encode()).hexdigest())
        self.assertEqual((build / "coredata.dat").read_text(), "untouched")

    def test_matching_checkout_is_noop(self):
        self.git("checkout", "--detach", self.pin)
        self.cache.write_text(hashlib.sha256(self.wrap.read_text().encode()).hexdigest())
        self.assertFalse(dtc.ensure_dtc(self.root, self.root / "no-meson"))

    def test_dirty_checkout_is_preserved(self):
        (self.repo / "meson_options.txt").write_text("local changes\n")
        with self.assertRaisesRegex(dtc.DTCError, "local changes"):
            dtc.ensure_dtc(self.root, self.meson)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.old)
        self.assertEqual(self.git("remote", "get-url", "origin"),
                         "https://gitlab.com/qemu-project/dtc.git")

    def test_attached_branch_is_preserved(self):
        self.git("checkout", "-q", "master")
        with self.assertRaisesRegex(dtc.DTCError, "development branch"):
            dtc.ensure_dtc(self.root, self.meson)

    def test_unknown_origin_is_preserved(self):
        self.git("remote", "set-url", "origin", "https://example.com/custom.git")
        with self.assertRaisesRegex(dtc.DTCError, "origin differs"):
            dtc.ensure_dtc(self.root, self.meson)

    def test_offline_rejects_old_revision(self):
        with self.assertRaisesRegex(dtc.DTCError, "downloads are disabled"):
            dtc.ensure_dtc(self.root, self.meson, no_download=True)

    def test_offline_can_refresh_cache_of_pinned_revision(self):
        self.git("checkout", "--detach", self.pin)
        self.assertTrue(dtc.ensure_dtc(self.root, self.meson, no_download=True))

    def test_meson_failure_restores_original_url(self):
        failing = self.root / "fail-meson"
        failing.write_text("#!/bin/sh\nexit 23\n")
        failing.chmod(0o755)
        with self.assertRaisesRegex(dtc.DTCError, "Meson DTC subproject update failed"):
            dtc.ensure_dtc(self.root, failing)
        self.assertEqual(self.git("remote", "get-url", "origin"),
                         "https://gitlab.com/qemu-project/dtc.git")

    def test_non_repository_is_preserved(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.repo.mkdir()
        with self.assertRaisesRegex(dtc.DTCError, "not a standalone Git checkout"):
            dtc.ensure_dtc(self.root, self.meson)

    def test_release_archive_vendored_source_is_not_changed(self):
        (self.root / ".git").rmdir()
        self.repo.rename(self.subprojects / "old-dtc")
        self.repo.mkdir()
        (self.repo / "meson_options.txt").write_text("vendored")
        self.assertFalse(dtc.ensure_dtc(self.root, self.root / "no-meson"))
        self.assertEqual((self.repo / "meson_options.txt").read_text(), "vendored")

    def test_missing_checkout_is_normal_meson_case(self):
        self.repo.rename(self.subprojects / "old-dtc")
        self.assertFalse(dtc.ensure_dtc(self.root, self.root / "no-meson"))


if __name__ == "__main__":
    unittest.main()
