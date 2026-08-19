#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
BASE_BOOTSTRAP="$SCRIPT_DIR/bootstrap-powerpc-clang-base.sh"
AR_BOOTSTRAP="$SCRIPT_DIR/bootstrap-powerpc-llvm-ar.sh"
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
JOBS="${JOBS:-}"

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

cmake_parallel_args=(--parallel)
if [[ -n "$JOBS" ]]; then
    case "$JOBS" in
        0|*[!0-9]*)
            printf 'error: JOBS must be a positive integer when set: %s\n' "$JOBS" >&2
            exit 1
            ;;
    esac
    cmake_parallel_args=(--parallel "$JOBS")
fi

for required in git cmake ninja awk grep cksum ln mkdir rm readlink uname; do
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

# QEMU's gitlink is the LLVM revision pin. Initialize the checkout only when
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

clang_lld_toolchain_is_usable()
{
    local bfd_tool
    local tool

    for tool in gcc ar ld ranlib; do
        [[ -x "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
    done
    [[ -x "$TOOLCHAIN_DIR/llvm/bin/clang" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/llvm/bin/ld.lld" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/llvm/bin/llvm-readelf" ]] || return 1
    [[ -x "$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu/ld" ]] || return 1
    for tool in as ar ld nm objcopy objdump readelf strip ranlib; do
        bfd_tool="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu/${tool}.bfd"
        [[ ! -e "$bfd_tool" ]] || return 1
    done
    [[ "$(readlink "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ld")" == \
       "../llvm/bin/ld.lld" ]] || return 1
    [[ "$(readlink "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/ld")" == \
       "../../bin/${TOOLCHAIN_TARGET}-ld" ]] || return 1
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
# Always let the compiler/LLVM foundation validate its own complete marker
# first. It exits quickly when current and rebuilds atomically when one of its
# compiler, host, or LLVM inputs has changed.
POWERPC_LLVM_GIT_URL="$LLVM_SUBMODULE_DIR" \
POWERPC_LLVM_GIT_REF="$llvm_revision" \
POWERPC_LLVM_GIT_COMMIT="$llvm_revision" \
POWERPC_LLVM_GIT_OFFLINE=0 \
POWERPC_LLVM_SOURCE_DIR="$TOOLCHAIN_WORK_DIR/llvm-source-from-submodule" \
POWERPC_TOOLCHAIN_FORCE_REBUILD="$base_force" \
    bash "$BASE_BOOTSTRAP"

# The LLD smoke links through a real archive, so make the core entry point
# independently usable as well as callable through the full orchestrator.
bash "$AR_BOOTSTRAP"

llvm_dir="$TOOLCHAIN_DIR/llvm"
llvm_cmake_dir="$llvm_dir/lib/cmake/llvm"
base_marker="$TOOLCHAIN_DIR/.whp-powerpc-toolchain"
if [[ ! -d "$llvm_cmake_dir" ]]; then
    printf 'error: base LLVM install is missing CMake package files: %s\n' \
        "$llvm_cmake_dir" >&2
    exit 1
fi
if [[ ! -f "$base_marker" ]]; then
    printf 'error: base LLVM install is missing its bootstrap marker: %s\n' \
        "$base_marker" >&2
    exit 1
fi

# Reuse the exact host compile/link profile proven by the completed base LLVM
# stage. C and C++ are intentionally separate: C++ uses the lighter incremental
# profile while C retains the existing release optimization policy.
lld_host_c_release_flags="$(awk -F= '$1 == "HOST_C_RELEASE_FLAGS" {sub(/^[^=]*=/, ""); print; exit}' "$base_marker")"
lld_host_cxx_release_flags="$(awk -F= '$1 == "HOST_CXX_RELEASE_FLAGS" {sub(/^[^=]*=/, ""); print; exit}' "$base_marker")"
lld_host_linker="$(awk -F= '$1 == "HOST_LINKER" {print $2; exit}' "$base_marker")"
if [[ -z "$lld_host_c_release_flags" || -z "$lld_host_cxx_release_flags" ]]; then
    printf 'error: base LLVM marker is missing split C/C++ release flags\n' >&2
    exit 1
fi
base_marker_signature="$(cksum "$base_marker" | awk '{print $1 ":" $2}')"

# Key LLD to the actual base marker, not only to the bootstrap script checksum.
# This makes output-affecting knobs such as the C++ optimization level rebuild
# LLD exactly once, while execution-only settings such as JOBS do not invalidate
# either marker.
expected_lld_marker="$(cat <<MARKER
LLD_SCHEMA=5
LLD_BUILD_MODE=incremental-elf-only
LINKER=lld
ASSEMBLER=clang-integrated
GNU_BINUTILS=disabled
SFRAME=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_SOURCE_MODE=submodule
LLVM_SUBMODULE_PATH=$LLVM_SUBMODULE_PATH
LLVM_GIT_COMMIT=$llvm_revision
BASE_BOOTSTRAP_SIGNATURE=$base_signature
BASE_MARKER_SIGNATURE=$base_marker_signature
ORCHESTRATOR_SIGNATURE=$orchestrator_signature
HOST_C_RELEASE_FLAGS=$lld_host_c_release_flags
HOST_CXX_RELEASE_FLAGS=$lld_host_cxx_release_flags
MARKER
)"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 && -f "$lld_marker" &&
      "$(cat "$lld_marker")" == "$expected_lld_marker" ]] &&
   clang_lld_toolchain_is_usable; then
    printf 'PowerPC Clang/LLD toolchain is current: %s/bin/%s-\n' \
        "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
    exit 0
fi

cmake_host_profile_args=()
if [[ "$lld_host_c_release_flags" != toolchain-default ]]; then
    cmake_host_profile_args+=("-DCMAKE_C_FLAGS_RELEASE=$lld_host_c_release_flags")
fi
if [[ "$lld_host_cxx_release_flags" != toolchain-default ]]; then
    cmake_host_profile_args+=("-DCMAKE_CXX_FLAGS_RELEASE=$lld_host_cxx_release_flags")
fi
if [[ -n "$lld_host_linker" && "$lld_host_linker" != toolchain-default ]]; then
    cmake_host_profile_args+=("-DLLVM_USE_LINKER=$lld_host_linker")
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

printf 'Building focused ELF LLD from QEMU LLVM submodule\n'
cmake -S "$LLVM_SUBMODULE_DIR/lld" -B "$LLD_BUILD_DIR" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="$TOOLCHAIN_HOST_CC" \
    -DCMAKE_CXX_COMPILER="$TOOLCHAIN_HOST_CXX" \
    "${cmake_host_profile_args[@]}" \
    -DCMAKE_INSTALL_PREFIX="$llvm_dir" \
    -DCMAKE_INSTALL_LIBDIR=lib \
    -DCMAKE_EXPORT_COMPILE_COMMANDS=OFF \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF \
    -DCMAKE_SKIP_INSTALL_ALL_DEPENDENCY=ON \
    -DCMAKE_INSTALL_MESSAGE=NEVER \
    -DLLVM_DIR="$llvm_cmake_dir" \
    -DLLVM_TARGETS_TO_BUILD=PowerPC \
    -DLLD_ENABLE_BACKENDS=ELF \
    -DLLD_USE_VTUNE=OFF \
    -DLLVM_INCLUDE_TESTS=OFF \
    -DLLVM_ENABLE_WARNINGS=OFF \
    -DLLVM_ENABLE_PEDANTIC=OFF \
    -DLLVM_NO_DEAD_STRIP=ON \
    -DLINKER_SUPPORTS_RELR=FALSE \
    -DLINKER_SUPPORTS_COLOR_DIAGNOSTICS=FALSE \
    "${cmake_platform_args[@]}"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then
    cmake --build "$LLD_BUILD_DIR" --target clean
fi
cmake --build "$LLD_BUILD_DIR" --target lld "${cmake_parallel_args[@]}"
cmake --install "$LLD_BUILD_DIR"

lld="$llvm_dir/bin/ld.lld"
clang="$llvm_dir/bin/clang"
llvm_readelf="$llvm_dir/bin/llvm-readelf"
if [[ ! -x "$lld" ]]; then
    printf 'error: LLVM build did not produce LLD: %s\n' "$lld" >&2
    exit 1
fi
if [[ ! -x "$clang" ]]; then
    printf 'error: LLVM install did not produce Clang: %s\n' "$clang" >&2
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
# OpenBIOS ROM layout and the GNU-style options used by PPC-Firmware. Assemble
# with LLVM IAS directly so this stage has no dependency on GNU as.
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
"$clang" --target=powerpc-none-elf -c -x assembler \
    "$smoke_dir/layout.s" -o "$smoke_dir/layout.o"
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
"$lld" --warn-common -z noexecstack \
    -T "$smoke_dir/layout.ld" \
    -o "$smoke_dir/layout.elf" \
    --whole-archive "$smoke_dir/liblayout.a" --no-whole-archive

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
while IFS='|' read -r vaddr memsz segment_flags; do
    [[ -n "$vaddr" && -n "$memsz" ]] || continue
    ((load_count += 1))
    vaddr_num=$((vaddr))
    memsz_num=$((memsz))
    end_num=$((vaddr_num + memsz_num))
    if [[ "$segment_flags" == *W* && "$segment_flags" == *E* ]]; then
        printf 'error: LLD produced a writable and executable OpenBIOS LOAD segment\n' >&2
        exit 1
    fi
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
done < <(awk '$1 == "LOAD" { flags=""; for (i=7; i<NF; i++) flags=flags $i; print $3 "|" $6 "|" flags }' <<< "$layout_phdrs")
if ((load_count == 0 || start_loaded == 0 || hreset_loaded == 0)); then
    printf 'error: LLD did not map both OpenBIOS entry vectors into LOAD segments\n' >&2
    exit 1
fi

# LLD is now proven against the firmware layout. Publish it as the only linker
# behind both target-prefixed entry points and Clang's private tool route.
shim_dir="$TOOLCHAIN_DIR/libexec/powerpc-clang-gnu"
public_ld="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ld"
target_ld="$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/ld"
mkdir -p "$TOOLCHAIN_DIR/bin" "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin" "$shim_dir"
rm -f "$public_ld" "$target_ld" "$shim_dir/ld"
for tool in as ar ld nm objcopy objdump readelf strip ranlib; do
    rm -f "$shim_dir/${tool}.bfd"
done
ln -s "../llvm/bin/ld.lld" "$public_ld"
ln -s "../../bin/${TOOLCHAIN_TARGET}-ld" "$target_ld"
ln -s "../../llvm/bin/ld.lld" "$shim_dir/ld"

clang_driver="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-gcc"
reported_ld="$($clang_driver -print-prog-name=ld)"
if [[ "$reported_ld" != "$shim_dir/ld" ]]; then
    printf 'error: Clang is not routed through LLD: %s\n' "$reported_ld" >&2
    exit 1
fi
if ! "$public_ld" --version | grep -q 'LLD'; then
    printf 'error: public PowerPC linker does not resolve to LLD\n' >&2
    exit 1
fi
for tool in as ar ld nm objcopy objdump readelf strip ranlib; do
    if [[ -e "$shim_dir/${tool}.bfd" ]]; then
        printf 'error: obsolete binary-tool residue remains: %s\n' \
            "$shim_dir/${tool}.bfd" >&2
        exit 1
    fi
done

printf '%s\n' "$expected_lld_marker" > "$lld_marker"
printf '%s\n' \
    "Bootstrapped PowerPC compiler/linker: Clang + LLD ($llvm_revision)" \
    "LLVM source: QEMU submodule $LLVM_SUBMODULE_PATH" \
    "Assembler: Clang integrated assembler" \
    "LLD backends: ELF only" \
    "Compatibility prefix: $TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-"
