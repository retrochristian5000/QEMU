#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the CMake fork seed contract without compiling CMake."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SOURCE = ROOT / "scripts/ensure-cmake.py"
SEED = ROOT / "seeds/cmake.sh"
spec = importlib.util.spec_from_file_location("whp_cmake_bootstrap", SOURCE)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CMakeBootstrapTests(unittest.TestCase):
    def test_submodule_and_bootstrap_contract(self):
        gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
        self.assertIn('[submodule "toolchains/cmake"]', gitmodules)
        self.assertIn('https://github.com/retrochristian5000/CMake.git', gitmodules)
        self.assertIn('branch = master', gitmodules)
        code = SOURCE.read_text(encoding="utf-8")
        self.assertIn("reconcile_submodule(ROOT, SUBMODULE, git=git)", code)
        self.assertIn('"-DCMAKE_USE_OPENSSL=OFF"', code)
        self.assertNotIn('"seeds/cmake.sh"', code)
        subprocess.run(["/bin/sh", "-n", str(SEED)], check=True)

    def test_cross_target_environment_does_not_escape(self):
        with mock.patch.dict(os.environ, {
            "CMAKE_TOOLCHAIN_FILE": "/foreign.cmake",
            "CMAKE_C_COMPILER_TARGET": "powerpc-apple-darwin9",
            "CXXFLAGS": "-target powerpc-apple-darwin9",
            "LDFLAGS": "-Wl,-platform_version,macos,99,99",
            "build_alias": "powerpc-apple-darwin9",
            "CCC_OVERRIDE_OPTIONS": "^--target=powerpc-apple-darwin9",
            "TARGET_TRIPLE": "powerpc-apple-darwin9",
            "CC_FOR_TARGET": "/cross/cc",
            "CMAKE_OSX_ARCHITECTURES": "ppc",
            "IPHONEOS_DEPLOYMENT_TARGET": "14.0",
        }):
            env = module.host_environment(
                "/usr/bin/cc", "/usr/bin/c++", "/usr/bin/make",
                "/macOS/SDK/MacOSX.sdk", "26.0",
            )
        for key in ("CMAKE_TOOLCHAIN_FILE", "CMAKE_C_COMPILER_TARGET",
                    "build_alias", "CCC_OVERRIDE_OPTIONS", "TARGET_TRIPLE",
                    "CC_FOR_TARGET", "CMAKE_OSX_ARCHITECTURES",
                    "IPHONEOS_DEPLOYMENT_TARGET"):
            self.assertNotIn(key, env)
        self.assertEqual(env["CC"], "/usr/bin/cc")
        self.assertEqual(env["CXX"], "/usr/bin/c++")
        self.assertEqual(env["CXXFLAGS"], "")
        self.assertEqual(env["LDFLAGS"], "")
        if sys.platform != "darwin":
            self.assertNotIn("SDKROOT", env)

    def test_nonexecutable_native_seed_uses_posix_shell(self):
        # A Git 100644 seed is readable but cannot be executed directly.
        # CMake's bootstrap must not require a checkout chmod.
        with tempfile.TemporaryDirectory(prefix="whp-cmake-seed-mode-") as td:
            base = Path(td)
            (base / "seeds").mkdir()
            selected = base / "native-make"
            selected.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            selected.chmod(0o700)
            adapter = base / "seeds" / "make.sh"
            adapter.write_text(
                "#!/bin/sh\n"
                'test "$1" = --print-make || exit 2\n'
                f"printf '%s\\n' '{selected}'\n",
                encoding="utf-8",
            )
            adapter.chmod(0o600)
            self.assertFalse(os.access(adapter, os.X_OK))
            with mock.patch.object(module, "ROOT", base):
                self.assertEqual(
                    module.admitted_tool("make.sh", "--print-make"),
                    str(selected),
                )
                with self.assertRaisesRegex(RuntimeError, "missing"):
                    module.admitted_tool("missing.sh", "--print-make")

    def test_explicit_cmake_and_source_mode_are_exclusive(self):
        with tempfile.TemporaryDirectory(prefix="whp-cmake-seed-") as td:
            good = Path(td) / "cmake"
            old = Path(td) / "old-cmake"
            for binary, banner in ((good, "cmake version 4.1.1"),
                                   (old, "cmake version 3.19.9")):
                binary.write_text(
                    '#!/bin/sh\n'
                    'if [ "$1" = --version ]; then\n'
                    f"  printf '%s\\n' '{banner}'\n"
                    "fi\n", encoding="utf-8",
                )
                binary.chmod(0o700)
            def check(mode, executable):
                env = os.environ.copy()
                for name in ("BOOTSTRAP_CMAKE", "WHP_CMAKE_SEED", "CMAKE_CMD", "CMAKE"):
                    env.pop(name, None)
                env.update({"BOOTSTRAP_CMAKE": mode,
                            "WHP_CMAKE_SEED": str(executable)})
                return subprocess.run(
                    ["/bin/sh", str(SEED), "--print-cmake"],
                    env=env, capture_output=True, text=True, check=False,
                )
            selected = check("auto", good)
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selected.stdout.strip(), str(good))
            rejected = check("0", old)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("WHP_CMAKE_SEED", rejected.stderr)
            conflict = check("1", good)
            self.assertNotEqual(conflict.returncode, 0)
            self.assertIn("conflicts with an explicit", conflict.stderr)

    def test_explicit_cmake_under_prefix_with_spaces(self):
        # The native prefix may be inside a checkout or build path with spaces.
        # Its absolute executable is one argument, not a shell command line.
        with tempfile.TemporaryDirectory(prefix="whp-cmake-prefix-") as td:
            bin_dir = Path(td) / "native tools" / "bin"
            bin_dir.mkdir(parents=True)
            cmake = bin_dir / "cmake"
            cmake.write_text(
                "#!/bin/sh\n"
                'if [ "$1" = --version ]; then\n'
                "    printf '%s\\n' 'cmake version 4.5.20261118'\n"
                "    exit 0\n"
                "fi\n"
                "exit 2\n",
                encoding="utf-8",
            )
            cmake.chmod(0o700)
            env = os.environ.copy()
            for name in ("BOOTSTRAP_CMAKE", "WHP_CMAKE_SEED", "CMAKE_CMD",
                         "CMAKE"):
                env.pop(name, None)
            env.update({"BOOTSTRAP_CMAKE": "auto",
                        "WHP_CMAKE_SEED": str(cmake)})
            result = subprocess.run(
                ["/bin/sh", str(SEED), "--print-cmake"],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(cmake))

            # A multiword command without an executable pathname must remain
            # invalid. Shell tokenization would otherwise mis-select a tool.
            env["WHP_CMAKE_SEED"] = "cmake --version"
            rejected = subprocess.run(
                ["/bin/sh", str(SEED), "--print-cmake"],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("WHP_CMAKE_SEED", rejected.stderr)

            # Invalid absolute paths must still fail closed.
            env["WHP_CMAKE_SEED"] = str(bin_dir / "missing cmake")
            missing = subprocess.run(
                ["/bin/sh", str(SEED), "--print-cmake"],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(missing.returncode, 0)

    def test_actual_cmake_in_space_prefix_configures_project(self):
        installed = shutil.which("cmake")
        if installed is None:
            self.skipTest("host CMake is unavailable")
        with tempfile.TemporaryDirectory(prefix="whp-cmake-downstream-") as td:
            work = Path(td)
            tool_dir = work / "native tools" / "bin"
            tool_dir.mkdir(parents=True)
            candidate = tool_dir / "cmake"
            candidate.symlink_to(installed)
            env = os.environ.copy()
            for name in ("BOOTSTRAP_CMAKE", "WHP_CMAKE_SEED", "CMAKE_CMD",
                         "CMAKE"):
                env.pop(name, None)
            env.update({"BOOTSTRAP_CMAKE": "0",
                        "WHP_CMAKE_SEED": str(candidate)})
            selected = subprocess.run(
                ["/bin/sh", str(SEED), "--print-cmake"],
                env=env, capture_output=True, text=True, check=False,
            )
            if selected.returncode and "host CMake >= 3.20" in selected.stderr:
                self.skipTest("host CMake is older than the supported minimum")
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selected.stdout.strip(), str(candidate))

            source = work / "downstream project"
            source.mkdir()
            (source / "CMakeLists.txt").write_text(
                "cmake_minimum_required(VERSION 3.20)\n"
                "project(WHP_CMake_Downstream LANGUAGES NONE)\n"
                'file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/configured.txt" "ok")\n',
                encoding="utf-8",
            )
            output = work / "generated graph"
            result = subprocess.run(
                [str(candidate), "-S", str(source), "-B", str(output),
                 "-G", "Unix Makefiles"],
                env=env, capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(
                (output / "configured.txt").read_text(encoding="utf-8"), "ok",
            )

    def test_identity_changes_with_sdk_or_source(self):
        with mock.patch.object(module, "version", return_value="fixture"):
            first = module.identity("a" * 40, "/cc", "/cxx", "/make", "", "")
            same = module.identity("a" * 40, "/cc", "/cxx", "/make", "", "")
            different = module.identity("b" * 40, "/cc", "/cxx", "/make", "", "")
            sdk = module.identity("a" * 40, "/cc", "/cxx", "/make",
                                  "/macos/MacOSX.sdk", "26.0")
        self.assertEqual(first, same)
        self.assertNotEqual(first, different)
        self.assertNotEqual(first, sdk)


if __name__ == "__main__":
    unittest.main()
