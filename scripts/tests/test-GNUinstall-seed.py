#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""GNU-only install admission, delegation, recursion and provider boundaries."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/GNUinstall.sh"
GENERIC = ROOT / "seeds/install.sh"


class GNUInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-gnu-install-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.gnu = self.make_install(self.bin / "ginstall")
        self.env = os.environ.copy()
        for name in ("WHP_GNU_INSTALL_SEED", "WHP_INSTALL_SEED",
                     "WHP_INSTALL_LOCKED", "WHP_BREW_SEED",
                     "WHP_HOMEBREW_BREW", "HOMEBREW_PREFIX",
                     "WHP_MACOS_DEPENDENCY_PROVIDER", "MACPORTS_PREFIX"):
            self.env.pop(name, None)
        self.env["PATH"] = str(self.bin) + os.pathsep + self.env.get("PATH", "")

    def make_install(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        # Simulates the subset needed by native install, -D and --compare.
        # A fake banner alone cannot satisfy the seed's functional probe.
        path.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, shutil, sys\n"
            "a = sys.argv[1:]\n"
            "if a and a[0] == '--version':\n"
            " print(os.environ.get('TEST_GNU_INSTALL_BANNER', "
            "'install (GNU coreutils) 9.7'))\n"
            " sys.exit(0)\n"
            "if os.environ.get('TEST_GNU_INSTALL_BANNER_ONLY') == '1': sys.exit(0)\n"
            "if '-m' not in a: sys.exit(2)\n"
            "mode = int(a[a.index('-m') + 1], 8)\n"
            "dst = pathlib.Path(a[-1])\n"
            "if '-d' in a:\n"
            " dst.mkdir(parents=True, exist_ok=True)\n"
            " dst.chmod(mode)\n"
            " sys.exit(0)\n"
            "src = pathlib.Path(a[-2])\n"
            "if '-D' in a: dst.parent.mkdir(parents=True, exist_ok=True)\n"
            "if not dst.parent.is_dir(): sys.exit(2)\n"
            "if '--compare' not in a or not dst.exists() or "
            "src.read_bytes() != dst.read_bytes():\n"
            " shutil.copyfile(src, dst)\n"
            "dst.chmod(mode)\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *args, **settings):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env={**self.env, **settings}, text=True, capture_output=True,
            check=False, timeout=30,
        )

    def fake_uname(self, system):
        uname = self.bin / "uname"
        uname.write_text("#!/bin/sh\nprintf '%s\\n' '" + system + "'\n",
                         encoding="utf-8")
        uname.chmod(0o755)

    def test_explicit_gnu_does_not_inherit_generic_install(self):
        r = self.run_seed("--print-seed", WHP_GNU_INSTALL_SEED=str(self.gnu),
                          WHP_INSTALL_SEED="/nonexistent/native")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(self.gnu))
        check = self.run_seed("--check", WHP_GNU_INSTALL_SEED=str(self.gnu))
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("-D and --compare verified", check.stdout)

    def test_forwarding_keeps_content_and_permissions(self):
        src, dst = self.root / "source", self.root / "destination"
        src.write_text("payload\n", encoding="utf-8")
        r = self.run_seed("-m", "0644", str(src), str(dst),
                          WHP_GNU_INSTALL_SEED=str(self.gnu))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(dst.read_text(), "payload\n")
        self.assertEqual(dst.stat().st_mode & 0o777, 0o644)

    def test_invalid_vendor_and_banner_only_are_rejected(self):
        r = self.run_seed("--print-seed", WHP_GNU_INSTALL_SEED="/missing/install")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("WHP_GNU_INSTALL_SEED", r.stderr)
        r = self.run_seed("--print-seed", WHP_GNU_INSTALL_SEED=str(self.gnu),
                          TEST_GNU_INSTALL_BANNER="install (BSD) 99.0")
        self.assertNotEqual(r.returncode, 0)
        r = self.run_seed("--print-seed", WHP_GNU_INSTALL_SEED=str(self.gnu),
                          TEST_GNU_INSTALL_BANNER_ONLY="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("functional probe failed", r.stderr)

    def test_generic_and_gnu_adapters_reject_recursion(self):
        for value in (SEED, GENERIC):
            with self.subTest(value=value):
                r = self.run_seed("--print-candidate",
                                  WHP_GNU_INSTALL_SEED=str(value))
                self.assertNotEqual(r.returncode, 0)
        r = subprocess.run(["/bin/sh", str(GENERIC), "--print-seed"],
                           env={**self.env, "WHP_INSTALL_SEED": str(SEED)},
                           capture_output=True, text=True, check=False)
        self.assertNotEqual(r.returncode, 0)
        alias = self.root / "gnu-install-alias"
        alias.symlink_to(SEED)
        r = self.run_seed("--print-candidate", WHP_GNU_INSTALL_SEED=str(alias))
        self.assertNotEqual(r.returncode, 0)

    def test_automatic_ginstall_selection(self):
        self.fake_uname("Linux")
        r = self.run_seed("--print-seed")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(self.gnu))

    def test_selected_homebrew_keg_only_coreutils(self):
        self.fake_uname("Darwin")
        prefix = self.root / "homebrew"
        keg = self.make_install(prefix / "opt/coreutils/bin/ginstall")
        brew = prefix / "bin/brew"
        brew.parent.mkdir(parents=True)
        brew.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            '  --whp-brew-adapter-probe) exit 2 ;;\n'
            '  --version) printf "Homebrew 5.0\\n" ;;\n'
            '  --prefix)\n'
            '    if [ "$#" -eq 1 ]; then printf "%s\\n" "$HOMEBREW_PREFIX"; exit 0; fi\n'
            '    if [ "$2" = --installed ] && [ "$3" = coreutils ]; then\n'
            '      printf "%s\\n" "$HOMEBREW_PREFIX/opt/coreutils"; exit 0\n'
            '    fi\n'
            '    exit 2 ;;\n'
            '  *) exit 2 ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        brew.chmod(0o755)
        overrides = {
            "HOMEBREW_PREFIX": str(prefix),
            "WHP_BREW_SEED": str(brew),
            "WHP_MACOS_DEPENDENCY_PROVIDER": "homebrew",
        }
        r = self.run_seed("--print-seed", **overrides)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(keg))
        keg.unlink()
        r = self.run_seed("--print-seed", **overrides)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("selected Homebrew", r.stderr)

    def test_macports_provider_does_not_choose_homebrew(self):
        self.fake_uname("Darwin")
        prefix = self.root / "macports"
        port = self.make_install(prefix / "bin/ginstall")
        r = self.run_seed("--print-seed",
                          WHP_MACOS_DEPENDENCY_PROVIDER="macports",
                          MACPORTS_PREFIX=str(prefix))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(port))

    def test_real_gnu_install_when_available(self):
        real = Path("/usr/bin/install")
        if not real.is_file():
            self.skipTest("no system install")
        banner = subprocess.run([str(real), "--version"], capture_output=True,
                                text=True, check=False)
        if "GNU coreutils" not in banner.stdout:
            self.skipTest("system install is not GNU coreutils")
        r = self.run_seed("--print-seed", WHP_GNU_INSTALL_SEED=str(real))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), str(real))


if __name__ == "__main__":
    unittest.main()
