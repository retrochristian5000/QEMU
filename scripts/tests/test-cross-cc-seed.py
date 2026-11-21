#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Cross C compiler adapter: explicit target, no native fallback or run probe."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/cross-cc.sh"
TARGET = "powerpc-unknown-unknown-elf"


class CrossCcTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-cross-cc-test-")
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.env = dict(os.environ)
        for name in ("WHP_CROSS_CC_SEED", "WHP_CROSS_TARGET", "WHP_CROSS_CC_KIND",
                     "WHP_CROSS_SYSROOT"):
            self.env.pop(name, None)
        self.driver = self.directory / "mock-cross-driver"
        self.driver.write_text(
            "#!/bin/sh\n"
            "if [ \"${1:-}\" = --version ]; then printf 'mock cross compiler 1\\n'; exit 0; fi\n"
            "target=\nmode=${WHP_MOCK_KIND:-clang}\n"
            "for item do\n"
            "  case \"$item\" in\n"
            "    --target=*) target=${item#--target=} ;;\n"
            "  esac\n"
            "done\n"
            "if [ \"${1:-}\" = -dumpmachine ]; then printf '%s\\n' \"${WHP_MOCK_TARGET:-powerpc-unknown-unknown-elf}\"; exit 0; fi\n"
            "case \" $* \" in *\" -dumpmachine \"*)\n"
            "  printf '%s\\n' \"${target:-${WHP_MOCK_TARGET:-powerpc-unknown-unknown-elf}}\"; exit 0 ;;\n"
            "esac\n"
            "case \" $* \" in *\" -c \"*) ;; *) printf '%s\\n' 'link/run forbidden' >&2; exit 91 ;; esac\n"
            "if [ -n \"${WHP_MOCK_LOG:-}\" ]; then\n"
            "  printf 'args:' >> \"$WHP_MOCK_LOG\"\n"
            "  for item do printf '[%s]' \"$item\" >> \"$WHP_MOCK_LOG\"; done\n"
            "  printf '\\n' >> \"$WHP_MOCK_LOG\"\n"
            "  for key in SDKROOT MACOSX_DEPLOYMENT_TARGET CCC_OVERRIDE_OPTIONS CPATH LIBRARY_PATH CC_FOR_BUILD TARGET_TRIPLE; do\n"
            "    if printenv \"$key\" >/dev/null 2>&1; then printf 'poison:%s\\n' \"$key\" >> \"$WHP_MOCK_LOG\"; fi\n"
            "  done\n"
            "fi\n"
            "output=\n"
            "while [ \"$#\" -gt 0 ]; do\n"
            "  if [ \"$1\" = -o ]; then shift; output=$1; fi\n"
            "  shift\n"
            "done\n"
            "[ -n \"$output\" ] || exit 92\n"
            "printf 'MOCK-CROSS-OBJECT\\n' > \"$output\"\n",
            encoding="utf-8",
        )
        self.driver.chmod(0o700)
        self.env.update(WHP_CROSS_CC_SEED=str(self.driver),
                        WHP_CROSS_TARGET=TARGET, WHP_CROSS_CC_KIND="clang")

    def run_seed(self, *args, env=None, input_data=None):
        return subprocess.run(
            ["/bin/sh", str(SEED), *args],
            env=self.env if env is None else env,
            input=input_data, capture_output=True, text=True,
            check=False, timeout=20,
        )

    def test_posix_syntax_and_marker(self):
        result = subprocess.run(["/bin/sh", "-n", str(SEED)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        probe = self.run_seed("--whp-cross-cc-adapter-probe", env={})
        self.assertEqual(probe.returncode, 0)
        self.assertEqual(probe.stdout.strip(), "whp-qemu-cross-cc-seed-adapter")
        generic = self.run_seed("--whp-cc-adapter-probe", env={})
        self.assertEqual(generic.stdout, probe.stdout)

    def test_explicit_target_and_driver_required(self):
        for setting in ("WHP_CROSS_CC_SEED", "WHP_CROSS_TARGET", "WHP_CROSS_CC_KIND"):
            with self.subTest(setting=setting):
                env = dict(self.env)
                env.pop(setting, None)
                result = self.run_seed("--check", env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertIn(setting, result.stderr)
        for bad in ("powerpc", "--target=powerpc-unknown-elf", "powerpc unknown elf", "powerpc-unknown-elf\nfoo"):
            with self.subTest(target=bad):
                result = self.run_seed("--check", env=dict(self.env, WHP_CROSS_TARGET=bad))
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
        bad_kind = self.run_seed("--check", env=dict(self.env, WHP_CROSS_CC_KIND="auto"))
        self.assertEqual(bad_kind.returncode, 2)

    def test_compile_only_check_and_wrapper_identity(self):
        checked = self.run_seed("--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn(TARGET, checked.stdout)
        target = self.run_seed("--print-target")
        self.assertEqual(target.stdout, TARGET + "\n")
        driver = self.run_seed("--print-driver")
        self.assertEqual(Path(driver.stdout.strip()), self.driver)
        selected = self.run_seed("--print-seed")
        self.assertEqual(Path(selected.stdout.strip()).resolve(), SEED.resolve())
        obj = self.directory / "cross.o"
        compiled = self.run_seed("-c", "source.c", "-o", str(obj))
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        self.assertEqual(obj.read_text(), "MOCK-CROSS-OBJECT\n")
        wrong_api = self.run_seed("--print-cc")
        self.assertEqual(wrong_api.returncode, 2)

    def test_runtime_environment_is_not_native(self):
        logfile = self.directory / "calls.log"
        poisoned = dict(self.env, WHP_MOCK_LOG=str(logfile),
                        SDKROOT="/stale/native/sdk", MACOSX_DEPLOYMENT_TARGET="9.0",
                        CCC_OVERRIDE_OPTIONS="^--target=x86_64-apple-darwin",
                        CPATH="/stale/includes", LIBRARY_PATH="/stale/lib",
                        CC_FOR_BUILD="/stale/native/cc", TARGET_TRIPLE="x86_64-apple-darwin")
        obj = self.directory / "target.o"
        result = self.run_seed("-c", "target.c", "-o", str(obj), env=poisoned)
        self.assertEqual(result.returncode, 0, result.stderr)
        contents = logfile.read_text()
        self.assertIn("[--target=" + TARGET + "]", contents)
        self.assertNotIn("poison:", contents)
        self.assertEqual(obj.read_text(), "MOCK-CROSS-OBJECT\n")

    def test_target_override_is_rejected(self):
        for args in (("--target=x86_64-linux-gnu",), ("--target", "host"),
                     ("-target", "host"), ("-arch", "arm64"),
                     ("-isysroot", "/tmp"), ("--sysroot=/tmp",),
                     ("-m32",), ("-m64",), ("-Xclang", "-triple")):
            with self.subTest(args=args):
                result = self.run_seed("-c", "x.c", "-o", "x.o", *args)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(result.stdout, "")
                self.assertIn("override is forbidden", result.stderr)

    def test_explicit_sysroot_is_validated_and_passed(self):
        for bad in ("relative/sysroot", str(self.directory / "missing")):
            bad_result = self.run_seed("--check", env=dict(self.env, WHP_CROSS_SYSROOT=bad))
            self.assertEqual(bad_result.returncode, 2)
        sysroot = self.directory / "cross sysroot"
        sysroot.mkdir()
        log = self.directory / "sysroot.log"
        env = dict(self.env, WHP_CROSS_SYSROOT=str(sysroot), WHP_MOCK_LOG=str(log))
        checked = self.run_seed("--check", env=env)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("[--sysroot=" + str(sysroot) + "]", log.read_text())

    def test_gcc_mode_is_embedded_not_overridden(self):
        env = dict(self.env, WHP_CROSS_CC_KIND="gcc", WHP_MOCK_KIND="gcc")
        log = self.directory / "gcc.log"
        checked = self.run_seed("--check", env=dict(env, WHP_MOCK_LOG=str(log)))
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertNotIn("--target=", log.read_text())
        mismatched = self.run_seed("--check", env=dict(env, WHP_MOCK_TARGET="x86_64-unknown-linux-gnu"))
        self.assertEqual(mismatched.returncode, 2)
        self.assertIn("differs from compiler target", mismatched.stderr)

    def test_recursive_native_and_fake_compilers_rejected(self):
        # Native cc.sh reports the generic C adapter marker.
        native = ROOT / "seeds/cc.sh"
        if native.is_file():
            rejected = self.run_seed("--print-driver", env=dict(self.env, WHP_CROSS_CC_SEED=str(native)))
            self.assertNotEqual(rejected.returncode, 0)
            native_rejected = subprocess.run(
                ["/bin/sh", str(native), "--print-cc"],
                env=dict(self.env, WHP_CC_SEED=str(SEED)),
                capture_output=True, text=True, check=False, timeout=20,
            )
            self.assertNotEqual(native_rejected.returncode, 0)
            self.assertIn("loops into WHP adapter", native_rejected.stderr)
        copied = self.directory / "copied-cross.sh"
        copied.write_bytes(SEED.read_bytes())
        copied.chmod(0o700)
        rejected = self.run_seed("--print-driver", env=dict(self.env, WHP_CROSS_CC_SEED=str(copied)))
        self.assertNotEqual(rejected.returncode, 0)
        no_compile = self.directory / "fake-banner"
        no_compile.write_text(
            '#!/bin/sh\n'
            'case "$1" in --version) exit 0 ;; esac\n'
            'case " $* " in *" -dumpmachine "*) printf "' + TARGET + '\\n"; exit 0 ;; esac\n'
            'exit 0\n', encoding="utf-8")
        no_compile.chmod(0o700)
        failed = self.run_seed("--check", env=dict(self.env, WHP_CROSS_CC_SEED=str(no_compile)))
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("produced no cross object", failed.stderr)

    def test_real_clang_cross_object_when_available(self):
        clang = shutil.which("clang")
        if not clang:
            self.skipTest("Clang is not present")
        # A compile-only target may have no target runtime or linker.
        # Prefer PowerPC; Apple Clang may supply only ARM64 and X86 targets.
        # Each fallback remains explicitly target-selected rather than native.
        native = subprocess.run([clang, "-dumpmachine"], text=True,
                                capture_output=True, check=False).stdout.strip()
        env = None
        for triple in (TARGET, "aarch64-unknown-unknown-elf",
                       "x86_64-unknown-unknown-elf"):
            if triple == native:
                continue
            selected = dict(self.env, WHP_CROSS_CC_SEED=clang,
                            WHP_CROSS_TARGET=triple)
            if self.run_seed("--check", env=selected).returncode == 0:
                env = selected
                break
        if env is None:
            self.skipTest("installed Clang has no supported cross backend")
        source = self.directory / "real.c"
        source.write_text("int whp_cross_object(void) { return 27; }\n")
        out = self.directory / "real.o"
        built = self.run_seed("-c", str(source), "-o", str(out), env=env)
        self.assertEqual(built.returncode, 0, built.stderr)
        self.assertTrue(out.is_file())
        self.assertGreater(out.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
