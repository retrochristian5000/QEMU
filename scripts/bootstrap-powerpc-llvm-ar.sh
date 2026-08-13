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

for required in git awk grep cksum ln mkdir rm readlink; do
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

llvm_ar="$TOOLCHAIN_DIR/llvm/bin/llvm-ar"
llvm_nm="$TOOLCHAIN_DIR/llvm/bin/llvm-nm"
llvm_readelf="$TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
public_as="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"
public_ld="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ld"
public_ar="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar"
target_ar="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/ar"
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
ar_marker="$TOOLCHAIN_DIR/.whp-powerpc-ar"
ar_signature="$(cksum "${BASH_SOURCE[0]}" | awk '{print $1 ":" $2}')"
expected_ar_marker="$(cat <<MARKER
AR_SCHEMA=1
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

for required_tool in "$llvm_ar" "$llvm_nm" "$llvm_readelf" \
                     "$public_as" "$public_ld"; do
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
if ! "$public_ld" --version 2>/dev/null | grep -q 'LLD'; then
    printf 'error: LLVM ar migration requires the proven LLD linker stage\n' >&2
    exit 1
fi
if ! "$llvm_nm" --help 2>/dev/null | grep -q -- '--gnu-compatible'; then
    printf 'error: LLVM ar qualification requires GNU-compatible llvm-nm\n' >&2
    exit 1
fi

# Qualify the archive operations OpenBIOS and the PowerPC linker lane depend on
# before publishing llvm-ar.  The test uses a real ELF32 big-endian PowerPC
# object, requires an archive symbol index, verifies member enumeration, and
# proves LLD can consume the resulting archive.
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
"$public_as" -o "$smoke_dir/archive.o" "$smoke_dir/archive.s"
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

"$public_ld" -r --whole-archive "$smoke_dir/libarchive.a" \
    --no-whole-archive -o "$smoke_dir/linked.o"
linked_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/linked.o")"
linked_symbols="$(LC_ALL=C "$llvm_readelf" -sW "$smoke_dir/linked.o")"
if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$linked_header" ||
   ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$linked_header" ||
   ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$linked_header" ||
   ! grep -Eq '[[:space:]]whp_llvm_ar_smoke$' <<< "$linked_symbols"; then
    printf 'error: LLD could not consume the llvm-ar PowerPC archive correctly\n' >&2
    exit 1
fi

# GNU ar has served only as the bootstrap implementation up to this point.
# Remove any published/private residue and expose llvm-ar directly: no option
# translating wrapper is required because llvm-ar already accepts GNU ar's
# operation/modifier grammar.
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
