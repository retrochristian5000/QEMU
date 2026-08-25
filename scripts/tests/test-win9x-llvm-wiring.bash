#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
profile="$root/scripts/bootstrap-win9x-clang.sh"
triple_names="$root/toolchains/llvm-project/llvm/include/llvm/TargetParser/TripleName.def"

[[ -f "$profile" ]] || {
    printf 'error: Win9x LLVM bootstrap is missing: %s\n' "$profile" >&2
    exit 1
}
[[ -f "$triple_names" ]] || {
    printf 'error: LLVM triple table is missing: %s\n' "$triple_names" >&2
    exit 1
}

grep -Fq 'WIN9X_TARGET="${WIN9X_TOOLCHAIN_TARGET:-i386-pc-win9x}"' "$profile"
grep -Fq -- '-DLLD_ENABLE_BACKENDS=ELF;COFF' "$profile"
# The generated wrapper must preserve this variable for expansion when the
# wrapper runs, so the generator source contains an escaped dollar sign.
grep -Fq -- '--target="\$WIN9X_TARGET"' "$profile"
grep -Fq -- '-march=i386' "$profile"
grep -Fq '/machine:x86' "$profile"
grep -Fq '/subsystem:windows,4.0' "$profile"
grep -Fq '/nodefaultlib' "$profile"
grep -Fq 'TRIPLE_OS_ALIAS(Win32, "win9x")' "$triple_names"

printf 'Win9x LLVM target wiring looks correct\n'
