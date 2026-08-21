#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
LLVM_SUBMODULE_PATH="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SUBMODULE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
BASE_BOOTSTRAP="$SCRIPT_DIR/bootstrap-powerpc-clang-base.sh"
TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
config_shell="${CONFIG_SHELL:-/bin/bash}"

if [[ ! -x "$config_shell" ]]; then
    printf 'error: PowerPC toolchain CONFIG_SHELL is not executable: %s\n' \
        "$config_shell" >&2
    exit 1
fi
case "$TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac

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

# The compiler foundation intentionally owns no public assembler command. Clear
# the downstream LLVM-MC interface before base validation, then republish it
# after LLD. This lets the base keep rejecting stale GNU-as installations
# without forcing a full compiler rebuild on every subsequent toolchain run.
rm -f "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"
rm -f "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/as"
rm -f "$TOOLCHAIN_DIR/.whp-powerpc-as"

# Reuse the already-pinned LLVM submodule as the compiler source cache.  This
# avoids asking a local Git repository for partial-clone filtering before the
# established Clang + LLD bootstrap validates and builds that exact revision.
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-source-cache.sh"

llvm_revision="$(
    git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH" | awk '{print $3}'
)"
if [[ -z "$llvm_revision" ]]; then
    printf 'error: LLVM submodule is not registered in QEMU: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi

# The base bootstrap owns its semantic marker and the persistent CMake/Ninja
# graph. Never turn script-checksum drift into a clean rebuild here: semantic
# input changes should reconfigure incrementally, while only an explicit
# POWERPC_TOOLCHAIN_FORCE_REBUILD=1 may erase compiled LLVM outputs.
"${toolchain_clean_env[@]}" \
    POWERPC_LLVM_GIT_URL="$LLVM_SUBMODULE_DIR" \
    POWERPC_LLVM_GIT_REF="$llvm_revision" \
    POWERPC_LLVM_GIT_COMMIT="$llvm_revision" \
    POWERPC_LLVM_GIT_OFFLINE=0 \
    POWERPC_LLVM_SOURCE_DIR="$TOOLCHAIN_WORK_DIR/llvm-source-from-submodule" \
    POWERPC_TOOLCHAIN_FORCE_REBUILD="$TOOLCHAIN_FORCE_REBUILD" \
    bash "$BASE_BOOTSTRAP"

# llvm-ar and llvm-ranlib are LLVM core tools, so qualify and publish them
# immediately after the base compiler install. bootstrap-powerpc-clang-core.sh
# then consumes the LLVM-backed archive route while proving LLD.
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-ar.sh"

# The base foundation has already been validated above.  Do not force it a
# second time inside the LLD stage: a redundant forced rebuild would replace
# the freshly-published archive entry points before the LLD smoke runs.
"${toolchain_clean_env[@]}" \
    POWERPC_TOOLCHAIN_FORCE_REBUILD=0 \
    bash "$SCRIPT_DIR/bootstrap-powerpc-clang-core.sh"

# Publish assembly as its own LLVM-backed interface after the compiler and LLD
# foundations are proven. The implementation remains Clang's integrated LLVM-MC
# assembler; GNU as is neither built nor retained as a fallback.
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-mc.sh"

# llvm-readelf is consumed directly and objcopy/objdump are not yet public
# interfaces in this lane. Remove entry points left by older toolchain caches.
for tool in objcopy objdump readelf; do
    rm -f "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-${tool}"
    rm -f "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/$tool"
done

# Publish the remaining migrated binary-tool interfaces after LLD and the
# assembler are proven. nm deliberately consumes the already-published LLVM ar
# route for its archive-map qualification. No private GNU binary-tool fallback
# survives.
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-nm.sh"
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-strip.sh"
