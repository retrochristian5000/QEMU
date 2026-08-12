#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_BOOTSTRAP="$SCRIPT_DIR/bootstrap-powerpc-clang-base.sh"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
TOOLCHAIN_HOST_CC="${TOOLCHAIN_HOST_CC:-${CC_FOR_BUILD:-${CC:-cc}}}"
TOOLCHAIN_HOST_CXX="${TOOLCHAIN_HOST_CXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
LLVM_SUBMODULE_PATH="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SUBMODULE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
LLVM_GIT_OFFLINE="${POWERPC_LLVM_GIT_OFFLINE:-0}"
LLD_BUILD_DIR="${POWERPC_LLD_BUILD_DIR:-$TOOLCHAIN_WORK_DIR/lld-build}"
JOBS="${JOBS:-1}"

case "$TOOLCHAIN_TARGET" in
    powerpc-elf) ;;
    *)
        printf 'error: the Clang/LLD lane currently supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac
case "$TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac
case "$LLVM_GIT_OFFLINE" in
    0|1) ;;
    *)
        printf 'error: POWERPC_LLVM_GIT_OFFLINE must be 0 or 1\n' >&2
        exit 1
        ;;
esac

for required in git cmake ninja awk grep cksum ln mkdir mv rm readlink uname; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: PowerPC Clang/LLD bootstrap dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done
if [[ ! -f "$BASE_BOOTSTRAP" ]]; then
    printf 'error: base PowerPC Clang bootstrap is missing: %s\n' \
        "$BASE_BOOTSTRAP" >&2
    exit 1
fi

# QEMU's gitlink is the LLVM revision pin.  Initialize the checkout only when
# network access is allowed; an offline build must already have the submodule.
if [[ ! -f "$LLVM_SUBMODULE_DIR/llvm/CMakeLists.txt" ]]; then
    if [[ "$LLVM_GIT_OFFLINE" == 1 ]]; then
        printf 'error: LLVM submodule is not initialized in offline mode: %s\n' \
            "$LLVM_SUBMODULE_PATH" >&2
        exit 1
    fi
    git -C "$SOURCE_DIR" submodule update --init --depth 1 "$LLVM_SUBMODULE_PATH"
fi
if [[ ! -f "$LLVM_SUBMODULE_DIR/llvm/CMakeLists.txt" ||
      ! -f "$LLVM_SUBMODULE_DIR/clang/CMakeLists.txt" ||
      ! -f "$LLVM_SUBMODULE_DIR/lld/CMakeLists.txt" ]]; then
    printf 'error: LLVM submodule is missing llvm/clang/lld projects: %s\n' \
        "$LLVM_SUBMODULE_DIR" >&2
    exit 1
fi

expected_llvm_revision="$(
    git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH" | awk '{print $3}'
)"
llvm_revision="$(git -C "$LLVM_SUBMODULE_DIR" rev-parse HEAD)"
if [[ -z "$expected_llvm_revision" ]]; then
    printf 'error: LLVM submodule is not registered in QEMU: %s\n' \
        "$LLVM_SUBMODULE_PATH" >&2
    exit 1
fi
if [[ "$llvm_revision" != "$expected_llvm_revision" ]]; then
    printf '%s\n' \
        'error: LLVM checkout does not match the QEMU submodule pointer.' \
        "checked out: $llvm_revision" \
        "QEMU expects: $expected_llvm_revision" \
        "run: git submodule update --init $LLVM_SUBMODULE_PATH" >&2
    exit 1
fi
if [[ -n "$(git -C "$LLVM_SUBMODULE_DIR" status --porcelain --untracked-files=no)" ]]; then
    printf '%s\n' \
        'error: LLVM submodule has uncommitted tracked changes.' \
        'Commit LLVM changes in the LLVM fork, then update the QEMU submodule pointer.' >&2
    exit 1
fi

base_signature="$(cksum "$BASE_BOOTSTRAP" | awk '{print $1 ":" $2}')"
orchestrator_signature="$(cksum "${BASH_SOURCE[0]}" | awk '{print $1 ":" $2}')"
lld_marker="$TOOLCHAIN_DIR/.whp-powerpc-lld"
expected_lld_marker="$(cat <<MARKER
LLD_SCHEMA=1
LINKER=lld
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
BASE_BOOTSTRAP_SIGNATURE=$base_signature
ORCHESTRATOR_SIGNATURE=$orchestrator_signature
MARKER
)"

clang_lld_toolchain_is_usable()
{
    local tool

    for tool in gcc as ar ld nm objcopy objdump readelf strip ranlib; do
        [[ -x "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
    done
    [[ -x "$TOOLCHAIN_DIR/llvm/bin/clang" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/llvm/bin/ld.lld" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/llvm/bin/llvm-readelf" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu/as" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu/ld" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu/ld.bfd" ]] || return 1
    "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ld" --version 2>/dev/null |
        grep -q 'LLD' || return 1
}

base_force="$TOOLCHAIN_FORCE_REBUILD"
if [[ -f "$lld_marker" ]]; then
    old_base_signature="$(awk -F= '$1 == "BASE_BOOTSTRAP_SIGNATURE" {print $2; exit}' "$lld_marker")"
    if [[ -n "$old_base_signature" && "$old_base_signature" != "$base_signature" ]]; then
        base_force=1
    fi
fi

printf 'LLVM submodule revision: %s\n' "$llvm_revision"
# Always let the compiler/binutils foundation validate its own complete marker
# first.  It exits quickly when current and rebuilds atomically when one of its
# compiler, binutils, host, or LLVM inputs has changed.
POWERPC_LLVM_GIT_URL="$LLVM_SUBMODULE_DIR" \
POWERPC_LLVM_GIT_REF="$llvm_revision" \
POWERPC_LLVM_GIT_COMMIT="$llvm_revision" \
POWERPC_LLVM_GIT_OFFLINE=0 \
POWERPC_LLVM_SOURCE_DIR="$TOOLCHAIN_WORK_DIR/llvm-source-from-submodule" \
POWERPC_TOOLCHAIN_FORCE_REBUILD="$base_force" \
    bash "$BASE_BOOTSTRAP"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 && -f "$lld_marker" &&
      "$(cat "$lld_marker")" == "$expected_lld_marker" ]] &&
   clang_lld_toolchain_is_usable; then
    printf 'PowerPC Clang/LLD toolchain is current: %s/bin/%s-\n' \
        "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
    exit 0
fi

llvm_dir="$TOOLCHAIN_DIR/llvm"
llvm_cmake_dir="$llvm_dir/lib/cmake/llvm"
if [[ ! -d "$llvm_cmake_dir" ]]; then
    printf 'error: base LLVM install is missing CMake package files: %s\n' \
        "$llvm_cmake_dir" >&2
    exit 1
fi

cmake_platform_args=()
if [[ "$(uname -s)" == Darwin ]]; then
    for required in xcrun sw_vers; do
        if ! command -v "$required" >/dev/null 2>&1; then
            printf 'error: required Apple tool is missing: %s\n' "$required" >&2
            exit 1
        fi
    done
    sdkroot="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
    deployment_target="${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion | awk -F. '{print $1 "." $2}')}"
    case "$(uname -m)" in
        arm64|aarch64) host_arch=arm64 ;;
        x86_64) host_arch=x86_64 ;;
        *)
            printf 'error: unsupported Darwin host architecture: %s\n' "$(uname -m)" >&2
            exit 1
            ;;
    esac
    cmake_platform_args=(
        "-DCMAKE_OSX_SYSROOT=$sdkroot"
        "-DCMAKE_OSX_ARCHITECTURES=$host_arch"
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=$deployment_target"
    )
fi

printf 'Building LLD from QEMU LLVM submodule\n'
rm -rf "$LLD_BUILD_DIR"
cmake -S "$LLVM_SUBMODULE_DIR/lld" -B "$LLD_BUILD_DIR" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="$TOOLCHAIN_HOST_CC" \
    -DCMAKE_CXX_COMPILER="$TOOLCHAIN_HOST_CXX" \
    -DCMAKE_INSTALL_PREFIX="$llvm_dir" \
    -DLLVM_DIR="$llvm_cmake_dir" \
    -DLLVM_INCLUDE_TESTS=OFF \
    -DLLD_INCLUDE_TESTS=OFF \
    "${cmake_platform_args[@]}"
cmake --build "$LLD_BUILD_DIR" --parallel "$JOBS"
cmake --install "$LLD_BUILD_DIR"

lld="$llvm_dir/bin/ld.lld"
llvm_readelf="$llvm_dir/bin/llvm-readelf"
if [[ ! -x "$lld" ]]; then
    printf 'error: LLVM build did not produce LLD: %s\n' "$lld" >&2
    exit 1
fi
if [[ ! -x "$llvm_readelf" ]]; then
    printf 'error: LLVM install did not produce llvm-readelf: %s\n' \
        "$llvm_readelf" >&2
    exit 1
fi
if ! "$lld" --version | grep -q 'LLD'; then
    printf 'error: installed linker is not LLD: %s\n' "$lld" >&2
    exit 1
fi

# Before changing the public linker, prove LLD can reproduce the critical
# OpenBIOS ROM layout and the GNU-style options used by PPC-Firmware.
smoke_dir="$TOOLCHAIN_WORK_DIR/lld-openbios-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/layout.s" <<'ASSEMBLY'
.section .text.vectors,"ax",@progbits
.globl _entry
_entry:
    nop
.section .text,"ax",@progbits
.globl whp_lld_smoke
whp_lld_smoke:
    nop
.section .romentry,"ax",@progbits
.globl whp_hreset
whp_hreset:
    b _entry
ASSEMBLY
"$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as" \
    -o "$smoke_dir/layout.o" "$smoke_dir/layout.s"
"$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar" rcs \
    "$smoke_dir/liblayout.a" "$smoke_dir/layout.o"
cat > "$smoke_dir/layout.ld" <<'LDSCRIPT'
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
"$lld" --warn-common -z noexecstack -N \
    -T "$smoke_dir/layout.ld" \
    -o "$smoke_dir/layout.elf" \
    --whole-archive "$smoke_dir/liblayout.a"

layout_header="$(LC_ALL=C "$llvm_readelf" -hW "$smoke_dir/layout.elf")"
layout_symbols="$(LC_ALL=C "$llvm_readelf" -sW "$smoke_dir/layout.elf")"
layout_phdrs="$(LC_ALL=C "$llvm_readelf" -lW "$smoke_dir/layout.elf")"
if ! grep -Eq 'Class:[[:space:]]+ELF32' <<< "$layout_header" ||
   ! grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$layout_header" ||
   ! grep -Eq 'Type:[[:space:]]+EXEC' <<< "$layout_header" ||
   ! grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$layout_header" ||
   ! grep -Eq 'Entry point address:[[:space:]]+0xfff00100' <<< "$layout_header"; then
    printf 'error: LLD did not produce the expected OpenBIOS ELF header\n' >&2
    exit 1
fi
start_value="$(awk '$8 == "_start" {print tolower($2); exit}' <<< "$layout_symbols")"
entry_value="$(awk '$8 == "_entry" {print tolower($2); exit}' <<< "$layout_symbols")"
hreset_value="$(awk '$8 == "whp_hreset" {print tolower($2); exit}' <<< "$layout_symbols")"
if [[ "$start_value" != fff00100 || "$entry_value" != fff00000 ||
      "$hreset_value" != fffffffc ]]; then
    printf '%s\n' \
        'error: LLD changed the OpenBIOS PROM symbol layout.' \
        "_start=$start_value _entry=$entry_value hreset=$hreset_value" >&2
    exit 1
fi
if grep -Eq '^[[:space:]]*(INTERP|DYNAMIC)[[:space:]]' <<< "$layout_phdrs"; then
    printf 'error: LLD smoke image contains a dynamic-loader segment\n' >&2
    exit 1
fi
load_count=0
start_loaded=0
hreset_loaded=0
while read -r vaddr memsz; do
    [[ -n "$vaddr" && -n "$memsz" ]] || continue
    ((load_count += 1))
    vaddr_num=$((vaddr))
    memsz_num=$((memsz))
    end_num=$((vaddr_num + memsz_num))
    if ((vaddr_num < 0xfff00000 || end_num > 0x100000000)); then
        printf 'error: LLD LOAD segment escapes the OpenBIOS PROM window\n' >&2
        exit 1
    fi
    if ((vaddr_num <= 0xfff00100 && end_num > 0xfff00100)); then
        start_loaded=1
    fi
    if ((vaddr_num <= 0xfffffffc && end_num > 0xfffffffc)); then
        hreset_loaded=1
    fi
done < <(awk '$1 == "LOAD" {print $3, $6}' <<< "$layout_phdrs")
if ((load_count == 0 || start_loaded == 0 || hreset_loaded == 0)); then
    printf 'error: LLD did not map both OpenBIOS entry vectors into LOAD segments\n' >&2
    exit 1
fi

# LLD is now proven against the firmware layout.  Demote GNU ld to an explicit
# A/B oracle and make the normal powerpc-elf-ld interface resolve to LLD.
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
public_ld="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ld"
gnu_ld="$shim_dir/ld.bfd"
mkdir -p "$shim_dir"
if [[ ! -x "$gnu_ld" ]]; then
    if [[ ! -x "$public_ld" ]] || ! "$public_ld" --version 2>/dev/null | grep -q 'GNU ld'; then
        printf 'error: retained GNU linker is unavailable for the A/B fallback\n' >&2
        exit 1
    fi
    mv "$public_ld" "$gnu_ld"
fi
ln -sfn "../llvm/bin/ld.lld" "$public_ld"
ln -sfn "../../llvm/bin/ld.lld" "$shim_dir/ld"

clang_driver="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-gcc"
reported_as="$($clang_driver -print-prog-name=as)"
reported_ld="$($clang_driver -print-prog-name=ld)"
if [[ "$reported_as" != "$shim_dir/as" ]]; then
    printf 'error: Clang assembler route changed unexpectedly: %s\n' \
        "$reported_as" >&2
    exit 1
fi
if [[ "$reported_ld" != "$shim_dir/ld" ]]; then
    printf 'error: Clang is not routed through LLD: %s\n' "$reported_ld" >&2
    exit 1
fi
if ! "$public_ld" --version | grep -q 'LLD'; then
    printf 'error: public PowerPC linker does not resolve to LLD\n' >&2
    exit 1
fi

printf '%s\n' "$expected_lld_marker" > "$lld_marker"
printf '%s\n' \
    "Bootstrapped PowerPC compiler/linker: Clang + LLD ($llvm_revision)" \
    "LLVM source: QEMU submodule $LLVM_SUBMODULE_PATH" \
    "Retained assembler: GNU as" \
    "Private A/B linker: $gnu_ld" \
    "Compatibility prefix: $TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-"
