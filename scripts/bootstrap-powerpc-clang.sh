#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
config_shell="${CONFIG_SHELL:-/bin/bash}"

if [[ ! -x "$config_shell" ]]; then
    printf 'error: PowerPC toolchain CONFIG_SHELL is not executable: %s\n' \
        "$config_shell" >&2
    exit 1
fi

# Keep QEMU, Homebrew, or an earlier cross-toolchain from selecting host or
# target binary utilities implicitly while the PowerPC toolchain bootstraps.
toolchain_clean_env=(
    env
    -u CC -u CXX -u OBJC
    -u AR -u AS -u LD -u NM -u OBJCOPY -u OBJDUMP -u RANLIB -u READELF -u STRIP
    -u CC_FOR_TARGET -u CXX_FOR_TARGET -u GCC_FOR_TARGET -u GXX_FOR_TARGET
    -u AR_FOR_TARGET -u AS_FOR_TARGET -u LD_FOR_TARGET -u NM_FOR_TARGET
    -u OBJCOPY_FOR_TARGET -u OBJDUMP_FOR_TARGET -u RANLIB_FOR_TARGET
    -u READELF_FOR_TARGET -u STRIP_FOR_TARGET
    -u CFLAGS -u CXXFLAGS -u OBJCFLAGS -u CPPFLAGS -u LDFLAGS
    -u CFLAGS_FOR_TARGET -u CXXFLAGS_FOR_TARGET
    -u CPPFLAGS_FOR_TARGET -u LDFLAGS_FOR_TARGET
    -u CPATH -u C_INCLUDE_PATH -u CPLUS_INCLUDE_PATH -u OBJC_INCLUDE_PATH
    -u COMPILER_PATH -u GCC_EXEC_PREFIX -u LIBRARY_PATH
    -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH -u DYLD_FALLBACK_LIBRARY_PATH
    -u DYLD_INSERT_LIBRARIES
    -u PKG_CONFIG_PATH -u PKG_CONFIG_LIBDIR -u PKG_CONFIG_SYSROOT_DIR
    -u CMAKE_PREFIX_PATH -u CMAKE_LIBRARY_PATH -u CMAKE_INCLUDE_PATH
    -u ACLOCAL_PATH -u ARCHFLAGS
    CONFIG_SHELL="$config_shell"
    SHELL="$config_shell"
)

# Reuse the already-pinned LLVM submodule as the compiler source cache.  This
# avoids asking a local Git repository for partial-clone filtering before the
# established Clang + LLD bootstrap validates and builds that exact revision.
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-source-cache.sh"

# Build the Clang foundation with GNU GAS disabled, migrate the public linker
# to LLD, publish GNU-compatible assembler and strip entry points backed only
# by LLVM, and leave no private GNU as/strip fallbacks behind.
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-clang-core.sh"
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-as.sh"
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-strip.sh"
