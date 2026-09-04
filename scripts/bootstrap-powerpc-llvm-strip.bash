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
        printf 'error: the LLVM strip lane currently supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac

for required in git awk grep cksum mkdir rm ln; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: LLVM strip migration dependency not found: %s\n' \
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
llvm_strip="$TOOLCHAIN_DIR/llvm/bin/llvm-strip"
llvm_readelf="$TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
public_ld="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ld"
public_strip="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-strip"
target_strip="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/strip"
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
strip_marker="$TOOLCHAIN_DIR/.whp-powerpc-strip"
strip_signature="$(cksum "${BASH_SOURCE[0]}" | awk '{print $1 ":" $2}')"
expected_strip_marker="$(cat <<MARKER
STRIP_SCHEMA=2
STRIP=llvm-strip
GNU_STRIP=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
STRIP_BOOTSTRAP_SIGNATURE=$strip_signature
MARKER
)"

llvm_strip_toolchain_is_usable()
{
    [[ -x "$llvm_strip" ]] || return 1
    [[ -x "$llvm_readelf" ]] || return 1
    [[ -x "$public_strip" ]] || return 1
    [[ -e "$target_strip" ]] || return 1
    [[ ! -e "$shim_dir/strip" ]] || return 1
    [[ ! -e "$shim_dir/strip.bfd" ]] || return 1
    "$llvm_strip" --version 2>/dev/null | grep -q 'llvm-strip' || return 1
    "$public_strip" --version 2>/dev/null | grep -q 'llvm-strip' || return 1
    "$target_strip" --version 2>/dev/null | grep -q 'llvm-strip' || return 1
}

if [[ -f "$strip_marker" &&
      "$(cat "$strip_marker")" == "$expected_strip_marker" ]] &&
   llvm_strip_toolchain_is_usable; then
    printf 'PowerPC LLVM strip stage is current: %s\n' "$public_strip"
    exit 0
fi

for required_tool in "$clang" "$llvm_strip" "$llvm_readelf" "$public_ld"; do
    if [[ ! -x "$required_tool" ]]; then
        printf 'error: LLVM strip migration prerequisite is missing: %s\n' \
            "$required_tool" >&2
        exit 1
    fi
done
if ! "$llvm_strip" --version 2>/dev/null | grep -q 'llvm-strip'; then
    printf 'error: installed LLVM strip executable is invalid: %s\n' \
        "$llvm_strip" >&2
    exit 1
fi
if ! "$public_ld" --version 2>/dev/null | grep -q 'LLD'; then
    printf 'error: LLVM strip migration requires the proven LLD linker stage\n' >&2
    exit 1
fi

# Exercise exactly the OpenBIOS strip interface before publishing llvm-strip:
#   $(STRIP) openbios-qemu.elf.nostrip -o openbios-qemu.elf
# The smoke image deliberately uses the same PowerPC PROM address window as
# OpenBIOS so stripping cannot silently change ELF class, endian, entry point,
# load segments, or allocatable section contents.
smoke_dir="$TOOLCHAIN_WORK_DIR/llvm-strip-openbios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/strip.s" <<'ASSEMBLY'
.section .text.vectors,"ax",@progbits
.globl _entry
_entry:
    nop
.section .text,"ax",@progbits
.globl whp_strip_smoke
whp_strip_smoke:
    nop
.section .romentry,"ax",@progbits
.globl whp_strip_hreset
whp_strip_hreset:
    b _entry
ASSEMBLY
"$clang" --target=powerpc-none-elf -c -x assembler \
    -o "$smoke_dir/strip.o" "$smoke_dir/strip.s"
cat > "$smoke_dir/strip.ld" <<'LDSCRIPT'
OUTPUT_FORMAT(elf32-powerpc)
OUTPUT_ARCH(powerpc:common)
ENTRY(_start)
BASE_ADDR = 0xfff00000;
TEXT_ADDR = 0xfff08000;
HRESET_ADDR = 0xfffffffc;
SECTIONS
{
    . = BASE_ADDR;
    _start = BASE_ADDR + 0x0100;
    .text.vectors ALIGN(4096): { *(.text.vectors) }
    . = TEXT_ADDR;
    .text ALIGN(4096): { *(.text) *(.text.*) }
    . = HRESET_ADDR;
    .romentry : { *(.romentry) }
    . = ALIGN(4096);
    _end = .;
    /DISCARD/ : { *(.comment*) *(.note.*) }
}
LDSCRIPT
"$public_ld" --warn-common -z noexecstack -N \
    -T "$smoke_dir/strip.ld" \
    -o "$smoke_dir/unstripped.elf" "$smoke_dir/strip.o"

before_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/unstripped.elf")"
before_sections="$(LC_ALL=C "$llvm_readelf" -SW "$smoke_dir/unstripped.elf")"
before_phdrs="$(LC_ALL=C "$llvm_readelf" -lW "$smoke_dir/unstripped.elf")"
before_text="$(LC_ALL=C "$llvm_readelf" -x .text "$smoke_dir/unstripped.elf")"
before_rom="$(LC_ALL=C "$llvm_readelf" -x .romentry "$smoke_dir/unstripped.elf")"
if ! grep -Eq '[[:space:]]\.symtab[[:space:]]' <<< "$before_sections"; then
    printf 'error: LLVM strip smoke input has no symbol table to remove\n' >&2
    exit 1
fi

"$llvm_strip" "$smoke_dir/unstripped.elf" -o "$smoke_dir/stripped.elf"

after_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/stripped.elf")"
after_sections="$(LC_ALL=C "$llvm_readelf" -SW "$smoke_dir/stripped.elf")"
after_phdrs="$(LC_ALL=C "$llvm_readelf" -lW "$smoke_dir/stripped.elf")"
after_text="$(LC_ALL=C "$llvm_readelf" -x .text "$smoke_dir/stripped.elf")"
after_rom="$(LC_ALL=C "$llvm_readelf" -x .romentry "$smoke_dir/stripped.elf")"

header_identity()
{
    grep -E '^[[:space:]]*(Class:|Data:|Type:|Machine:|Entry point address:)' <<< "$1"
}
load_identity()
{
    awk '$1 == "LOAD" {print $2, $3, $4, $5, $6, $7, $8}' <<< "$1"
}

if [[ "$(header_identity "$before_header")" != \
      "$(header_identity "$after_header")" ]]; then
    printf 'error: llvm-strip changed a critical OpenBIOS ELF header field\n' >&2
    exit 1
fi
if [[ "$(load_identity "$before_phdrs")" != \
      "$(load_identity "$after_phdrs")" ]]; then
    printf 'error: llvm-strip changed the OpenBIOS LOAD segment layout\n' >&2
    exit 1
fi
if [[ "$before_text" != "$after_text" || "$before_rom" != "$after_rom" ]]; then
    printf 'error: llvm-strip changed allocatable OpenBIOS section contents\n' >&2
    exit 1
fi
if grep -Eq '[[:space:]]\.symtab[[:space:]]' <<< "$after_sections"; then
    printf 'error: llvm-strip did not remove the ELF symbol table\n' >&2
    exit 1
fi
if ! grep -Eq 'Entry point address:[[:space:]]+0xfff00100' <<< "$after_header" ||
   ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$after_header" ||
   ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$after_header"; then
    printf 'error: llvm-strip output is not the expected PowerPC OpenBIOS ELF\n' >&2
    exit 1
fi

# Remove any GNU strip residue from older toolchains, then publish only LLVM
# implementations under both GNU-compatible strip entry points.
mkdir -p "$TOOLCHAIN_DIR/bin" "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin"
rm -f "$shim_dir/strip" "$shim_dir/strip.bfd"
rm -f "$public_strip" "$target_strip"
ln -s "../llvm/bin/llvm-strip" "$public_strip"
ln -s "../../bin/${TOOLCHAIN_TARGET}-strip" "$target_strip"

if ! llvm_strip_toolchain_is_usable; then
    printf 'error: PowerPC strip compatibility entry points are not LLVM-only\n' >&2
    exit 1
fi
printf '%s\n' "$expected_strip_marker" > "$strip_marker"
printf '%s\n' \
    "Bootstrapped PowerPC strip: llvm-strip ($llvm_revision)" \
    "Compatibility strip: $public_strip" \
    "Target strip: $target_strip"
