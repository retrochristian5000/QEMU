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

    def test_detects_changed_submodule_checkout(self):
        result = self.updater("update", "modules/a")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        checkout = self.clone / "modules/a"
        git("config", "user.email", "test@example.org", cwd=checkout)
        git("config", "user.name", "Test", cwd=checkout)
        (checkout / "README").write_text("locally advanced\n", encoding="utf-8")
        git("add", "README", cwd=checkout)
        git("commit", "-qm", "advance local module", cwd=checkout)
        self.assertNotEqual(self.updater("validate", "modules/a").returncode, 0)


if __name__ == "__main__":
    unittest.main()
