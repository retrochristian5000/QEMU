#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
lld_cmake="$ROOT/toolchains/llvm-project/lld/CMakeLists.txt"

# The persistent standalone LLD cache must be actively normalized to LLVM's
# lib layout rather than retaining a build-machine GNUInstallDirs default.
grep -Fq -- '-DCMAKE_INSTALL_LIBDIR=lib' "$core"

# The LLVM source itself must import LLVM's libdir policy before GNUInstallDirs
# is allowed to derive/cache a host default.
grep -Fq 'find_package(LLVM REQUIRED HINTS "${LLVM_CMAKE_DIR}")' "$lld_cmake"
grep -Fq 'LLVMInstallDirs.cmake' "$lld_cmake"

printf 'PowerPC CMake libdir policy: verified\n'
