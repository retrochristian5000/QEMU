#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Keep x86-only ISA tuning out of native LLVM's non-x86 host tools.

The LLVM toolchain builds AArch64, X86 and PowerPC backends in one *host*
executable set. Backend selection does not authorize x86 host compiler flags.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
bootstrap = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(
    encoding="utf-8"
)
meson = (ROOT / "meson.build").read_text(encoding="utf-8")

subprocess.run(
    ["bash", "-n", str(ROOT / "scripts/bootstrap-native-clang.bash")],
    check=True,
)

# The only QEMU host -msse4.2 selection is scoped to an x86_64 host;
# it is not a request to compile the LLVM AArch64/PowerPC backends with SSE.
begin = meson.index("if host_arch == 'x86_64'")
end = meson.index("\nendif", begin)
assert meson.count("-msse4.2") == 1
assert "-msse4.2" in meson[begin:end]

# Native LLVM must retain independently controlled C/C++/ASM flag lanes.
assert "LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'" in bootstrap
assert "unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS ASMFLAGS" in bootstrap
assert "llvm_bootstrap_cflags='-O2 -DNDEBUG'" in bootstrap
assert "llvm_bootstrap_cxxflags='-O2 -DNDEBUG'" in bootstrap
for flag in (
    "-DCMAKE_C_FLAGS=",
    "-DCMAKE_CXX_FLAGS=",
    "-DCMAKE_ASM_FLAGS=",
    "-DCMAKE_ASM_FLAGS_RELEASE=",
):
    assert "    " + flag + "\n" in bootstrap, flag
assert (
    "CMAKE_C_FLAGS=\n"
    "CMAKE_CXX_FLAGS=\n"
    "CMAKE_ASM_FLAGS=\n"
    "CMAKE_ASM_FLAGS_RELEASE=\n"
) in bootstrap
assert "-DCMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags" in bootstrap
assert "-DCMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags" in bootstrap
assert "CMAKE_ASM_FLAGS_RELEASE=-msse4.2" not in bootstrap

# Verify the CMake-cache exposure and the repair independently of LLVM's
# very large build. Neither phase compiles foreign-architecture objects.
if shutil.which("cmake") and shutil.which("ninja"):
    with tempfile.TemporaryDirectory(prefix="whp-llvm-isa-") as tmp:
        root = Path(tmp)
        source = root / "src"
        build = root / "build"
        source.mkdir()
        (source / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.18)\n"
            "project(ISAFlagBoundary LANGUAGES ASM)\n"
            "add_library(isa_probe OBJECT probe.S)\n",
            encoding="utf-8",
        )
        (source / "probe.S").write_text(".text\n", encoding="utf-8")
        env = os.environ.copy()
        for variable in ("CFLAGS", "CXXFLAGS", "CPPFLAGS", "ASMFLAGS"):
            env.pop(variable, None)

        base = ["cmake", "-S", str(source), "-B", str(build), "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release"]

        subprocess.run(
            [*base, "-DCMAKE_ASM_FLAGS=-msse4.2",
             "-DCMAKE_ASM_FLAGS_RELEASE=-msse4.2"],
            check=True, env=env, stdout=subprocess.DEVNULL,
        )
        assert "-msse4.2" in (build / "build.ninja").read_text(
            encoding="utf-8"
        ), "the poisoned ASM CMake cache was not reproduced"

        subprocess.run(
            [*base, "-DCMAKE_ASM_FLAGS=", "-DCMAKE_ASM_FLAGS_RELEASE="],
            check=True, env=env, stdout=subprocess.DEVNULL,
        )
        assert "-msse4.2" not in (build / "build.ninja").read_text(
            encoding="utf-8"
        ), "stale SSE4.2 compiler flags survived the CMake cache reset"

print("native LLVM cross-target ISA isolation tests: passed")
