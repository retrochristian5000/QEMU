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
        printf 'error: the LLVM assembler migration supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac

for required in git awk grep cksum chmod ln mkdir mv rm; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: PowerPC LLVM assembler dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done

clang="$TOOLCHAIN_DIR/llvm/bin/clang"
llvm_readelf="$TOOLCHAIN_DIR/llvm/bin/llvm-readelf"
public_as="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
gnu_as="$shim_dir/as.bfd"
shim_as="$shim_dir/as"
marker="$TOOLCHAIN_DIR/.whp-powerpc-as"

if [[ ! -x "$clang" ]]; then
    printf 'error: WHP Clang is missing: %s\n' "$clang" >&2
    exit 1
fi
if [[ ! -x "$llvm_readelf" ]]; then
    printf 'error: WHP llvm-readelf is missing: %s\n' "$llvm_readelf" >&2
    exit 1
fi
if [[ ! -f "$LLVM_SUBMODULE_DIR/llvm/CMakeLists.txt" ]]; then
    printf 'error: LLVM submodule is not initialized: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi

expected_llvm_revision="$(
    git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH" | awk '{print $3}'
)"
llvm_revision="$(git -C "$LLVM_SUBMODULE_DIR" rev-parse HEAD)"
if [[ -z "$expected_llvm_revision" ||
      "$llvm_revision" != "$expected_llvm_revision" ]]; then
    printf '%s\n' \
        'error: LLVM checkout does not match the QEMU submodule pointer.' \
        "checked out: ${llvm_revision:-missing}" \
        "QEMU expects: ${expected_llvm_revision:-missing}" >&2
    exit 1
fi

stage_signature="$(cksum "${BASH_SOURCE[0]}" | awk '{print $1 ":" $2}')"
expected_marker="$(cat <<MARKER
ASSEMBLER_SCHEMA=1
ASSEMBLER=clang-integrated
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
STAGE_SIGNATURE=$stage_signature
MARKER
)"

mkdir -p "$TOOLCHAIN_WORK_DIR" "$shim_dir"
smoke_dir="$TOOLCHAIN_WORK_DIR/llvm-as-openbios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/openbios.s" <<'ASSEMBLY'
.section .text,"ax",@progbits
.globl whp_llvm_as_smoke
whp_llvm_as_smoke:
    lis 3, whp_llvm_as_data@ha
    addi 3, 3, whp_llvm_as_data@l
    mftbu 4
    mftb 5
    cmpw 0, 4, 5
    bne 1f
    blr
1:
    rfi

.macro WHP_OPENBIOS_MACRO value
.ifc \\value,4
    nop
.else
    blr
.endif
.endm
WHP_OPENBIOS_MACRO 4

.section .text.vectors,"ax",@progbits
.org 0x100
.globl whp_llvm_as_vector
whp_llvm_as_vector:
    nop

.section .data,"aw",@progbits
whp_llvm_as_data:
    .long 0x12345678
ASSEMBLY

verify_powerpc_object()
{
    local object="$1"
    local header
    local sections

    header="$(LC_ALL=C "$llvm_readelf" -hW "$object")"
    sections="$(LC_ALL=C "$llvm_readelf" -SW "$object")"
    if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$header" ||
       ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$header" ||
       ! grep -Eq 'Type:[[:space:]]+REL' <<< "$header" ||
       ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$header"; then
        printf 'error: assembler did not emit ELF32 big-endian PowerPC REL\n' >&2
        printf '%s\n' "$header" >&2
        return 1
    fi
    if ! grep -Eq '[[:space:]]\.text\.vectors[[:space:]]' <<< "$sections"; then
        printf 'error: assembler dropped the OpenBIOS-style vector section\n' >&2
        return 1
    fi
}

# Qualification happens before changing the public assembler.  If the pinned
# LLVM IAS cannot consume the GNU-style surface OpenBIOS needs, leave GNU as in
# place and fail here with the real assembler diagnostic.
printf 'Qualifying WHP LLVM integrated assembler for PowerPC OpenBIOS\n'
"$clang" --target=powerpc-none-elf -c -x assembler \
    "$smoke_dir/openbios.s" -m32 -g -o "$smoke_dir/llvm-direct.o"
verify_powerpc_object "$smoke_dir/llvm-direct.o"

assembler_route_is_current()
{
    [[ -f "$marker" ]] || return 1
    [[ "$(cat "$marker")" == "$expected_marker" ]] || return 1
    [[ -x "$public_as" ]] || return 1
    [[ -x "$gnu_as" ]] || return 1
    [[ -x "$shim_as" ]] || return 1
    "$gnu_as" --version 2>/dev/null | grep -q 'GNU assembler' || return 1
}

if assembler_route_is_current; then
    "$public_as" "$smoke_dir/openbios.s" -m32 -g \
        -o "$smoke_dir/public.o"
    verify_powerpc_object "$smoke_dir/public.o"
    printf 'PowerPC LLVM assembler route is current: %s\n' "$public_as"
    exit 0
fi

# Preserve GNU as as the controlled A/B oracle before publishing LLVM IAS.
# Never overwrite the oracle with an already-rerouted wrapper.
if [[ ! -x "$gnu_as" ]]; then
    if [[ ! -x "$public_as" ]] ||
       ! "$public_as" --version 2>/dev/null | grep -q 'GNU assembler'; then
        printf '%s\n' \
            'error: cannot preserve GNU as before the LLVM assembler reroute.' \
            "public assembler: $public_as" \
            "expected oracle: $gnu_as" >&2
        exit 1
    fi
    mv "$public_as" "$gnu_as"
fi
if ! "$gnu_as" --version 2>/dev/null | grep -q 'GNU assembler'; then
    printf 'error: retained assembler oracle is not GNU as: %s\n' "$gnu_as" >&2
    exit 1
fi

wrapper_candidate="${public_as}.new.$$"
rm -f "$wrapper_candidate"
cat > "$wrapper_candidate" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
clang="$prefix/llvm/bin/clang"
if [[ ! -x "$clang" ]]; then
    printf 'error: WHP PowerPC assembler cannot find Clang: %s\n' "$clang" >&2
    exit 1
fi
exec "$clang" --target=powerpc-none-elf -c -x assembler "$@"
WRAPPER
chmod +x "$wrapper_candidate"
mv -f "$wrapper_candidate" "$public_as"

# The existing Clang compatibility driver still uses -fno-integrated-as for
# this first experiment.  Keep that path intact, but make its external `as`
# resolve to the newly published LLVM IAS wrapper rather than GNU as.
ln -sfn "../../bin/${TOOLCHAIN_TARGET}-as" "$shim_as"

"$public_as" "$smoke_dir/openbios.s" -m32 -g -o "$smoke_dir/public.o"
verify_powerpc_object "$smoke_dir/public.o"

printf '%s\n' "$expected_marker" > "$marker"
printf '%s\n' \
    "Rerouted PowerPC assembler: $public_as -> WHP Clang IAS" \
    "Retained GNU assembler oracle: $gnu_as" \
    "LLVM revision: $llvm_revision"
