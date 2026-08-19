#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
OPENBIOS="$ROOT/roms/openbios"
CLANG_BOOTSTRAP="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"

if [[ ! -f "$OPENBIOS/libgcc/build.xml" ]]; then
    printf '%s\n' \
        'error: OpenBIOS submodule is not initialized for Clang ABI tests.' \
        'run: git submodule update --init roms/openbios' >&2
    exit 1
fi

# Clang's 32-bit PowerPC lowering can call __moddi3 for signed long long
# remainder. The pinned OpenBIOS runtime must provide and link that helper.
test -f "$OPENBIOS/libgcc/__moddi3.c"
grep -Fq '<object source="__moddi3.c"/>' "$OPENBIOS/libgcc/build.xml"
grep -Fq 'int64_t __moddi3(int64_t num, int64_t den);' \
    "$OPENBIOS/libgcc/libgcc.h"
grep -Fq '__udivmoddi4(unum, uden, &rem)' "$OPENBIOS/libgcc/__moddi3.c"

# These are GCC PowerPC switches that Clang does not implement. Keep their
# compatibility translation explicit in the project-owned compiler driver.
for flag in -mcall-sysv-noeabi -msdata=none -G0; do
    grep -Fq -- "$flag" "$CLANG_BOOTSTRAP"
done
grep -Fq -- '--target=powerpc-none-elf' "$CLANG_BOOTSTRAP"
grep -Fq -- '-fintegrated-as' "$CLANG_BOOTSTRAP"

# When a host Clang is available, verify the runtime ABI assumption itself
# rather than only the source wiring. This is intentionally a tiny compiler
# probe so it remains independent of the full LLVM bootstrap.
if command -v clang >/dev/null 2>&1 && command -v nm >/dev/null 2>&1; then
    scratch="$(mktemp -d "${TMPDIR:-/tmp}/qemu-openbios-clang-abi.XXXXXX")"
    trap 'rm -rf "$scratch"' EXIT
    cat > "$scratch/remainder.c" <<'SOURCE'
long long whp_signed_remainder(long long value, long long divisor)
{
    return value % divisor;
}
SOURCE
    clang --target=powerpc-none-elf -m32 -mcpu=604 -msoft-float \
        -ffreestanding -fno-pic -fno-pie -O0 \
        -c "$scratch/remainder.c" -o "$scratch/remainder.o"
    if ! nm -u "$scratch/remainder.o" | grep -Eq '(^|[[:space:]])__moddi3$'; then
        printf '%s\n' \
            'error: Clang PowerPC runtime lowering changed; re-audit OpenBIOS helpers.' >&2
        exit 1
    fi
fi

printf 'QEMU/OpenBIOS Clang runtime ABI: verified\n'
