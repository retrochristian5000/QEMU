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
        printf 'error: the LLVM nm lane currently supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac

for required in git awk grep cksum chmod ln mkdir rm; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: LLVM nm migration dependency not found: %s\n' \
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

llvm_nm="$TOOLCHAIN_DIR/llvm/bin/llvm-nm"
public_as="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"
public_ar="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar"
public_nm="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-nm"
target_nm="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/nm"
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
nm_marker="$TOOLCHAIN_DIR/.whp-powerpc-nm"
nm_signature="$(cksum "${BASH_SOURCE[0]}" | awk '{print $1 ":" $2}')"
expected_nm_marker="$(cat <<MARKER
NM_SCHEMA=1
NM=llvm-nm
GNU_COMPATIBILITY=--gnu-compatible
GNU_NM=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
NM_BOOTSTRAP_SIGNATURE=$nm_signature
MARKER
)"

llvm_nm_toolchain_is_usable()
{
    [[ -x "$llvm_nm" ]] || return 1
    [[ -x "$public_nm" ]] || return 1
    [[ -e "$target_nm" ]] || return 1
    [[ ! -e "$shim_dir/nm" ]] || return 1
    [[ ! -e "$shim_dir/nm.bfd" ]] || return 1
    grep -Fq -- '--gnu-compatible' "$public_nm" || return 1
    "$llvm_nm" --version 2>/dev/null | grep -q 'llvm-nm' || return 1
    "$public_nm" --version 2>/dev/null | grep -q 'llvm-nm' || return 1
    "$target_nm" --version 2>/dev/null | grep -q 'llvm-nm' || return 1
}

if [[ -f "$nm_marker" &&
      "$(cat "$nm_marker")" == "$expected_nm_marker" ]] &&
   llvm_nm_toolchain_is_usable; then
    printf 'PowerPC LLVM nm stage is current: %s\n' "$public_nm"
    exit 0
fi

for required_tool in "$llvm_nm" "$public_as" "$public_ar"; do
    if [[ ! -x "$required_tool" ]]; then
        printf 'error: LLVM nm migration prerequisite is missing: %s\n' \
            "$required_tool" >&2
        exit 1
    fi
done
if ! "$llvm_nm" --version 2>/dev/null | grep -q 'llvm-nm'; then
    printf 'error: installed LLVM nm executable is invalid: %s\n' \
        "$llvm_nm" >&2
    exit 1
fi
if ! "$llvm_nm" --help 2>/dev/null | grep -q -- '--gnu-compatible'; then
    printf 'error: llvm-nm does not provide the WHP GNU compatibility mode\n' >&2
    printf 'LLVM revision: %s\n' "$llvm_revision" >&2
    exit 1
fi

# Qualify the GNU compatibility semantics needed by the PowerPC firmware lane
# before replacing GNU nm. The archive-map check catches the -s collision with
# native llvm-nm's Darwin segment/section option, while the format checks prove
# GNU first-character and case-insensitive -f behavior.
smoke_dir="$TOOLCHAIN_WORK_DIR/llvm-nm-openbios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/nm.s" <<'ASSEMBLY'
.text
.globl whp_llvm_nm_smoke
whp_llvm_nm_smoke:
    nop
.globl whp_llvm_nm_second
whp_llvm_nm_second:
    blr
ASSEMBLY
"$public_as" -o "$smoke_dir/nm.o" "$smoke_dir/nm.s"
"$public_ar" rcs "$smoke_dir/libnm.a" "$smoke_dir/nm.o"

armap_output="$("$llvm_nm" --gnu-compatible -s "$smoke_dir/libnm.a")"
if ! grep -Fq 'Archive map' <<< "$armap_output" ||
   ! grep -Fq 'whp_llvm_nm_smoke in ' <<< "$armap_output"; then
    printf 'error: llvm-nm GNU -s did not expose the archive map\n' >&2
    exit 1
fi

bsd_output="$("$llvm_nm" --gnu-compatible -f Banana "$smoke_dir/nm.o")"
if ! grep -Eq '^[[:xdigit:]]+[[:space:]]+T[[:space:]]+whp_llvm_nm_smoke$' \
        <<< "$bsd_output"; then
    printf 'error: llvm-nm GNU abbreviated BSD format is incompatible\n' >&2
    exit 1
fi

# Remove GNU nm residue from the published toolchain and expose a deliberately
# thin compatibility launcher. GNU semantics stay in LLVM rather than leaking
# into QEMU wrapper logic.
mkdir -p "$TOOLCHAIN_DIR/bin" "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin" "$shim_dir"
rm -f "$shim_dir/nm" "$shim_dir/nm.bfd"
rm -f "$public_nm" "$target_nm"
cat > "$public_nm" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail
prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
llvm_nm="$prefix/llvm/bin/llvm-nm"
if [[ ! -x "$llvm_nm" ]]; then
    printf 'error: WHP PowerPC nm cannot find llvm-nm: %s\n' "$llvm_nm" >&2
    exit 1
fi
exec "$llvm_nm" --gnu-compatible "$@"
WRAPPER
chmod +x "$public_nm"
ln -s "../../bin/${TOOLCHAIN_TARGET}-nm" "$target_nm"

if ! llvm_nm_toolchain_is_usable; then
    printf 'error: PowerPC nm compatibility entry points are not LLVM-only\n' >&2
    exit 1
fi

public_armap="$("$public_nm" -s "$smoke_dir/libnm.a")"
if [[ "$public_armap" != "$armap_output" ]]; then
    printf 'error: published PowerPC nm changed GNU archive-map behavior\n' >&2
    exit 1
fi

printf '%s\n' "$expected_nm_marker" > "$nm_marker"
printf '%s\n' \
    "Bootstrapped PowerPC nm: llvm-nm ($llvm_revision)" \
    "GNU compatibility: --gnu-compatible" \
    "Compatibility nm: $public_nm" \
    "Target nm: $target_nm"
