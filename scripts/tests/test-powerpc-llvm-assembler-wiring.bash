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

# GNU binutils may still provide temporary linker/object utilities, but GAS
# and the profiling frontends are outside the OpenBIOS Clang contract.
grep -Fq -- '--disable-gas' "$base"
grep -Fq -- '--disable-gprof' "$base"
grep -Fq -- '--disable-gprofng' "$base"
grep -Fq 'BOOTSTRAP_SCHEMA=10' "$base"
grep -Fq 'GNU_GAS=disabled' "$base"
grep -Fq 'GNU_GPROF=disabled' "$base"
grep -Fq 'GNU_GPROFNG=disabled' "$base"
grep -Fq '[[ ! -e "$prefix/bin/${TOOLCHAIN_TARGET}-gprof" ]]' "$base"
grep -Fq '[[ ! -e "$prefix/$TOOLCHAIN_TARGET/bin/gprof" ]]' "$base"
if grep -Fq -- '-fno-integrated-as' "$base"; then
    printf 'error: PowerPC Clang wrapper still disables the integrated assembler\n' >&2
    exit 1
fi
if grep -Fq 'for tool in gcc as ar ld' "$base" ||
   grep -Fq 'for tool in as ar ld' "$base"; then
    printf 'error: PowerPC base toolchain still requires GNU as\n' >&2
    exit 1
fi
if grep -Fq 'ln -sf "../../bin/${TOOLCHAIN_TARGET}-as" "$shim_dir/as"' "$base"; then
    printf 'error: base bootstrap still wires a private GNU assembler shim\n' >&2
    exit 1
fi

grep -Fq 'LLD_SCHEMA=2' "$core"
grep -Fq 'ASSEMBLER=clang-integrated' "$core"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$core"
if grep -Fq 'Retained assembler: GNU as' "$core"; then
    printf 'error: LLD stage still declares GNU as as retained\n' >&2
    exit 1
fi

if [[ -e "$ROOT/scripts/bootstrap-powerpc-llvm-as.sh" ]] ||
   grep -Fq 'bootstrap-powerpc-llvm-as.sh' "$orchestrator"; then
    printf 'error: obsolete standalone PowerPC as stage remains wired\n' >&2
    exit 1
fi

grep -Fq 'rm -f "$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-as"' "$orchestrator"
grep -Fq 'rm -f "$TOOLCHAIN_DIR/$TOOLCHAIN_TARGET/bin/as"' "$orchestrator"
grep -Fq 'GNU as is not built, retained, or published' "$orchestrator"

grep -Fq 'powerpc_tools=(gcc ar ld nm strip ranlib)' "$build_openbios"
grep -Fq 'for tool in gcc ar ld nm strip ranlib; do' "$meson_openbios"
if grep -Fq 'powerpc_tools=(gcc as ar ld nm strip ranlib)' "$build_openbios" ||
   grep -Fq 'for tool in gcc as ar ld nm strip ranlib; do' "$meson_openbios"; then
    printf 'error: OpenBIOS still requires a standalone as command\n' >&2
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
