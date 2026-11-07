#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression tests for the pinned-Gitlink automatic submodule updater."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


UPDATER = Path(__file__).resolve().parents[1] / "git-submodule.sh"


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


class GitSubmoduleTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.source = root / "source"
        self.source.mkdir()
        git("init", "-q", cwd=self.source)
        git("config", "user.email", "test@example.org", cwd=self.source)
        git("config", "user.name", "Test", cwd=self.source)
        for name in ("a", "b"):
            dependency = root / name
            dependency.mkdir()
            git("init", "-q", cwd=dependency)
            git("config", "user.email", "test@example.org", cwd=dependency)
            git("config", "user.name", "Test", cwd=dependency)
            (dependency / "README").write_text(name + "\n", encoding="utf-8")
            git("add", "README", cwd=dependency)
            git("commit", "-qm", f"add {name}", cwd=dependency)
            git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
                str(dependency), f"modules/{name}", cwd=self.source)
        git("commit", "-qam", "record pinned gitlinks", cwd=self.source)
        self.clone = root / "clone"
        git("clone", "-q", str(self.source), str(self.clone))
        (self.clone / "scripts").mkdir()
        shutil.copy2(UPDATER, self.clone / "scripts" / "git-submodule.sh")
        shared = self.clone / "scripts" / "whp-build"
        shared.mkdir()
        shutil.copy2(UPDATER.parent / "whp-build" / "shell-functions.sh",
                     shared / "shell-functions.sh")

    def updater(self, action, *modules):
        env = os.environ.copy()
        env["GIT_ALLOW_PROTOCOL"] = "file"
        return subprocess.run(
            ["sh", "scripts/git-submodule.sh", action, *modules],
            cwd=self.clone, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def test_updates_only_selected_gitlinks_and_tracks_them(self):
        result = self.updater("update", "modules/a")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = self.clone / ".git-submodule-status"
        self.assertEqual(len(record.read_text().splitlines()), 1)
        self.assertIn("modules/a", record.read_text())
        self.assertNotIn("modules/b", record.read_text())
        self.assertFalse(git("submodule", "status", "modules/a", cwd=self.clone).startswith("-"))
        self.assertTrue(git("submodule", "status", "modules/b", cwd=self.clone).startswith("-"))
        self.assertEqual(self.updater("validate", "modules/a").returncode, 0)

        result = self.updater("update", "modules/b")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(record.read_text().splitlines()), 2)
        validated = self.updater("validate", "modules/a", "modules/b")
        self.assertEqual(validated.returncode, 0,
                         validated.stdout + validated.stderr + record.read_text())
        result = self.updater("update", "modules/a")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(record.read_text().splitlines()), 2)
        self.assertEqual(self.updater("validate", "modules/b").returncode, 0)

    def test_mesons_dtc_is_not_a_git_submodule(self):
        dtc = self.clone / "subprojects" / "dtc"
        dtc.mkdir(parents=True)
        marker = dtc / "user-source"
        marker.write_text("preserve DTC checkout\n", encoding="utf-8")

        # A mistaken mixed invocation must fail before updating modules/a.
        result = self.updater("update", "modules/a", "subprojects/dtc")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Meson-owned", result.stderr)
        self.assertEqual(marker.read_text(), "preserve DTC checkout\n")
        self.assertFalse((self.clone / ".git-submodule-status").exists())
        self.assertTrue(git("submodule", "status", "modules/a",
                            cwd=self.clone).startswith("-"))

    def test_accepts_remote_descendant_without_rewinding_or_repinning(self):
        result = self.updater("update", "modules/a")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checkout = self.clone / "modules/a"
        remote = self.source.parent / "a"
        old_pin = git("rev-parse", "HEAD:modules/a", cwd=self.clone)

        # Simulate 'git submodule update --remote': the child remote advances
        # while the parent's recorded gitlink intentionally remains at v1.
        (remote / "README").write_text("remote v2\n", encoding="utf-8")
        git("add", "README", cwd=remote)
        git("commit", "-qm", "remote child v2", cwd=remote)
        newer = git("rev-parse", "HEAD", cwd=remote)
        git("fetch", "origin", cwd=checkout)
        git("checkout", "--detach", newer, cwd=checkout)

        # A stale status ledger is not permission to reject or rewind v2.
        validated = self.updater("validate", "modules/a")
        self.assertEqual(validated.returncode, 0,
                         validated.stdout + validated.stderr)
        result = self.updater("update", "modules/a")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(git("rev-parse", "HEAD", cwd=checkout), newer)
        self.assertEqual(git("rev-parse", "HEAD:modules/a", cwd=self.clone), old_pin)
        self.assertIn(newer, (self.clone / ".git-submodule-status").read_text())
        self.assertEqual(self.updater("validate", "modules/a").returncode, 0)
        self.assertTrue(git("submodule", "status", "modules/b",
                            cwd=self.clone).startswith("-"))

    def test_rejects_divergent_checkout_without_changing_it(self):
        result = self.updater("update", "modules/a")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checkout = self.clone / "modules/a"
        git("config", "user.email", "test@example.org", cwd=checkout)
        git("config", "user.name", "Test", cwd=checkout)
        # A root commit with identical tree content is nevertheless unrelated
        # to the QEMU gitlink, so neither update nor validate may accept it.
        unrelated = git("commit-tree", "HEAD^{tree}", "-m", "unrelated root",
                        cwd=checkout)
        git("checkout", "--detach", unrelated, cwd=checkout)
        self.assertNotEqual(self.updater("validate", "modules/a").returncode, 0)
        self.assertNotEqual(self.updater("update", "modules/a").returncode, 0)
        self.assertEqual(git("rev-parse", "HEAD", cwd=checkout), unrelated)


if __name__ == "__main__":
    unittest.main()
