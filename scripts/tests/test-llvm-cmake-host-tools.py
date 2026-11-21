#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise standalone firmware LLVM CMake/Ninja selection without LLVM builds."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/whp-build/llvm-cmake-tools.bash"
I386 = ROOT / "scripts/bootstrap-i386-clang.bash"
POWERPC = ROOT / "scripts/bootstrap-powerpc-clang-base.bash"


class FirmwareLLVMBuildTools(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-llvm-build-tools-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.compiler_dir = self.directory / "tools"
        self.compiler_dir.mkdir()
        self.ninja_dir = self.directory / "tool chain"
        self.ninja_dir.mkdir()
        self.ninja = self.ninja_dir / "ninja"
        self.cmake = self.compiler_dir / "cmake"
        self.old_cmake = self.compiler_dir / "old-cmake"
        self._executable(self.ninja, "1.12.1")
        self._executable(self.cmake, "cmake version 3.31.6")
        self._executable(self.old_cmake, "cmake version 3.18.4")

    def _executable(self, path: Path, version: str):
        path.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = --version ]; then\n'
            + "    printf '%s\\n' " + "'" + version + "'\n"
            + "    exit 0\n"
            + "fi\n"
            + "exit 0\n",
            encoding="utf-8",
        )
        path.chmod(0o700)

    def select(self, cache_dir=None, **overrides):
        env = os.environ.copy()
        for key in ("WHP_CMAKE_SEED", "CMAKE_CMD", "CMAKE", "NINJA_CMD", "NINJA"):
            env.pop(key, None)
        env.update({
            "SOURCE_DIR": str(ROOT),
            "CMAKE_CMD": str(self.cmake),
            "NINJA_CMD": str(self.ninja),
            "WHP_LLVM_TEST_CACHE": str(cache_dir) if cache_dir else "",
            **overrides,
        })
        return subprocess.run(
            [
                "bash", "-c",
                'set -euo pipefail\n'
                'source "$SOURCE_DIR/scripts/whp-build/llvm-cmake-tools.bash"\n'
                'whp_llvm_select_cmake_ninja\n'
                'if [ -n "$WHP_LLVM_TEST_CACHE" ]; then\n'
                '    whp_llvm_verify_ninja_cache "$WHP_LLVM_TEST_CACHE"\n'
                'fi\n'
                'printf "%s\\n%s\\n" "$whp_llvm_cmake_cmd" "$whp_llvm_ninja_cmd"\n',
            ],
            cwd=self.directory, env=env, capture_output=True, text=True,
            check=False, timeout=12,
        )

    def test_uses_validated_explicit_cmake_and_ninja(self):
        result = self.select()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [str(self.cmake), str(self.ninja)],
        )

    def test_cmake_seed_override_has_precedence(self):
        result = self.select(WHP_CMAKE_SEED=str(self.cmake),
                             CMAKE_CMD=str(self.old_cmake))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[0], str(self.cmake))

    def test_stale_cmake_fails_without_path_fallback(self):
        result = self.select(CMAKE_CMD=str(self.old_cmake))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CMAKE_CMD must select host CMake >= 3.20", result.stderr)

    def test_explicit_missing_ninja_fails_closed(self):
        result = self.select(NINJA_CMD=str(self.directory / "missing-ninja"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LLVM host Ninja is not executable", result.stderr)

    def test_relative_ninja_is_frozen_before_cmake_changes_directory(self):
        relative = "./tool chain/ninja"
        result = self.select(NINJA_CMD=relative)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines()[1], str(self.ninja))

    def test_existing_ninja_cache_preserved_if_identical(self):
        build = self.directory / "llvm-build"
        build.mkdir()
        cache = build / "CMakeCache.txt"
        cache.write_text(
            f"CMAKE_MAKE_PROGRAM:FILEPATH={self.ninja}\n", encoding="utf-8",
        )
        result = self.select(cache_dir=build)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(cache.read_text(encoding="utf-8").strip(),
                         f"CMAKE_MAKE_PROGRAM:FILEPATH={self.ninja}")

    def test_cached_ninja_symlink_alias_is_same_build_tool(self):
        build = self.directory / "llvm-build"
        build.mkdir()
        alias = self.directory / "cached-ninja"
        alias.symlink_to(self.ninja)
        cache = build / "CMakeCache.txt"
        cache.write_text(
            f"CMAKE_MAKE_PROGRAM:FILEPATH={alias}\n", encoding="utf-8",
        )
        graph = build / "build.ninja"
        graph.write_text("preserve graph\n", encoding="utf-8")
        result = self.select(cache_dir=build)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(alias), cache.read_text(encoding="utf-8"))
        self.assertEqual(graph.read_text(encoding="utf-8"), "preserve graph\n")

    def test_cached_ninja_copy_with_same_version_is_distinct(self):
        build = self.directory / "llvm-build"
        build.mkdir()
        copy = self.directory / "different-ninja"
        copy.write_bytes(self.ninja.read_bytes())
        copy.chmod(0o700)
        (build / "CMakeCache.txt").write_text(
            f"CMAKE_MAKE_PROGRAM:FILEPATH={copy}\n", encoding="utf-8",
        )
        result = self.select(cache_dir=build)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different build tool", result.stderr)

    def test_broken_cached_ninja_symlink_fails_closed(self):
        build = self.directory / "llvm-build"
        build.mkdir()
        broken = self.directory / "missing-cached-ninja"
        broken.symlink_to(self.directory / "missing-tool")
        (build / "CMakeCache.txt").write_text(
            f"CMAKE_MAKE_PROGRAM:FILEPATH={broken}\n", encoding="utf-8",
        )
        result = self.select(cache_dir=build)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different build tool", result.stderr)

    def test_conflicting_ninja_cache_fails_without_deleting_graph(self):
        build = self.directory / "llvm-build"
        build.mkdir()
        cache = build / "CMakeCache.txt"
        old_ninja = self.directory / "old-ninja"
        cache.write_text(
            f"CMAKE_MAKE_PROGRAM:FILEPATH={old_ninja}\n",
            encoding="utf-8",
        )
        graph = build / "build.ninja"
        graph.write_text("preserve graph\n", encoding="utf-8")
        result = self.select(cache_dir=build)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("different build tool", result.stderr)
        self.assertEqual(graph.read_text(encoding="utf-8"), "preserve graph\n")
        self.assertIn(str(old_ninja), cache.read_text(encoding="utf-8"))

    def test_multiple_cmake_make_program_values_are_rejected(self):
        build = self.directory / "llvm-build"
        build.mkdir()
        (build / "CMakeCache.txt").write_text(
            f"CMAKE_MAKE_PROGRAM:FILEPATH={self.ninja}\n"
            f"CMAKE_MAKE_PROGRAM:STRING={self.ninja}\n",
            encoding="utf-8",
        )
        result = self.select(cache_dir=build)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple CMAKE_MAKE_PROGRAM", result.stderr)

    def test_standalone_llvm_lanes_use_one_producer_and_generator(self):
        for path in (I386, POWERPC):
            with self.subTest(path=path.name):
                code = path.read_text(encoding="utf-8")
                self.assertIn('source "$SOURCE_DIR/scripts/whp-build/llvm-cmake-tools.bash"', code)
                self.assertIn("whp_llvm_select_cmake_ninja || exit 1", code)
                self.assertIn('whp_llvm_verify_ninja_cache "$LLVM_BUILD_DIR" || exit 1', code)
                self.assertIn('"-DCMAKE_MAKE_PROGRAM=$whp_llvm_ninja_cmd"', code)
                self.assertIn('"$whp_llvm_cmake_cmd" --build "$LLVM_BUILD_DIR"', code)
                self.assertIn("unset CMAKE_TOOLCHAIN_FILE CMAKE_GENERATOR", code)
                self.assertNotIn('cmake --build "$LLVM_BUILD_DIR"', code)

    def test_shared_toolchain_reuse_precedes_rebuild_only_tools(self):
        i386 = I386.read_text(encoding="utf-8")
        ppc = POWERPC.read_text(encoding="utf-8")
        self.assertLess(
            i386.index('usable "$TOOLCHAIN_DIR"; then'),
            i386.index("whp_llvm_select_cmake_ninja || exit 1"),
        )
        self.assertLess(
            ppc.index('clang_toolchain_is_usable "$TOOLCHAIN_DIR"; then'),
            ppc.index("whp_llvm_select_cmake_ninja || exit 1"),
        )


if __name__ == "__main__":
    unittest.main()
