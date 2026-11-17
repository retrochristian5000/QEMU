#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check GNU sed identity, NUL support and separation from host sed."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
GNU = ROOT / "seeds/GNUsed.sh"
GENERIC = ROOT / "seeds/sed.sh"


class GNUsedTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="whp-gnused-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.host = shutil.which("sed")
        if not self.host:
            self.skipTest("native sed is absent")
        self.gnu = self.fake_gnu(self.bin / "gsed")
        self.env = os.environ.copy()
        for key in ("WHP_GNU_SED_SEED", "GNUSED", "GSED", "WHP_SED_SEED",
                    "SED", "WHP_MACOS_DEPENDENCY_PROVIDER", "WHP_BREW_SEED",
                    "WHP_HOMEBREW_BREW", "HOMEBREW_PREFIX", "MACPORTS_PREFIX"):
            self.env.pop(key, None)
        self.env["WHP_TEST_HOST_SED"] = self.host
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")

    def fake_gnu(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """#!/usr/bin/env python3
import os
import sys
args = sys.argv[1:]
if args == ["--version"]:
    print(os.environ.get("WHP_TEST_SED_BANNER", "sed (GNU sed) 4.10"))
    sys.exit(0)
if os.environ.get("WHP_TEST_SED_BANNER_ONLY") == "1":
    sys.exit(0)
if len(args) == 3 and args[:2] == ["--null-data", "s/beta/gamma/"]:
    with open(args[2], "rb") as source:
        sys.stdout.buffer.write(source.read().replace(b"beta", b"gamma"))
    sys.exit(0)
host = os.environ["WHP_TEST_HOST_SED"]
os.execv(host, [host, *args])
""",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *args, **extra):
        return subprocess.run(
            ["/bin/sh", str(GNU), *args], text=True, capture_output=True,
            env={**self.env, **extra}, check=False, timeout=30,
        )

    def fake_uname(self, name):
        tool = self.bin / "uname"
        tool.write_text("#!/bin/sh\nprintf '%s\\n' '" + name + "'\n")
        tool.chmod(0o755)

    def test_explicit_gnu_separate_from_native(self):
        result = self.run_seed("--print-seed", WHP_GNU_SED_SEED=str(self.gnu),
                               WHP_SED_SEED="/missing", SED="/missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gnu))
        result = self.run_seed("--check", WHP_GNU_SED_SEED=str(self.gnu))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--null-data verified", result.stdout)

    def test_forwarding_and_auto_discovery(self):
        self.fake_uname("Linux")
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.gnu))
        run = subprocess.run(
            ["/bin/sh", str(GNU), "-n", "s/^alpha$/beta/p"],
            input="alpha\n", text=True, capture_output=True, check=False,
            env={**self.env, "WHP_GNU_SED_SEED": str(self.gnu)},
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "beta\n")

    def test_reject_bsd_and_fake_banner(self):
        for settings in (
            {"WHP_TEST_SED_BANNER": "sed (BSD) 2026"},
            {"WHP_TEST_SED_BANNER_ONLY": "1"},
        ):
            with self.subTest(settings=settings):
                result = self.run_seed("--print-seed",
                                       WHP_GNU_SED_SEED=str(self.gnu),
                                       **settings)
                self.assertNotEqual(result.returncode, 0)

    def test_invalid_explicit_override_does_not_fallback(self):
        for variable in ("WHP_GNU_SED_SEED", "GNUSED", "GSED"):
            with self.subTest(variable=variable):
                result = self.run_seed("--print-seed", **{variable: "/missing"})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(variable, result.stderr)

    def test_recursion_guards_in_both_adapters(self):
        for provider in (GNU, GENERIC):
            with self.subTest(provider=provider):
                result = self.run_seed("--print-candidate",
                                       WHP_GNU_SED_SEED=str(provider))
                self.assertNotEqual(result.returncode, 0)
        link = self.root / "gsed-link"
        link.symlink_to(GNU)
        result = self.run_seed("--print-candidate",
                               WHP_GNU_SED_SEED=str(link))
        self.assertNotEqual(result.returncode, 0)
        generic = subprocess.run(
            ["/bin/sh", str(GENERIC), "--print-seed"],
            env={**self.env, "WHP_SED_SEED": str(GNU)},
            text=True, capture_output=True, check=False,
        )
        self.assertNotEqual(generic.returncode, 0)
        self.assertIn("points back", generic.stderr)

    def test_generic_prefers_native_sed(self):
        native = Path("/usr/bin/sed")
        if not native.is_file():
            self.skipTest("no native /usr/bin/sed")
        result = subprocess.run(
            ["/bin/sh", str(GENERIC), "--print-seed"],
            env=self.env, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(native))

    def test_homebrew_formula_and_lock(self):
        self.fake_uname("Darwin")
        prefix = self.root / "homebrew"
        tool = self.fake_gnu(prefix / "opt/gnu-sed/bin/gsed")
        brew = prefix / "bin/brew"
        brew.parent.mkdir(parents=True)
        brew.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  --whp-brew-adapter-probe) exit 2 ;;\n'
            '  --version) printf "Homebrew 5.0\\n" ;;\n'
            '  --prefix)\n'
            '    if [ "$#" -eq 1 ]; then printf "%s\\n" "$HOMEBREW_PREFIX"; exit 0; fi\n'
            '    if [ "$2" = --installed ] && [ "$3" = gnu-sed ]; then\n'
            '      printf "%s\\n" "$HOMEBREW_PREFIX/opt/gnu-sed"; exit 0\n'
            '    fi\n'
            '    exit 2 ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        brew.chmod(0o755)
        env = {
            "HOMEBREW_PREFIX": str(prefix), "WHP_BREW_SEED": str(brew),
            "WHP_MACOS_DEPENDENCY_PROVIDER": "homebrew",
        }
        result = self.run_seed("--print-seed", **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(tool))
        tool.unlink()
        result = self.run_seed("--print-seed", **env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("selected Homebrew", result.stderr)

    def test_macports_provider_isolation(self):
        self.fake_uname("Darwin")
        prefix = self.root / "ports"
        tool = self.fake_gnu(prefix / "bin/gsed")
        env = {"WHP_MACOS_DEPENDENCY_PROVIDER": "macports",
               "MACPORTS_PREFIX": str(prefix)}
        result = self.run_seed("--print-seed", **env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(tool))
        tool.unlink()
        result = self.run_seed("--print-seed", **env)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("selected MacPorts", result.stderr)

    def test_real_gnu_sed_when_present(self):
        version = subprocess.run(
            [self.host, "--version"], capture_output=True, text=True,
            check=False,
        )
        if "(GNU sed)" not in version.stdout:
            self.skipTest("host sed is not GNU")
        result = self.run_seed("--print-seed", WHP_GNU_SED_SEED=self.host)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), self.host)


if __name__ == "__main__":
    unittest.main()
