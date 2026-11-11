#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
build="$ROOT/build.sh"
native="$ROOT/scripts/bootstrap-native-clang.bash"
i386="$ROOT/scripts/bootstrap-i386-clang.bash"
powerpc="$ROOT/scripts/bootstrap-powerpc-clang.bash"
powerpc_base="$ROOT/scripts/bootstrap-powerpc-clang-base.bash"
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

# Public host identification precedes the bootstrap dependencies and is
# consumed by Bash and portable Python without taking a new reading.
python3 - "$build" "$ROOT/scripts/whp-build/prepare-build.bash" \
    "$ROOT/scripts/whp-build/portable-build.py" <<'PY'
import pathlib
import sys
entry, bash, portable = [pathlib.Path(p).read_text() for p in sys.argv[1:]]
if entry.index('WHP_HOST_KERNEL=$(uname -s') >= entry.index('whp_python_usable()'):
    raise SystemExit('error: host reading occurs after Python discovery')
if entry.count('$(uname -s') != 1 or entry.count('$(uname -m') != 1:
    raise SystemExit('error: public build reads uname more than once')
if entry.count('case "$WHP_HOST_OS" in') < 3:
    raise SystemExit('error: early bootstrap bypasses normalized host OS')
if 'HOST_OS="${WHP_HOST_KERNEL:-$(uname -s)}"' not in bash:
    raise SystemExit('error: Bash stage ignores public kernel')
if 'PROCESS_ARCH="${WHP_HOST_ARCH:-$(uname -m)}"' not in bash:
    raise SystemExit('error: Bash stage ignores public architecture')
if "os.environ.get('WHP_HOST_KERNEL')" not in portable:
    raise SystemExit('error: portable Python ignores public kernel')
if "os.environ.get('WHP_HOST_ARCH')" not in portable:
    raise SystemExit('error: portable Python ignores public architecture')
PY

for host_os in macos linux windows; do
    grep -Fq "WHP_HOST_OS=$host_os" "$build" || {
        printf 'error: build entry does not normalize host OS %s\n' "$host_os" >&2
        exit 1
    }
done
grep -Fq 'export WHP_HOST_OS WHP_HOST_KERNEL WHP_HOST_ARCH' "$build" || {
    printf 'error: normalized host identity is not exported by build.sh\n' >&2
    exit 1
}
grep -Fq 'WHP host: %s (%s/%s)' "$build" || {
    printf 'error: build.sh does not report the detected host to the user\n' >&2
    exit 1
}
grep -Fq 'host_os="${WHP_HOST_OS:-}"' "$native" || {
    printf 'error: native LLVM redetects the OS instead of consuming build host policy\n' >&2
    exit 1
}

# Every LLVM host executable build on macOS must opt in to CMake's positive
# SDK selection. The compiler's target (PowerPC/i386) is not the host SDK.
grep -Fq -- '-DLLVM_MACOS_HOST_SDK_RESOLVE=ON' "$native" || {
    printf 'error: native LLVM does not request CMake host SDK resolution\n' >&2
    exit 1
}
grep -Fq -- '-DLLVM_MACOS_HOST_SDK_RESOLVE=ON' "$powerpc_base" || {
    printf 'error: PowerPC LLVM does not request CMake host SDK resolution\n' >&2
    exit 1
}
grep -Fq -- '-DLLVM_MACOS_HOST_SDK_RESOLVE=ON' "$i386" || {
    printf 'error: i386 LLVM does not request CMake host SDK resolution\n' >&2
    exit 1
}
grep -Fq '"-DCMAKE_OSX_SYSROOT=$i386_host_sdk"' "$i386" || {
    printf 'error: i386 LLVM can reuse a stale CMake SDK cache entry\n' >&2
    exit 1
}
grep -Fq 'sdkroot="$sdk_real_path"' "$native" || {
    printf 'error: native LLVM builtins/runtimes do not use the canonical SDK\n' >&2
    exit 1
}
grep -Fq 'SDKROOT="$sdk_real_path"' "$powerpc_base" || {
    printf 'error: PowerPC LLVM does not propagate its canonical SDK\n' >&2
    exit 1
}

# The standalone PowerPC LLVM bootstrap can be called without macos-builder.
# It must independently keep iPad/iPhone/simulator headers out of native tools.
for required in \
    'MacOSX*.sdk) ;;' \
    'WHP_LLVM_MACOS_SDK' \
    'WHP_LLVM_MACOS_CXX_SDK' \
    '#include <TargetConditionals.h>' \
    '#include <memory>' \
    '"-DCMAKE_OSX_SYSROOT=$SDKROOT"'; do
    if ! grep -Fq "$required" "$powerpc_base"; then
        printf 'error: missing standalone LLVM macOS SDK guard: %s\n' \
            "$required" >&2
        exit 1
    fi
done

for script in "$native" "$i386"; do
    grep -Fq 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS' "$script" || {
        printf 'error: LLVM bootstrap inherits QEMU host flags: %s\n' "$script" >&2
        exit 1
    }
done

grep -Fq '"$prefix/bin/clang" -fno-omit-frame-pointer -momit-leaf-frame-pointer \' "$native" || {
    printf 'error: native LLVM cache check does not exercise non-leaf frame-pointer IR\n' >&2
    exit 1
}

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

for header in stddef.h stdarg.h; do
    grep -Fq "#include <$header>" "$i386" || {
        printf 'error: i386 LLVM cache does not exercise resource header %s\n' \
            "$header" >&2
        exit 1
    }
done
grep -Fq -- '-fno-omit-frame-pointer -momit-leaf-frame-pointer \' "$i386" || {
    printf 'error: i386 LLVM cache does not exercise non-leaf frame-pointer IR\n' >&2
    exit 1
}
for tool in as ld objcopy objdump strip; do
    grep -Fq '"$prefix/bin/$TOOLCHAIN_TARGET-'"$tool"'"' "$i386" || {
        printf 'error: i386 LLVM cache health gate omits %s semantics\n' "$tool" >&2
        exit 1
    }
done
grep -Fq '"$i386_ld" -r "$cache_smoke_dir/cache.o" "$cache_smoke_dir/cache-asm.o"' "$i386" || {
    printf 'error: i386 LLVM cache does not exercise LLD relocatable linking\n' >&2
    exit 1
}
grep -Fq '"$i386_objdump" -f "$cache_smoke_dir/cache-linked.o"' "$i386" || {
    printf 'error: i386 LLVM cache does not inspect linked ELF output\n' >&2
    exit 1
}
grep -Fq '"$i386_objcopy" "$cache_smoke_dir/cache-linked.o" \' "$i386" || {
    printf 'error: i386 LLVM cache does not exercise objcopy\n' >&2
    exit 1
}
grep -Fq '"$i386_strip" -o "$cache_smoke_dir/cache-stripped.o" \' "$i386" || {
    printf 'error: i386 LLVM cache does not exercise strip\n' >&2
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

grep -Fq 'POWERPC_LLVM_BUILD_DIR="$TOOLCHAIN_WORK_DIR/llvm-build/$llvm_revision"' "$powerpc" || {
    printf 'error: PowerPC LLVM build graph is not revision-isolated\n' >&2
    exit 1
}

printf 'LLVM bootstrap environment isolation: verified\n'
