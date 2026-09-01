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

# CMake/Ninja state is safe to reuse only while the LLVM source revision stays
# identical. A newer frontend may emit IR attributes that an older verifier in
# the retained object graph cannot understand, so make the gitlink part of the
# build-directory identity instead of mixing revisions in one graph.
POWERPC_LLVM_BUILD_DIR="$TOOLCHAIN_WORK_DIR/llvm-build/$llvm_revision"

powerpc_llvm_cache_is_usable()
{
    local clang="$TOOLCHAIN_DIR/llvm/bin/clang"
    local llvm_ar="$TOOLCHAIN_DIR/llvm/bin/llvm-ar"
    local llvm_ranlib="$TOOLCHAIN_DIR/llvm/bin/llvm-ranlib"
    local llvm_nm="$TOOLCHAIN_DIR/llvm/bin/llvm-nm"
    local llvm_readelf="$TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
    local llvm_strip="$TOOLCHAIN_DIR/llvm/bin/llvm-strip"
    local llvm_config="$TOOLCHAIN_DIR/llvm/bin/llvm-config"
    local llvm_tblgen="$TOOLCHAIN_DIR/llvm/bin/llvm-tblgen"
    local cache_smoke_dir="$TOOLCHAIN_WORK_DIR/llvm-cache-smoke"
    local header
    local nm_output
    local tool

    for tool in "$clang" "$llvm_ar" "$llvm_ranlib" "$llvm_nm" \
                "$llvm_readelf" "$llvm_strip" "$llvm_config" "$llvm_tblgen"; do
        [[ -x "$tool" ]] || return 1
    done

    rm -rf "$cache_smoke_dir"
    mkdir -p "$cache_smoke_dir"
    cat > "$cache_smoke_dir/cache.c" <<'SOURCE'
int whp_powerpc_cache_smoke(void) { return 0; }
SOURCE

    # Keep the original frame-pointer producer/verifier regression in the
    # broader health check, then reuse its real PowerPC object to exercise the
    # core LLVM tools that OpenBIOS consumes indirectly. Keep the literal
    # installed-Clang path visible so the original regression guard cannot be
    # accidentally weakened by a later refactor of this helper.
    if ! "$TOOLCHAIN_DIR/llvm/bin/clang" --target=powerpc-none-elf \
            -fno-omit-frame-pointer -momit-leaf-frame-pointer \
            -ffreestanding -O0 -c "$cache_smoke_dir/cache.c" \
            -o "$cache_smoke_dir/cache.o" >/dev/null 2>&1; then
        rm -rf "$cache_smoke_dir"
        return 1
    fi

    header="$(LC_ALL=C "$llvm_readelf" -hW "$cache_smoke_dir/cache.o" 2>/dev/null)" || {
        rm -rf "$cache_smoke_dir"
        return 1
    }
    if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$header" ||
       ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$header" ||
       ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$header"; then
        rm -rf "$cache_smoke_dir"
        return 1
    fi

    if ! "$llvm_ar" rcs "$cache_smoke_dir/libcache.a" "$cache_smoke_dir/cache.o" ||
       ! "$llvm_ranlib" "$cache_smoke_dir/libcache.a"; then
        rm -rf "$cache_smoke_dir"
        return 1
    fi
    if [[ "$("$llvm_ar" t "$cache_smoke_dir/libcache.a" 2>/dev/null)" != cache.o ]]; then
        rm -rf "$cache_smoke_dir"
        return 1
    fi

    nm_output="$("$llvm_nm" --gnu-compatible -g "$cache_smoke_dir/cache.o" 2>/dev/null)" || {
        rm -rf "$cache_smoke_dir"
        return 1
    }
    if ! grep -Fq 'whp_powerpc_cache_smoke' <<< "$nm_output"; then
        rm -rf "$cache_smoke_dir"
        return 1
    fi

    if ! "$llvm_strip" "$cache_smoke_dir/cache.o" -o "$cache_smoke_dir/cache-stripped.o" ||
       ! LC_ALL=C "$llvm_readelf" -hW "$cache_smoke_dir/cache-stripped.o" \
            >/dev/null 2>&1 ||
       ! "$llvm_config" --version >/dev/null 2>&1 ||
       ! "$llvm_tblgen" --version >/dev/null 2>&1; then
        rm -rf "$cache_smoke_dir"
        return 1
    fi

    rm -rf "$cache_smoke_dir"
    return 0
}

# A marker and matching gitlink are not enough to trust an already-installed
# LLVM distribution. A mixed object graph can leave one frontend/backend or
# utility module stale while every executable still exists and answers
# --version. Exercise the real PowerPC object path plus the core archive,
# symbol, ELF-reader, strip, config, and TableGen tools. If any part fails,
# discard the revision graph itself before rebuilding it from the pinned source.
if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 &&
      -x "$TOOLCHAIN_DIR/llvm/bin/clang" ]]; then
    if ! powerpc_llvm_cache_is_usable; then
        printf '%s\n' \
            'PowerPC LLVM cache failed the core module smoke; rebuilding.' >&2
        rm -rf "$POWERPC_LLVM_BUILD_DIR"
        TOOLCHAIN_FORCE_REBUILD=1
    fi
fi

# The base bootstrap owns its semantic marker. Script-checksum drift still does
# not force a clean rebuild; revision changes naturally select a fresh graph.
"${toolchain_clean_env[@]}" \
    POWERPC_LLVM_GIT_URL="$LLVM_SUBMODULE_DIR" \
    POWERPC_LLVM_GIT_REF="$llvm_revision" \
    POWERPC_LLVM_GIT_COMMIT="$llvm_revision" \
    POWERPC_LLVM_GIT_OFFLINE=0 \
    POWERPC_LLVM_SOURCE_DIR="$TOOLCHAIN_WORK_DIR/llvm-source-from-submodule" \
    POWERPC_LLVM_BUILD_DIR="$POWERPC_LLVM_BUILD_DIR" \
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
    POWERPC_LLVM_BUILD_DIR="$POWERPC_LLVM_BUILD_DIR" \
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
# assembler are proven. nm deliberately consumes the already-published LLVM ar.
# No private GNU as/ar/nm/strip fallbacks survive
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-nm.sh"
"${toolchain_clean_env[@]}" \
    bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-strip.sh"
