#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify QEMU's actual entrypoint path logic without invoking bootstrap tools."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def launcher_prefix(name: str) -> str:
    body = (ROOT / name).read_text(encoding="utf-8")
    if name == "build.sh":
        anchor = '. "$SOURCE_DIR/scripts/whp-build/shell-functions.sh"'
        prefix = body.split(anchor, 1)[0]
        output = 'printf "root=%s\\n" "$SOURCE_DIR"\n'
    elif name == "builder.sh":
        anchor = "# Direct calls must enter through the public policy boundary first."
        prefix = body.split(anchor, 1)[0]
        output = 'printf "root=%s\\n" "$script_dir"\n'
    else:
        anchor = "# builder.sh is the normalized stage runner, not a second public entry point."
        prefix = body.split(anchor, 1)[0]
        output = 'printf "root=%s\\n" "$SOURCE_DIR"\n'
    if anchor not in body:
        raise AssertionError(f"{name} source-directory contract not found")
    return prefix + output


class BuildEntryPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-root-paths-")
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.checkout = base / "checkout with spaces"
        self.launcher_dir = base / "external launchers" / "bin"
        self.cwd = base / "unrelated workdir"
        self.checkout.mkdir()
        self.physical_checkout = self.checkout.resolve()
        self.launcher_dir.mkdir(parents=True)
        self.cwd.mkdir()
        (self.checkout / "scripts/whp-build").mkdir(parents=True)
        (self.checkout / "scripts/whp-build/shell-functions.sh").write_text(
            "# smoke-test fixture\n", encoding="utf-8"
        )
        self.links = {}
        for name in ("build.sh", "builder.sh", "builder.bash"):
            target = self.checkout / name
            target.write_text(launcher_prefix(name), encoding="utf-8")
            target.chmod(0o755)
            alias = self.launcher_dir / f"alias-{name}"
            # Relative symlink targets exercise links outside the checkout.
            alias.symlink_to(os.path.relpath(target, alias.parent))
            self.links[name] = (target, alias)

    def run_script(self, command, *, prepend_path=False):
        env = os.environ.copy()
        if prepend_path:
            env["PATH"] = str(self.launcher_dir) + os.pathsep + env.get("PATH", "")
        return subprocess.run(
            command, cwd=self.cwd, env=env, text=True, capture_output=True,
            check=False, timeout=10,
        )

    def test_direct_paths_use_checkout_not_calling_directory(self):
        for name, (script, _) in self.links.items():
            with self.subTest(name=name):
                interpreter = "/bin/bash" if name.endswith(".bash") else "/bin/sh"
                result = self.run_script([interpreter, str(script)])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"root={self.physical_checkout}\n")

    def test_external_relative_symlinks_keep_checkout_identity(self):
        for name, (_, alias) in self.links.items():
            with self.subTest(name=name):
                interpreter = "/bin/bash" if name.endswith(".bash") else "/bin/sh"
                result = self.run_script([interpreter, str(alias)])
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f"root={self.physical_checkout}\n")

    def test_path_lookup_from_unrelated_directory(self):
        for name in ("build.sh", "builder.sh"):
            _, alias = self.links[name]
            result = self.run_script(["/bin/sh", "-c", alias.name], prepend_path=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"root={self.physical_checkout}\n")

    def test_bare_script_filename_through_explicit_interpreter(self):
        # PATH deliberately does not contain the checkout.
        for name in ("build.sh", "builder.sh", "builder.bash"):
            with self.subTest(name=name):
                interpreter = "/bin/bash" if name.endswith(".bash") else "/bin/sh"
                result = subprocess.run(
                    [interpreter, name], cwd=self.checkout,
                    env={"PATH": "/usr/bin:/bin"}, text=True,
                    capture_output=True, check=False, timeout=10,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(
                    result.stdout, f"root={self.physical_checkout}\n"
                )

    def test_wrong_checkout_is_not_silently_accepted(self):
        fake = self.cwd / "unrelated-build"
        fake.write_text(launcher_prefix("build.sh"), encoding="utf-8")
        result = self.run_script(["/bin/sh", str(fake)])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not resolve to a checkout", result.stderr)


if __name__ == "__main__":
    unittest.main()
