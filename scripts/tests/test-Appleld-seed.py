#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise Apple linker selection and the actual native probe on Darwin."""

import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/Appleld.sh"


class AppleLinkerSeedTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-apple-ld-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        (self.root / "seeds").mkdir()
        helper = self.root / "scripts/whp-build"
        helper.mkdir(parents=True)
        self.seed = self.root / "seeds/Appleld.sh"
        shutil.copy2(SEED, self.seed)
        shutil.copy2(ROOT / "scripts/whp-build/macos-developer-tools.sh",
                     helper / "macos-developer-tools.sh")
        self.tools = self.root / "bin"
        self.tools.mkdir()
        self.developer = self.root / "Xcode.app/Contents/Developer"
        self.apple = self.developer / "usr/bin/ld"
        self.apple.parent.mkdir(parents=True)
        self.log = self.root / "probe.log"
        self.args = self.root / "args.log"
        self.env = os.environ.copy()
        for key in ("WHP_APPLE_LD_SEED", "SDKROOT", "WHP_XCRUN_SEED",
                    "WHP_LD_SEED", "LD_FOR_BUILD", "DEVELOPER_DIR"):
            self.env.pop(key, None)
        self.env.update({
            "PATH": str(self.tools) + os.pathsep + self.env["PATH"],
            "DEVELOPER_DIR": str(self.developer),
            "WHP_TEST_LD": str(self.apple),
            "WHP_TEST_PROBE": str(self.log),
            "WHP_TEST_ARGS": str(self.args),
        })
        self.script(self.tools / "uname", 'printf "Darwin\\n"\n')
        self.script(self.tools / "xcrun", '''
test "$#" -eq 4 && test "$1" = --sdk && test "$2" = macosx &&
    test "$3" = --find && test "$4" = ld || exit 1
printf '%s\\n' "$WHP_TEST_LD"
''')
        # Only the expensive native compilation probe is mocked here.
        self.script(self.root / "seeds/ld.sh", '''
case "${1:-}" in
    --whp-ld-adapter-probe)
        printf '%s\\n' whp-qemu-ld-seed-adapter; exit 0 ;;
esac
test "$1" = --print-ld && test -z "$LD_FOR_BUILD" || exit 1
printf '%s\\n' "$WHP_LD_SEED" >> "$WHP_TEST_PROBE"
test "${WHP_TEST_REJECT:-0}" = 0 || exit 1
printf '%s\\n' "$WHP_LD_SEED"
''')
        self.linker(self.apple, "@(#)PROGRAM:ld PROJECT:ld-27106.1")

    @staticmethod
    def script(path, body):
        path.write_text("#!/bin/sh\nset -eu\n" + body, encoding="utf-8")
        path.chmod(0o700)

    def linker(self, path, banner):
        self.script(path, '''
case "${1:-}" in
    --whp-ld-adapter-probe) exit 1 ;;
    -v) printf '%s\\n' 'BANNER' >&2; exit 0 ;;
esac
printf '%s\\n' "$@" > "$WHP_TEST_ARGS"
'''.replace("BANNER", banner))

    def run_seed(self, *args, **env):
        return subprocess.run(
            ["/bin/sh", str(self.seed), *args],
            env={**self.env, **env}, capture_output=True, text=True,
            check=False,
        )

    def test_default_selected_developer_linker(self):
        result = self.run_seed("--print-ld", LD_FOR_BUILD="/wrong/ld")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, str(self.apple) + "\n")
        self.assertEqual(self.log.read_text(), str(self.apple) + "\n")

    def test_explicit_apple_linker_and_classic_identity(self):
        classic = self.tools / "ld-classic"
        self.linker(classic, "@(#)PROGRAM:ld-classic PROJECT:ld64-951.9")
        result = self.run_seed("--check", WHP_APPLE_LD_SEED=str(classic))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PROJECT:ld64-951.9", result.stdout)

    def test_reject_wrong_families_and_recursion(self):
        for name, banner in (("gnu", "GNU ld (GNU Binutils) 2.44"),
                             ("lld", "LLD 24.0.0"),
                             ("unknown", "vendor linker")):
            path = self.tools / name
            self.linker(path, banner)
            with self.subTest(name=name):
                result = self.run_seed("--print-seed",
                                       WHP_APPLE_LD_SEED=str(path))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("not an Apple Mach-O linker", result.stderr)
        for path in (self.seed, self.root / "seeds/ld.sh"):
            self.assertNotEqual(self.run_seed(
                "--print-seed", WHP_APPLE_LD_SEED=str(path)).returncode, 0)
        self.assertFalse(self.log.exists())

    def test_broken_selection_and_failed_native_probe(self):
        result = self.run_seed("--print-seed", DEVELOPER_DIR="/missing/xcode")
        self.assertNotEqual(result.returncode, 0)
        result = self.run_seed("--print-seed", WHP_TEST_LD="/bin/false")
        self.assertNotEqual(result.returncode, 0)
        result = self.run_seed("--print-seed", WHP_TEST_REJECT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed native relocatable link probe", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_forwarding_does_not_repeat_native_probe(self):
        args = ["-r", "-o", "output with spaces.o", "input.o"]
        result = self.run_seed(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.args.read_text().splitlines(), args)
        self.assertFalse(self.log.exists())

    def test_non_darwin_is_not_an_apple_provider(self):
        self.script(self.tools / "uname", 'printf "Linux\\n"\n')
        result = self.run_seed("--check")
        self.assertEqual(result.returncode, 0)
        self.assertIn("not applicable", result.stdout)
        self.assertNotEqual(self.run_seed("--print-seed").returncode, 0)

    @unittest.skipUnless(platform.system() == "Darwin", "requires macOS")
    def test_real_apple_native_linker(self):
        env = os.environ.copy()
        for key in ("WHP_APPLE_LD_SEED", "WHP_LD_SEED", "LD_FOR_BUILD"):
            env.pop(key, None)
        selected = subprocess.run(
            ["/bin/sh", str(SEED), "--print-ld"], env=env,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        self.assertTrue(Path(selected).is_file())
        # Also validate the public /usr/bin dispatcher found during the scan.
        subprocess.run(
            ["/bin/sh", str(SEED), "--check"],
            env={**env, "WHP_APPLE_LD_SEED": "/usr/bin/ld"}, check=True,
        )


if __name__ == "__main__":
    unittest.main()
