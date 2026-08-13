#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
base="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
as_stage="$ROOT/scripts/bootstrap-powerpc-llvm-as.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"
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

grep -Fq 'ASSEMBLER_SCHEMA=3' "$as_stage"
grep -Fq 'GNU_GAS=disabled' "$as_stage"
grep -Fq 'exec "$clang" --target=powerpc-none-elf -c -x assembler' "$as_stage"
if grep -Fq 'gnu_as=' "$as_stage" ||
   grep -Fq 'Retained GNU assembler oracle' "$as_stage" ||
   grep -Fq 'mv "$public_as" "$gnu_as"' "$as_stage"; then
    printf 'error: LLVM assembler stage still retains a GNU as fallback\n' >&2
    exit 1
fi

grep -Fq 'GNU as is not built or retained' "$orchestrator"

printf 'PowerPC LLVM assembler wiring: verified\n'
