#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""GNU G++ identity and native C++17 seed contracts (no source build)."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/g++.sh"
CXX = ROOT / "seeds/cxx.sh"
COMMON = ROOT / "scripts/whp-build/compiler-seed-common.sh"


class GNUCxxSeedTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory(prefix="whp-gxx-seed-")
        self.addCleanup(work.cleanup)
        self.tmp = Path(work.name)
        self.env = dict(os.environ)
        for name in ("WHP_GXX_SEED", "GXX", "WHP_GXX_LOCKED"):
            self.env.pop(name, None)

    def call(self, executable, *args, env=None, source=None):
        return subprocess.run(
            ["/bin/sh", str(executable), *args], input=source,
            env=self.env if env is None else env,
            capture_output=True, text=True, check=False, timeout=50,
        )

    def fixture(self, name, contents):
        path = self.tmp / name
        path.write_text(contents, encoding="utf-8")
        path.chmod(0o755)
        return path

    def test_posix_and_role_separation(self):
        text = SEED.read_text(encoding="utf-8")
        self.assertEqual(text.splitlines()[0], "#!/bin/sh")
        self.assertEqual(subprocess.run(
            ["/bin/sh", "-n", str(SEED)], check=False).returncode, 0)
        self.assertIn("whp-qemu-gxx-seed-adapter", COMMON.read_text())
        self.assertIn('WHP_GXX_SEED GXX', text)
        self.assertIn("WHP_GXX_LOCKED", text)
        self.assertNotIn("WHP_GXX_SEED", CXX.read_text())
        self.assertEqual(self.call(SEED, "--whp-gxx-adapter-probe").stdout.strip(),
                         "whp-qemu-gxx-seed-adapter")
        result = self.call(SEED, "--print-cxx")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_bad_override_does_not_fall_back(self):
        fake = self.fixture("banner-only",
                            "#!/bin/sh\n"
                            'case "$1" in --version) echo "g++ (GCC) 99";;'
                            ' -v) echo "gcc version 99";; esac\n'
                            "exit 0\n")
        for value in (str(self.tmp / "missing"), "/bin/sh",
                      "g++ -O2", str(SEED), str(CXX), str(fake)):
            with self.subTest(value=value):
                env = dict(self.env, WHP_GXX_SEED=value)
                result = self.call(SEED, "--print-seed", env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn("WHP_GXX_SEED", result.stderr)

    def test_gxx_name_does_not_admit_clang(self):
        clang = shutil.which("clang++")
        if not clang:
            self.skipTest("no Clang++ on runner")
        selected = self.call(SEED, "--print-gxx",
                             env=dict(self.env, WHP_GXX_SEED=clang))
        self.assertNotEqual(selected.returncode, 0)
        self.assertEqual(selected.stdout, "")
        self.assertIn("not the GNU GCC frontend", selected.stderr)

    def test_gxx_identity_and_stdlib_on_host(self):
        gxx = shutil.which("g++")
        if not gxx:
            self.skipTest("GNU G++ not installed")
        version = subprocess.run([gxx, "-v"], capture_output=True, text=True)
        if "gcc version " not in version.stdout + version.stderr:
            self.skipTest("g++ is not a native GNU GCC driver")
        env = dict(self.env, WHP_GXX_SEED=gxx)
        admitted = self.call(SEED, "--print-gxx", env=env)
        self.assertEqual(admitted.returncode, 0, admitted.stderr)
        chosen = admitted.stdout.strip()
        self.assertTrue(Path(chosen).is_file())
        self.assertEqual(self.call(SEED, "--check", env=env).returncode, 0)
        obj = self.tmp / "native.o"
        source = "int whp_gxx_probe() { return 37; }\n"
        compiled = self.call(SEED, "-std=c++17", "-x", "c++", "-",
                             "-c", "-o", str(obj),
                             env=dict(env, WHP_GXX_LOCKED="1", WHP_GXX_SEED=chosen),
                             source=source)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        self.assertGreater(obj.stat().st_size, 0)
        failing = self.call(SEED, "-x", "c++", "-",
                            env=dict(env, WHP_GXX_LOCKED="1",
                                     WHP_GXX_SEED=chosen),
                            source="#error expected failure\n")
        self.assertNotEqual(failing.returncode, 0)

    def test_cxx_stays_independent(self):
        # A GNU-only selector must not consult the generic C++ choice,
        # even if it is deliberately invalid.
        gxx = shutil.which("g++")
        if not gxx:
            self.skipTest("no G++")
        probe = self.call(SEED, "--check", env=dict(
            self.env, WHP_GXX_SEED=gxx, WHP_CXX_SEED="/nonexistent/cxx",
            CXX_FOR_BUILD="/nonexistent/cxx"))
        version = subprocess.run([gxx, "-v"], capture_output=True, text=True)
        if "gcc version " not in version.stdout + version.stderr:
            self.skipTest("host g++ is not GNU GCC")
        self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_locked_must_not_self_recurse(self):
        alias = self.tmp / "gxx-alias"
        alias.symlink_to(SEED)
        for value in ("", str(SEED), str(alias), "/no/such/gxx"):
            with self.subTest(value=value):
                result = self.call(SEED, "-c", "example.cc",
                                   env=dict(self.env, WHP_GXX_LOCKED="1",
                                            WHP_GXX_SEED=value))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("locked GNU G++", result.stderr)
        self.assertEqual(self.call(SEED, "--check",
            env=dict(self.env, WHP_GXX_SEED=str(alias))).returncode != 0, True)


if __name__ == "__main__":
    unittest.main()
