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
clang_driver="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-gcc"
public_as="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"
target_bin="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin"
target_as="$target_bin/as"
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
marker="$TOOLCHAIN_DIR/.whp-powerpc-as"

if [[ ! -x "$clang" ]]; then
    printf 'error: WHP Clang is missing: %s\n' "$clang" >&2
    exit 1
fi
if [[ ! -x "$llvm_readelf" ]]; then
    printf 'error: WHP llvm-readelf is missing: %s\n' "$llvm_readelf" >&2
    exit 1
fi
if [[ ! -x "$clang_driver" ]]; then
    printf 'error: WHP PowerPC Clang compatibility driver is missing: %s\n' \
        "$clang_driver" >&2
    exit 1
fi
if [[ ! -f "$LLVM_SUBMODULE_DIR/llvm/CMakeLists.txt" ]]; then
    printf 'error: LLVM submodule is not initialized: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi
if [[ -e "$shim_dir/as" || -e "$shim_dir/as.bfd" ]]; then
    printf '%s\n' \
        'error: GNU as residue remains in the PowerPC toolchain.' \
        'run the full PowerPC toolchain bootstrap so binutils is rebuilt with GAS disabled.' >&2
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
ASSEMBLER_SCHEMA=3
ASSEMBLER=clang-integrated
GNU_GAS=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
STAGE_SIGNATURE=$stage_signature
MARKER
)"

mkdir -p "$TOOLCHAIN_WORK_DIR" "$target_bin"
smoke_dir="$TOOLCHAIN_WORK_DIR/llvm-as-openbios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir/candidate-bin"
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
.ifc \value,4
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
cat > "$smoke_dir/openbios.c" <<'SOURCE'
#if !defined(__powerpc__) && !defined(__POWERPC__) && !defined(__PPC__)
#error compiler is not targeting PowerPC
#endif
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
#error compiler does not default to big endian
#endif
int whp_llvm_as_global = 7;
int whp_llvm_as_c_smoke(int value) { return whp_llvm_as_global + value; }
SOURCE

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
    if [[ "$object" == *assembly.o ]] &&
       ! grep -Eq '[[:space:]]\.text\.vectors[[:space:]]' <<< "$sections"; then
        printf 'error: assembler dropped the OpenBIOS-style vector section\n' >&2
        return 1
    fi
}

# PPC-Firmware invokes a GNU-style `as` interface.  Translate only the GNU
# mode-selection flags whose meaning is already fixed by powerpc-none-elf and
# send all assembly into Clang's integrated PowerPC assembler.
candidate_as="$smoke_dir/candidate-bin/as"
cat > "$candidate_as" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${WHP_POWERPC_CLANG:-}" ]]; then
    clang="$WHP_POWERPC_CLANG"
else
    prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
    clang="$prefix/llvm/bin/clang"
fi
if [[ ! -x "$clang" ]]; then
    printf 'error: WHP PowerPC assembler cannot find Clang: %s\n' "$clang" >&2
    exit 1
fi

translated=()
for arg in "$@"; do
    case "$arg" in
        -a32|-mppc|-many)
            ;;
        *)
            translated+=("$arg")
            ;;
    esac
done

exec "$clang" --target=powerpc-none-elf -c -x assembler "${translated[@]}"
WRAPPER
chmod +x "$candidate_as"

printf 'Qualifying WHP LLVM integrated assembler for PowerPC OpenBIOS\n'
WHP_POWERPC_CLANG="$clang" \
    "$candidate_as" "$smoke_dir/openbios.s" -m32 -g \
        -o "$smoke_dir/candidate-assembly.o"
verify_powerpc_object "$smoke_dir/candidate-assembly.o"

# The compatibility compiler itself must also succeed with no external `as`
# available.  Its driver forces -fintegrated-as in the base bootstrap.
"$clang_driver" \
    -m32 -mcpu=604 -msoft-float \
    -mcall-sysv-noeabi -msdata=none -G0 \
    -ffreestanding -fno-pic -fno-pie -O0 -g \
    -c "$smoke_dir/openbios.c" -o "$smoke_dir/candidate-c.o"
verify_powerpc_object "$smoke_dir/candidate-c.o"

assembler_route_is_current()
{
    [[ -f "$marker" ]] || return 1
    [[ "$(cat "$marker")" == "$expected_marker" ]] || return 1
    [[ -x "$public_as" ]] || return 1
    [[ -e "$target_as" ]] || return 1
    [[ ! -e "$shim_dir/as" ]] || return 1
    [[ ! -e "$shim_dir/as.bfd" ]] || return 1
    ! "$public_as" --version 2>&1 | grep -q 'GNU assembler'
}

validate_public_route()
{
    "$public_as" "$smoke_dir/openbios.s" -m32 -g \
        -o "$smoke_dir/public-assembly.o"
    verify_powerpc_object "$smoke_dir/public-assembly.o"

    "$clang_driver" \
        -m32 -mcpu=604 -msoft-float \
        -mcall-sysv-noeabi -msdata=none -G0 \
        -ffreestanding -fno-pic -fno-pie -O0 -g \
        -c "$smoke_dir/openbios.c" -o "$smoke_dir/public-c.o"
    verify_powerpc_object "$smoke_dir/public-c.o"
}

if assembler_route_is_current; then
    validate_public_route
    printf 'PowerPC LLVM assembler route is current: %s\n' "$public_as"
    exit 0
fi

if [[ -x "$public_as" ]] &&
   "$public_as" --version 2>&1 | grep -q 'GNU assembler'; then
    printf '%s\n' \
        'error: public PowerPC assembler is still GNU as.' \
        'run the full bootstrap so the GAS-disabled base toolchain replaces it first.' >&2
    exit 1
fi

mv -f "$candidate_as" "$public_as"
ln -sfn "../../bin/${TOOLCHAIN_TARGET}-as" "$target_as"
validate_public_route

printf '%s\n' "$expected_marker" > "$marker"
printf '%s\n' \
    "Published PowerPC assembler: $public_as -> WHP Clang IAS" \
    "GNU GAS: disabled" \
    "LLVM revision: $llvm_revision"
