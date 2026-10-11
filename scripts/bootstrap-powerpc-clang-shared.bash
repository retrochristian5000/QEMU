#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Reuse the already-built native LLVM for PowerPC firmware. No CMake/Ninja LLVM
# compilation, source cloning, or changes to the shared LLVM prefix take place.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
LLVM_SUBMODULE_PATH="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
SHARED_LLVM_DIR="${WHP_SHARED_LLVM_DIR:-${NATIVE_LLVM_DIR:-}}"

[[ "$TOOLCHAIN_TARGET" == powerpc-elf ]] || {
    printf 'error: shared LLVM firmware supports only powerpc-elf\n' >&2
    exit 1
}
[[ -n "$SHARED_LLVM_DIR" && -d "$SHARED_LLVM_DIR" ]] || {
    printf 'error: native LLVM directory not available for PowerPC sharing\n' >&2
    exit 1
}
SHARED_LLVM_DIR="$(cd -- "$SHARED_LLVM_DIR" && pwd -P)"
case "$TOOLCHAIN_DIR" in
    /*) ;;
    *) TOOLCHAIN_DIR="$PWD/$TOOLCHAIN_DIR" ;;
esac
case "$TOOLCHAIN_WORK_DIR" in
    /*) ;;
    *) TOOLCHAIN_WORK_DIR="$PWD/$TOOLCHAIN_WORK_DIR" ;;
esac
case "$TOOLCHAIN_DIR/" in
    "$SHARED_LLVM_DIR/"*)
        printf 'error: PowerPC prefix must not be inside shared LLVM\n' >&2
        exit 1
        ;;
esac
if [[ -d "$TOOLCHAIN_DIR" ]]; then
    prefix_real="$(cd -- "$TOOLCHAIN_DIR" && pwd -P)"
    case "$prefix_real/" in
        "$SHARED_LLVM_DIR/"*)
            printf 'error: PowerPC prefix resolves inside shared LLVM\n' >&2
            exit 1
            ;;
    esac
    [[ "$prefix_real" != "$SHARED_LLVM_DIR" ]] || {
        printf 'error: PowerPC prefix resolves to shared LLVM\n' >&2
        exit 1
    }
fi
case "$SHARED_LLVM_DIR/" in
    "$TOOLCHAIN_DIR/"*)
        printf 'error: shared LLVM must not reside inside the PowerPC prefix\n' >&2
        exit 1
        ;;
esac

# The pinned LLVM gitlink is the only accepted revision; no unrelated Clang
# found on PATH is allowed to impersonate the shared bootstrap.
expected_revision="$(git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH" | awk '{print $3}')"
llvm_source="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
[[ -n "$expected_revision" && -f "$llvm_source/llvm/CMakeLists.txt" ]] || {
    printf 'error: pinned LLVM submodule is absent\n' >&2
    exit 1
}
llvm_revision="$(git -C "$llvm_source" rev-parse HEAD)"
[[ "$llvm_revision" == "$expected_revision" ]] || {
    printf 'error: LLVM checkout does not match the QEMU gitlink\n' >&2
    exit 1
}
if [[ -n "$(git -C "$llvm_source" status --porcelain --untracked-files=no)" ]]; then
    printf 'error: tracked LLVM submodule changes must be committed first\n' >&2
    exit 1
fi

native_marker="$SHARED_LLVM_DIR/.whp-native-llvm"
[[ -f "$native_marker" ]] &&
    grep -Fxq "LLVM_GIT_COMMIT=$llvm_revision" "$native_marker" &&
    grep -Fxq 'LLVM_TARGETS_TO_BUILD=AArch64;X86;PowerPC' "$native_marker" &&
    grep -Fxq 'LLD_ENABLE_BACKENDS=ELF;COFF;MinGW;MachO' "$native_marker" || {
        printf 'error: native LLVM revision or PowerPC/ELF capabilities mismatch\n' >&2
        exit 1
    }

for name in clang ld.lld llvm-ar llvm-ranlib llvm-nm llvm-readelf \
            llvm-strip llvm-config llvm-tblgen; do
    [[ -x "$SHARED_LLVM_DIR/bin/$name" ]] || {
        printf 'error: shared LLVM tool missing: %s\n' "$name" >&2
        exit 1
    }
done
[[ -f "$SHARED_LLVM_DIR/lib/cmake/llvm/LLVMConfig.cmake" ]] || {
    printf 'error: shared LLVM is missing CMake export metadata\n' >&2
    exit 1
}
targets="$("$SHARED_LLVM_DIR/bin/clang" --print-targets)"
grep -Eq '(^|[[:space:]])ppc32([[:space:]]|$)' <<< "$targets" || {
    printf 'error: shared LLVM is missing PowerPC32 code generation\n' >&2
    exit 1
}

expected_marker="$(cat <<MARKER
BOOTSTRAP_SCHEMA=1
COMPILER=clang
ASSEMBLER=clang-integrated
GNU_BINUTILS=disabled
SFRAME=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_GIT_COMMIT=$llvm_revision
LLVM_EXECUTABLE_SOURCE=shared:$SHARED_LLVM_DIR
MARKER
)"
expected_lld_marker="$(cat <<MARKER
LLD_SCHEMA=shared-1
LINKER=lld
ASSEMBLER=clang-integrated
GNU_BINUTILS=disabled
SFRAME=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_GIT_COMMIT=$llvm_revision
LLVM_EXECUTABLE_SOURCE=shared:$SHARED_LLVM_DIR
LLD_BACKENDS=ELF;COFF;MinGW;MachO
MARKER
)"

# A previous standalone PowerPC prefix must never be treated as a shared
# installation just because it happens to have a working Clang executable.
current=0
if [[ "${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}" == 0 &&
      -f "$TOOLCHAIN_DIR/.whp-powerpc-toolchain" &&
      -f "$TOOLCHAIN_DIR/.whp-powerpc-lld" &&
      "$(cat "$TOOLCHAIN_DIR/.whp-powerpc-toolchain")" == "$expected_marker" &&
      "$(cat "$TOOLCHAIN_DIR/.whp-powerpc-lld")" == "$expected_lld_marker" &&
      "$(readlink "$TOOLCHAIN_DIR/llvm" 2>/dev/null)" == "$SHARED_LLVM_DIR" &&
      -x "$TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-gcc" &&
      -x "$TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-ld" ]]; then
    current=1
fi

staging_root=""
old_toolchain=""
old_moved=0
published=0
smoke=""
cleanup()
{
    local status=$?
    trap - EXIT
    if ((status != 0)); then
        if ((published == 1)); then
            rm -rf "$TOOLCHAIN_DIR"
        fi
        if ((old_moved == 1)) &&
           [[ -n "$old_toolchain" && ( -e "$old_toolchain" || -L "$old_toolchain" ) ]]; then
            mv "$old_toolchain" "$TOOLCHAIN_DIR"
        fi
    fi
    [[ -z "$staging_root" ]] || rm -rf "$staging_root"
    [[ -z "$smoke" ]] || rm -rf "$smoke"
    if ((status == 0)) && [[ -n "$old_toolchain" ]]; then
        rm -rf "$old_toolchain"
    fi
    exit "$status"
}
trap cleanup EXIT

if ((current == 0)); then
    mkdir -p "$(dirname "$TOOLCHAIN_DIR")" "$TOOLCHAIN_WORK_DIR"
    staging_root="$TOOLCHAIN_WORK_DIR/shared-llvm-install.$$"
    staged_toolchain="$staging_root$TOOLCHAIN_DIR"
    mkdir -p "$staged_toolchain/bin" \
             "$staged_toolchain/$TOOLCHAIN_TARGET/bin" \
             "$staged_toolchain/$TOOLCHAIN_TARGET/sys-root" \
             "$staged_toolchain/libexec/powerpc-clang-gnu"
    ln -s "$SHARED_LLVM_DIR" "$staged_toolchain/llvm"
    cp "$SCRIPT_DIR/whp-build/powerpc-clang-driver.bash" \
        "$staged_toolchain/bin/$TOOLCHAIN_TARGET-gcc"
    chmod +x "$staged_toolchain/bin/$TOOLCHAIN_TARGET-gcc"
    ln -s ../llvm/bin/ld.lld "$staged_toolchain/bin/$TOOLCHAIN_TARGET-ld"
    ln -s "../../bin/$TOOLCHAIN_TARGET-ld" \
        "$staged_toolchain/$TOOLCHAIN_TARGET/bin/ld"
    ln -s ../../llvm/bin/ld.lld \
        "$staged_toolchain/libexec/powerpc-clang-gnu/ld"

    printf '%s\n' "$expected_marker" > "$staged_toolchain/.whp-powerpc-toolchain"
    printf '%s\n' "$expected_lld_marker" > "$staged_toolchain/.whp-powerpc-lld"
    toolchain="$staged_toolchain"
else
    toolchain="$TOOLCHAIN_DIR"
fi

# Exercise a real firmware-target object and a freestanding link before
# publishing the wrappers. This also verifies resource headers and endianness.
mkdir -p "$TOOLCHAIN_WORK_DIR"
smoke="$TOOLCHAIN_WORK_DIR/shared-llvm-smoke.$$"
mkdir -p "$smoke"
cat > "$smoke/smoke.c" <<'SOURCE'
#include <stddef.h>
#include <stdarg.h>
#if !defined(__powerpc__) && !defined(__POWERPC__) && !defined(__PPC__)
#error PowerPC predefine missing
#endif
#if __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
#error PowerPC ELF should be big endian
#endif
_Static_assert(sizeof(void *) == 4, "expected PPC32 ABI");
size_t whp_shared_ppc_size(void) { return sizeof(size_t) + sizeof(va_list); }
int _entry(void) { return 0; }
SOURCE
cat > "$smoke/layout.ld" <<'LDSCRIPT'
OUTPUT_FORMAT(elf32-powerpc)
OUTPUT_ARCH(powerpc:common)
ENTRY(_entry)
SECTIONS {
    . = 0xfff00000;
    .text : { *(.text) *(.text.*) }
    .rodata : { *(.rodata) *(.rodata.*) }
    .data : { *(.data) *(.data.*) }
    .bss : { *(.bss) *(COMMON) }
    /DISCARD/ : { *(.comment*) *(.note.*) }
}
LDSCRIPT
"$toolchain/bin/$TOOLCHAIN_TARGET-gcc" -m32 -mcpu=604 -msoft-float \
    -mcall-sysv-noeabi -msdata=none -G0 -ffreestanding -fno-pic -fno-pie \
    -fno-omit-frame-pointer -momit-leaf-frame-pointer \
    -c "$smoke/smoke.c" -o "$smoke/smoke.o"
"$toolchain/bin/$TOOLCHAIN_TARGET-ld" --warn-common -z noexecstack \
    -T "$smoke/layout.ld" -o "$smoke/smoke.elf" "$smoke/smoke.o"
header="$(LC_ALL=C "$toolchain/llvm/bin/llvm-readelf" -hW "$smoke/smoke.elf")"
for pattern in 'Class:[[:space:]]+ELF32' \
               "Data:[[:space:]]+2's complement, big endian" \
               'Machine:[[:space:]]+PowerPC' \
               'Entry point address:[[:space:]]+0xfff00000'; do
    grep -Eq "$pattern" <<< "$header" || {
        printf 'error: shared PowerPC LLVM failed ELF layout smoke: %s\n' \
            "$pattern" >&2
        exit 1
    }
done
linker="$("$toolchain/bin/$TOOLCHAIN_TARGET-gcc" -print-prog-name=ld)"
[[ "$linker" == "$toolchain/libexec/powerpc-clang-gnu/ld" ]] || {
    printf 'error: shared Clang does not select its private LLD interface\n' >&2
    exit 1
}
rm -rf "$smoke"
smoke=""

if ((current == 0)); then
    old_toolchain="$TOOLCHAIN_DIR.old.$$"
    if [[ -e "$TOOLCHAIN_DIR" || -L "$TOOLCHAIN_DIR" ]]; then
        mv "$TOOLCHAIN_DIR" "$old_toolchain"
        old_moved=1
    fi
    mv "$staged_toolchain" "$TOOLCHAIN_DIR"
    published=1
fi

# Retain the original qualified target-specific archive, assembler, symbol,
# and strip interfaces and their ABI smokes. They use the shared executables.
for phase in llvm-ar llvm-mc llvm-nm llvm-strip; do
    bash "$SCRIPT_DIR/bootstrap-powerpc-$phase.sh"
done
for obsolete in objcopy objdump readelf; do
    rm -f "$TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-$obsolete" \
          "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/$obsolete"
done
printf 'PowerPC firmware reuses native LLVM: %s\n' "$SHARED_LLVM_DIR"
printf 'PowerPC compatibility prefix: %s/bin/%s-\n' \
    "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
