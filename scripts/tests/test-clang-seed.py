#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Clang selection and explicit cc.sh handoff, without building LLVM."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/clang.sh"
CC = ROOT / "seeds/cc.sh"
CXX = ROOT / "seeds/cxx.sh"


class ClangSeedTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="whp-clang-seed-")
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)
        self.native = shutil.which("clang")
        self.env = dict(os.environ)
        for key in ("WHP_CLANG_SEED", "WHP_CC_SEED", "CC_FOR_BUILD",
                    "WHP_CXX_SEED", "CXX_FOR_BUILD"):
            self.env.pop(key, None)

    def invoke(self, executable, *args, env=None, input_data=None):
        return subprocess.run(
            ["/bin/sh", str(executable), *args],
            env=self.env if env is None else env, input=input_data,
            capture_output=True, text=True, check=False, timeout=30,
        )

    def test_posix_launcher(self):
        self.assertEqual(SEED.read_text(encoding="utf-8").splitlines()[0],
                         "#!/bin/sh")
        result = subprocess.run(["/bin/sh", "-n", str(SEED)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_explicit_invalid_clang_does_not_fall_back(self):
        imitation = self.directory / "imitation-clang"
        imitation.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = --version ]; then printf "clang version 99\\n"; '
            "exit 0; fi\n"
            "exit 43\n",
            encoding="utf-8",
        )
        imitation.chmod(0o755)
        for value in (str(self.directory / "missing"), "clang -O2", "/bin/sh",
                      str(SEED), str(imitation)):
            with self.subTest(value=value):
                result = self.invoke(SEED, "--print-seed", env=dict(
                    self.env, WHP_CLANG_SEED=value))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("WHP_CLANG_SEED", result.stderr)

    def test_recursive_clang_alias_is_rejected(self):
        copied = self.directory / "copied-seed"
        copied.write_bytes(SEED.read_bytes())
        copied.chmod(0o755)
        alias = self.directory / "clang-alias"
        alias.symlink_to(SEED)
        for value in (str(copied), str(alias)):
            with self.subTest(value=value):
                result = self.invoke(SEED, "--print-clang", env=dict(
                    self.env, WHP_CLANG_SEED=value))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_native_autodiscovery(self):
        if not self.native:
            self.skipTest("Clang not installed on test host")
        result = self.invoke(SEED, "--print-clang")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(Path(result.stdout.strip()).is_file())
        self.assertEqual(self.invoke(SEED, "--check").returncode, 0)

    def test_native_compiler_must_be_clang(self):
        if not self.native:
            self.skipTest("Clang not installed on test host")
        # This wrapper really compiles, links and runs native programs, but
        # lies about the frontend macro result. It must not be mistaken for
        # Clang just because it reports a plausible version and compiles C.
        imitation = self.directory / "not-really-clang"
        imitation.write_text(
            "#!/bin/sh\n"
            'case " $* " in *" -dM "*) echo "#define __GNUC__ 4"; exit 0 ;; esac\n'
            'exec "$WHP_TEST_REAL_CLANG" "$@"\n',
            encoding="utf-8",
        )
        imitation.chmod(0o755)
        env = dict(self.env, WHP_CLANG_SEED=str(imitation),
                   WHP_TEST_REAL_CLANG=self.native)
        result = self.invoke(SEED, "--print-clang", env=env)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("not a usable Clang frontend", result.stderr)

    def test_native_clang_and_compiler_execution(self):
        if not self.native:
            self.skipTest("Clang not installed on test host")
        env = dict(self.env, WHP_CLANG_SEED=self.native)
        selected = self.invoke(SEED, "--print-seed", env=env)
        self.assertEqual(selected.returncode, 0, selected.stderr)
        self.assertEqual(Path(selected.stdout.strip()).resolve(),
                         Path(self.native).resolve())
        self.assertEqual(self.invoke(SEED, "--check", env=env).returncode, 0)
        self.assertEqual(self.invoke(SEED, "--print-cxx", env=env).returncode, 2)
        object_path = self.directory / "probe.o"
        built = self.invoke(
            SEED, "-c", "-x", "c", "-", "-o", str(object_path), env=env,
            input_data="int whp_clang_probe(void) { return 71; }\n",
        )
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertGreater(object_path.stat().st_size, 0)

    def test_cc_handoff_and_priority(self):
        if not self.native:
            self.skipTest("Clang not installed on test host")
        # A selected Clang need not be called cc or even be under a standard
        # executable name. It remains a real native compiler after handoff.
        alternate = self.directory / "independent-clang"
        alternate.write_text(
            "#!/bin/sh\n"
            'exec "$WHP_TEST_REAL_CLANG" "$@"\n',
            encoding="utf-8",
        )
        alternate.chmod(0o755)
        env = dict(self.env, WHP_CLANG_SEED=str(alternate),
                   WHP_TEST_REAL_CLANG=self.native)
        clang = self.invoke(SEED, "--print-clang", env=env)
        cc = self.invoke(CC, "--print-cc", env=env)
        self.assertEqual(clang.returncode, 0, clang.stderr)
        self.assertEqual(cc.returncode, 0, cc.stderr)
        self.assertEqual(cc.stdout.strip(), clang.stdout.strip())
        self.assertEqual(Path(cc.stdout.strip()).resolve(), alternate.resolve())

        # WHP_CC_SEED remains authoritative, even if the optional Clang
        # override is unusable. It must not unexpectedly reselect a compiler.
        native_cc = shutil.which("cc")
        if native_cc:
            priority_env = dict(self.env, WHP_CC_SEED=native_cc,
                                WHP_CLANG_SEED=str(self.directory / "missing"))
            selected = self.invoke(CC, "--print-cc", env=priority_env)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(Path(selected.stdout.strip()).resolve(),
                             Path(native_cc).resolve())

        # Do not mix a custom C compiler with an unrelated C++ fallback.
        # No clang++ sibling exists beside this deliberately named wrapper.
        cxx = self.invoke(CXX, "--print-cxx", env=env)
        self.assertNotEqual(cxx.returncode, 0)
        self.assertIn("no usable paired C++17 compiler", cxx.stderr)


if __name__ == "__main__":
    unittest.main()
