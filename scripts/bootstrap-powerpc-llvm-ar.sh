#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
LLVM_SUBMODULE_PATH="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SUBMODULE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"

case "$TOOLCHAIN_TARGET" in
    powerpc-elf) ;;
    *)
        printf 'error: the LLVM ar lane currently supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac

for required in git awk grep cksum cmp ln mkdir rm readlink; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: LLVM ar migration dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done

expected_llvm_revision="$(
    git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH" | awk '{print $3}'
)"
if [[ -z "$expected_llvm_revision" ]]; then
    printf 'error: LLVM submodule is not registered in QEMU: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi
if [[ ! -f "$LLVM_SUBMODULE_DIR/llvm/CMakeLists.txt" ]]; then
    printf 'error: LLVM submodule is not initialized: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi
llvm_revision="$(git -C "$LLVM_SUBMODULE_DIR" rev-parse HEAD)"
if [[ "$llvm_revision" != "$expected_llvm_revision" ]]; then
    printf '%s\n' \
        'error: LLVM checkout does not match the QEMU submodule pointer.' \
        "checked out: $llvm_revision" \
        "QEMU expects: $expected_llvm_revision" >&2
    exit 1
fi

clang="$TOOLCHAIN_DIR/llvm/bin/clang"
llvm_ar="$TOOLCHAIN_DIR/llvm/bin/llvm-ar"
llvm_nm="$TOOLCHAIN_DIR/llvm/bin/llvm-nm"
llvm_readelf="$TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
public_ar="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar"
target_ar="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/ar"
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
ar_marker="$TOOLCHAIN_DIR/.whp-powerpc-ar"
ar_signature="$(cksum "${BASH_SOURCE[0]}" | awk '{print $1 ":" $2}')"
expected_ar_marker="$(cat <<MARKER
AR_SCHEMA=2
AR=llvm-ar
GNU_AR=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
AR_BOOTSTRAP_SIGNATURE=$ar_signature
MARKER
)"

llvm_ar_toolchain_is_usable()
{
    [[ -x "$clang" ]] || return 1
    [[ -x "$llvm_ar" ]] || return 1
    [[ -x "$public_ar" ]] || return 1
    [[ -e "$target_ar" ]] || return 1
    [[ ! -e "$shim_dir/ar" ]] || return 1
    [[ ! -e "$shim_dir/ar.bfd" ]] || return 1
    [[ "$(readlink "$public_ar")" == "../llvm/bin/llvm-ar" ]] || return 1
    [[ "$(readlink "$target_ar")" == "../../bin/${TOOLCHAIN_TARGET}-ar" ]] || return 1
    "$llvm_ar" --version 2>/dev/null | grep -q 'LLVM' || return 1
    "$public_ar" --version 2>/dev/null | grep -q 'LLVM' || return 1
    "$target_ar" --version 2>/dev/null | grep -q 'LLVM' || return 1
}

if [[ -f "$ar_marker" &&
      "$(cat "$ar_marker")" == "$expected_ar_marker" ]] &&
   llvm_ar_toolchain_is_usable; then
    printf 'PowerPC LLVM ar stage is current: %s\n' "$public_ar"
    exit 0
fi

for required_tool in "$clang" "$llvm_ar" "$llvm_nm" "$llvm_readelf"; do
    if [[ ! -x "$required_tool" ]]; then
        printf 'error: LLVM ar migration prerequisite is missing: %s\n' \
            "$required_tool" >&2
        exit 1
    fi
done
if ! "$llvm_ar" --version 2>/dev/null | grep -q 'LLVM'; then
    printf 'error: installed LLVM archiver is invalid: %s\n' "$llvm_ar" >&2
    exit 1
fi
if ! "$llvm_nm" --help 2>/dev/null | grep -q -- '--gnu-compatible'; then
    printf 'error: LLVM ar qualification requires GNU-compatible llvm-nm\n' >&2
    exit 1
fi

# Qualify llvm-ar before the LLD bootstrap so the linker stage itself never
# needs GNU ar. Generate a real ELF32 big-endian PowerPC object with Clang IAS,
# require a GNU-style archive symbol index, verify member enumeration and byte
# preservation, then publish llvm-ar. bootstrap-powerpc-clang-core.sh runs next
# and consumes this published archive route in its existing LLD archive smoke.
smoke_dir="$TOOLCHAIN_WORK_DIR/llvm-ar-openbios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/archive.s" <<'ASSEMBLY'
.text
.globl whp_llvm_ar_smoke
whp_llvm_ar_smoke:
    nop
.globl whp_llvm_ar_second
whp_llvm_ar_second:
    blr
ASSEMBLY
"$clang" --target=powerpc-none-elf -c -x assembler \
    "$smoke_dir/archive.s" -o "$smoke_dir/archive.o"

object_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/archive.o")"
if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$object_header" ||
   ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$object_header" ||
   ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$object_header"; then
    printf 'error: LLVM ar smoke input is not the expected PowerPC ELF object\n' >&2
    exit 1
fi

"$llvm_ar" rcs "$smoke_dir/libarchive.a" "$smoke_dir/archive.o"
member_list="$("$llvm_ar" t "$smoke_dir/libarchive.a")"
if [[ "$member_list" != "archive.o" ]]; then
    printf 'error: llvm-ar did not preserve the expected archive member name\n' >&2
    printf 'members: %s\n' "$member_list" >&2
    exit 1
fi

armap_output="$("$llvm_nm" --gnu-compatible -s "$smoke_dir/libarchive.a")"
if ! grep -Fq 'Archive map' <<< "$armap_output" ||
   ! grep -Fq 'whp_llvm_ar_smoke in archive.o' <<< "$armap_output"; then
    printf 'error: llvm-ar did not create a usable GNU-style archive index\n' >&2
    exit 1
fi

"$llvm_ar" p "$smoke_dir/libarchive.a" archive.o > "$smoke_dir/extracted.o"
if ! cmp -s "$smoke_dir/archive.o" "$smoke_dir/extracted.o"; then
    printf 'error: llvm-ar changed archive member contents\n' >&2
    exit 1
fi

# GNU ar may have been installed by the still-partial binutils foundation, but
# it must not survive into the active PowerPC toolchain. Publish llvm-ar
# directly; no option-translating wrapper is necessary because llvm-ar already
# accepts the GNU ar operation/modifier grammar used by OpenBIOS.
mkdir -p "$TOOLCHAIN_DIR/bin" "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin" "$shim_dir"
rm -f "$shim_dir/ar" "$shim_dir/ar.bfd"
rm -f "$public_ar" "$target_ar"
ln -s "../llvm/bin/llvm-ar" "$public_ar"
ln -s "../../bin/${TOOLCHAIN_TARGET}-ar" "$target_ar"

if ! llvm_ar_toolchain_is_usable; then
    printf 'error: PowerPC ar compatibility entry points are not LLVM-only\n' >&2
    exit 1
fi

public_members="$("$public_ar" t "$smoke_dir/libarchive.a")"
if [[ "$public_members" != "$member_list" ]]; then
    printf 'error: published PowerPC ar changed LLVM archive behavior\n' >&2
    exit 1
fi

printf '%s\n' "$expected_ar_marker" > "$ar_marker"
printf '%s\n' \
    "Bootstrapped PowerPC ar: llvm-ar ($llvm_revision)" \
    "Compatibility ar: $public_ar" \
    "Target ar: $target_ar"
