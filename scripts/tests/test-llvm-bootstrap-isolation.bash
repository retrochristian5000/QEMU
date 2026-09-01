#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
native="$ROOT/scripts/bootstrap-native-clang.sh"
i386="$ROOT/scripts/bootstrap-i386-clang.sh"
powerpc="$ROOT/scripts/bootstrap-powerpc-clang.sh"
powerpc_base="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
seabios_config="$ROOT/scripts/whp-build/configure-seabios.bash"

for script in "$native" "$i386" "$powerpc" "$powerpc_base" "$seabios_config"; do
    [[ -f "$script" ]] || {
        printf 'error: missing LLVM bootstrap boundary: %s\n' "$script" >&2
        exit 1
    }
    bash -n "$script" || {
        printf 'error: LLVM bootstrap boundary has invalid shell syntax: %s\n' "$script" >&2
        exit 1
    }
done

# Native LLVM is invoked by build.sh before the normal QEMU host-flag cleanup,
# and the i386 bootstrap is invoked directly by the SeaBIOS preparation path.
# Both therefore own a local boundary against ambient host-object flags.
for script in "$native" "$i386"; do
    grep -Fq 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS' "$script" || {
        printf 'error: LLVM bootstrap inherits QEMU host flags: %s\n' "$script" >&2
        exit 1
    }
done

# PowerPC already enters its compiler stages through a dedicated clean env.
# Keep that single boundary instead of duplicating ad-hoc unsets in the base.
for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
    grep -Fq -- "-u $variable" "$powerpc" || {
        printf 'error: PowerPC LLVM clean environment retains %s\n' "$variable" >&2
        exit 1
    }
done

# Exercise the exact frontend -> IR verifier path implicated by the regression:
# keeping non-leaf frame pointers while omitting leaf frame pointers emits the
# modern "non-leaf-no-reserve" function attribute.
grep -Fq '"$prefix/bin/clang" -fno-omit-frame-pointer -momit-leaf-frame-pointer \' "$native" || {
    printf 'error: native LLVM cache check does not exercise non-leaf frame-pointer IR\n' >&2
    exit 1
}

# Native LLVM installs clang-resource-headers as a separate component and can
# be selected as QEMU's macOS host compiler. Its cache gate must therefore prove
# those headers are usable, not merely that a headerless frontend invocation
# succeeds.
for header in stddef.h stdarg.h; do
    grep -Fq "#include <$header>" "$native" || {
        printf 'error: native LLVM cache does not exercise resource header %s\n' \
            "$header" >&2
        exit 1
    }
done
grep -Fq 'size_t whp_native_llvm_resource_size' "$native" || {
    printf 'error: native LLVM resource-header smoke does not consume size_t\n' >&2
    exit 1
}

grep -Fq '"$i386_clang" --target=i386-none-elf -m32 -march=i386 \' "$seabios_config" || {
    printf 'error: SeaBIOS i386 cache check does not compile with installed clang\n' >&2
    exit 1
}
grep -Fq -- '-fno-omit-frame-pointer -momit-leaf-frame-pointer \' "$seabios_config" || {
    printf 'error: SeaBIOS i386 cache check does not exercise non-leaf frame-pointer IR\n' >&2
    exit 1
}
grep -Fq 'bootstrap_i386_toolchain 1' "$seabios_config" || {
    printf 'error: SeaBIOS i386 frame-pointer failure does not force a clean rebuild\n' >&2
    exit 1
}
grep -Fq '"$TOOLCHAIN_DIR/llvm/bin/clang" --target=powerpc-none-elf \' "$powerpc" || {
    printf 'error: PowerPC LLVM cache check does not compile with installed clang\n' >&2
    exit 1
}
grep -Fq -- '-fno-omit-frame-pointer -momit-leaf-frame-pointer \' "$powerpc" || {
    printf 'error: PowerPC LLVM cache check does not exercise non-leaf frame-pointer IR\n' >&2
    exit 1
}
grep -Fq 'TOOLCHAIN_FORCE_REBUILD=1' "$powerpc" || {
    printf 'error: PowerPC LLVM cache failure does not force a rebuild\n' >&2
    exit 1
}
grep -Fq 'rm -rf "$POWERPC_LLVM_BUILD_DIR"' "$powerpc" || {
    printf 'error: broken PowerPC LLVM module graph is not discarded before rebuild\n' >&2
    exit 1
}

# The frame-pointer failure proved that an installed compiler can look present
# while one LLVM module is stale. Guard the rest of the core distribution too:
# archive/index, symbol, ELF reader, strip, configuration, and TableGen tools
# must participate in the current-cache health gate instead of relying on
# markers or --version-only checks in later publication stages.
grep -Fq 'powerpc_llvm_cache_is_usable()' "$powerpc" || {
    printf 'error: PowerPC LLVM cache has no integrated core-module smoke\n' >&2
    exit 1
}
for tool in llvm-ar llvm-ranlib llvm-nm llvm-readelf llvm-strip llvm-config llvm-tblgen; do
    grep -Fq "\$TOOLCHAIN_DIR/llvm/bin/$tool" "$powerpc" || {
        printf 'error: PowerPC LLVM cache health gate omits %s\n' "$tool" >&2
        exit 1
    }
done
grep -Fq '"$llvm_ar" rcs "$cache_smoke_dir/libcache.a" "$cache_smoke_dir/cache.o"' "$powerpc" || {
    printf 'error: PowerPC LLVM cache does not exercise archive creation\n' >&2
    exit 1
}
grep -Fq '"$llvm_nm" --gnu-compatible -g "$cache_smoke_dir/cache.o"' "$powerpc" || {
    printf 'error: PowerPC LLVM cache does not exercise symbol inspection\n' >&2
    exit 1
}
grep -Fq '"$llvm_strip" "$cache_smoke_dir/cache.o" -o "$cache_smoke_dir/cache-stripped.o"' "$powerpc" || {
    printf 'error: PowerPC LLVM cache does not exercise object stripping\n' >&2
    exit 1
}

# clang-resource-headers is a separate installed distribution component. A
# headerless compiler smoke cannot detect a partial install where clang itself
# works but freestanding standard headers are missing or stale.
for header in stddef.h stdarg.h; do
    grep -Fq "#include <$header>" "$powerpc" || {
        printf 'error: PowerPC LLVM cache does not exercise resource header %s\n' \
            "$header" >&2
        exit 1
    }
done
grep -Fq 'size_t whp_powerpc_cache_size' "$powerpc" || {
    printf 'error: PowerPC LLVM resource-header smoke does not consume size_t\n' >&2
    exit 1
}

# Standalone LLD consumes the installed LLVM CMake package, not only the
# executables above. A stale LLVMConfig/exports graph can therefore break the
# macOS linker stage while clang and llvm-config still look healthy. Require a
# real CMake configure against that installed package before trusting the cache.
grep -Fq 'find_package(LLVM CONFIG REQUIRED)' "$powerpc" || {
    printf 'error: PowerPC LLVM cache does not validate installed CMake metadata\n' >&2
    exit 1
}
grep -Fq '"-DLLVM_DIR=$llvm_cmake_dir"' "$powerpc" || {
    printf 'error: PowerPC LLVM CMake metadata probe does not pin installed LLVM_DIR\n' >&2
    exit 1
}
grep -Fq 'cmake -S "$cache_cmake_source" -B "$cache_cmake_build"' "$powerpc" || {
    printf 'error: PowerPC LLVM cache does not configure a CMake package smoke\n' >&2
    exit 1
}

# A PowerPC compiler graph may be incremental within one LLVM revision, but it
# must not be reused after the gitlink changes. Key the build directory to the
# exact source revision selected by the QEMU tree.
grep -Fq 'POWERPC_LLVM_BUILD_DIR="$TOOLCHAIN_WORK_DIR/llvm-build/$llvm_revision"' "$powerpc" || {
    printf 'error: PowerPC LLVM build graph is not revision-isolated\n' >&2
    exit 1
}

printf 'LLVM bootstrap environment isolation: verified\n'
