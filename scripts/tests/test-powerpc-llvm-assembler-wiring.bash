#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
base="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
nm_stage="$ROOT/scripts/bootstrap-powerpc-llvm-nm.sh"
strip_stage="$ROOT/scripts/bootstrap-powerpc-llvm-strip.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"
build_openbios="$ROOT/scripts/build-openbios.sh"
meson_openbios="$ROOT/scripts/meson-build-openbios.sh"
configure_openbios="$ROOT/scripts/whp-build/configure-openbios.bash"
openbios_target="$ROOT/roms/openbios/Makefile.target"
openbios_asm="$ROOT/roms/openbios/arch/ppc/Makefile.asm"
gitmodules="$ROOT/.gitmodules"

# Normal QEMU builds are pinned by the LLVM gitlink.  If .gitmodules names a
# tracking branch, it may only name the LLVM repository's default branch.
llvm_module="$(awk '
    /^\[submodule "toolchains\/llvm-project"\]$/ { in_llvm=1; next }
    /^\[submodule / { if (in_llvm) exit }
    in_llvm { print }
' "$gitmodules")"
llvm_branch="$(awk -F= '
    /^[[:space:]]*branch[[:space:]]*=/ {
        value=$2
        gsub(/^[[:space:]]+|[[:space:]]+$/, "", value)
        print value
        exit
    }
' <<< "$llvm_module")"
case "$llvm_branch" in
    ''|main) ;;
    *)
        printf 'error: LLVM submodule tracks a non-default branch: %s\n' "$llvm_branch" >&2
        exit 1
        ;;
esac
grep -Fq 'LLVM_GIT_REF="${POWERPC_LLVM_GIT_REF:-HEAD}"' "$base"
grep -Fq 'LLVM_GIT_COMMIT="${POWERPC_LLVM_GIT_COMMIT:-}"' "$base"

# The OpenBIOS Clang lane is LLVM-only.  In particular, do not keep a partial
# GNU BFD build: current binutils couples BFD to libsframe even when OpenBIOS
# never emits or consumes SFrame unwind metadata.
grep -Fq 'BOOTSTRAP_SCHEMA=11' "$base"
grep -Fq 'GNU_BINUTILS=disabled' "$base"
grep -Fq 'SFRAME=disabled' "$base"
for binutils_token in BINUTILS_VERSION BINUTILS_URL BINUTILS_SHA256 \
                      binutils_src build-binutils --disable-gas libsframe; do
    if grep -Fq -- "$binutils_token" "$base"; then
        printf 'error: LLVM-only Clang base still references %s\n' \
            "$binutils_token" >&2
        exit 1
    fi
done
if grep -Fq -- '-fno-integrated-as' "$base"; then
    printf 'error: PowerPC Clang wrapper still disables the integrated assembler\n' >&2
    exit 1
fi
if grep -Fq 'ln -sf "../../bin/${TOOLCHAIN_TARGET}-as" "$shim_dir/as"' "$base"; then
    printf 'error: base bootstrap still wires a private GNU assembler shim\n' >&2
    exit 1
fi

grep -Fq 'LLD_SCHEMA=3' "$core"
grep -Fq 'ASSEMBLER=clang-integrated' "$core"
grep -Fq 'GNU_BINUTILS=disabled' "$core"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$core"
if grep -Fq 'ld.bfd' "$core" || grep -Fq 'GNU ld' "$core"; then
    printf 'error: LLD stage still retains a GNU linker fallback\n' >&2
    exit 1
fi

if [[ -e "$ROOT/scripts/bootstrap-powerpc-llvm-as.sh" ]] ||
   grep -Fq 'bootstrap-powerpc-llvm-as.sh' "$orchestrator"; then
    printf 'error: obsolete standalone PowerPC as stage remains wired\n' >&2
    exit 1
fi

grep -Fq 'for tool in as objcopy objdump readelf; do' "$orchestrator"
grep -Fq 'rm -f "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-${tool}"' "$orchestrator"
grep -Fq 'rm -f "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/$tool"' "$orchestrator"

grep -Fq 'powerpc_tools=(gcc ar ld nm strip ranlib)' "$build_openbios"
grep -Fq 'for tool in gcc ar ld nm strip ranlib; do' "$meson_openbios"
if grep -Fq 'powerpc_tools=(gcc as ar ld nm strip ranlib)' "$build_openbios" ||
   grep -Fq 'for tool in gcc as ar ld nm strip ranlib; do' "$meson_openbios"; then
    printf 'error: OpenBIOS still requires a standalone as command\n' >&2
    exit 1
fi
if grep -Fq 'compiler_mode" == clang && "$source_mode" != release' \
       "$meson_openbios" ||
   grep -Fq 'compiler_mode" == clang && "$source_mode" != release' \
       "$configure_openbios"; then
    printf 'error: LLVM submodule lane is still coupled to GNU source mode\n' >&2
    exit 1
fi

grep -Fq 'CC     := $(TARGET)gcc' "$openbios_target"
grep -Fq '$(CC) -c -x assembler $@.s $(AS_FLAGS) -o $@' "$openbios_asm"
if grep -Fq 'AS     := $(TARGET)as' "$openbios_target" ||
   grep -Fq '$(AS) $@.s' "$openbios_asm"; then
    printf 'error: PPC-Firmware still dispatches assembly through as\n' >&2
    exit 1
fi

grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$nm_stage"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$strip_stage"
if grep -Fq 'public_as=' "$nm_stage" || grep -Fq 'public_as=' "$strip_stage"; then
    printf 'error: LLVM utility qualification still depends on public as\n' >&2
    exit 1
fi

printf 'PowerPC LLVM assembler wiring: verified\n'
