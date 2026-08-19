#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"

for required in clang grep mktemp; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: required PowerPC ABI mode test tool is missing: %s\n' \
            "$required" >&2
        exit 1
    fi
done

if command -v llvm-readelf >/dev/null 2>&1; then
    READELF=llvm-readelf
elif command -v readelf >/dev/null 2>&1; then
    READELF=readelf
else
    printf 'error: llvm-readelf or readelf is required\n' >&2
    exit 1
fi

# switch-arch's qemu-ppc64 recipe carries the historical GNU-as selector
# -Wa,-a64. Clang's integrated assembler derives 64-bit mode from -m64 and
# rejects that GNU-as option on current LLVM. The compatibility driver must
# consume it just like the other GCC-only OpenBIOS policy switches.
grep -Fq -- '-Wa,-a64' "$BOOTSTRAP"
grep -Eq -- '-mcall-sysv-noeabi\|-msdata=none\|-G0\|.*-Wa,-a64' "$BOOTSTRAP"
grep -Fq -- '--target=powerpc-none-elf' "$BOOTSTRAP"
grep -Fq -- '-fintegrated-as' "$BOOTSTRAP"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/whp-powerpc-clang-abi.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT

cat > "$scratch/probe.c" <<'SOURCE'
#if !defined(__powerpc__) && !defined(__POWERPC__) && !defined(__PPC__)
#error compiler is not targeting PowerPC
#endif
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
#error PowerPC OpenBIOS compiler must generate big-endian code
#endif
#ifdef EXPECT_PPC64
# if !defined(__powerpc64__)
#  error PPC64 mode did not define __powerpc64__
# endif
_Static_assert(__SIZEOF_POINTER__ == 8, "PPC64 pointer ABI must be 64-bit");
#else
# if defined(__powerpc64__)
#  error PPC32 mode unexpectedly defined __powerpc64__
# endif
_Static_assert(__SIZEOF_POINTER__ == 4, "PPC32 pointer ABI must be 32-bit");
#endif
int whp_powerpc_abi_probe(void) { return 0; }
SOURCE

clang --target=powerpc-none-elf -fintegrated-as \
    -m32 -mcpu=604 -msoft-float -ffreestanding -fno-pic -fno-pie \
    -c "$scratch/probe.c" -o "$scratch/ppc32.o"

# This is the command after the compatibility driver removes -Wa,-a64.
clang --target=powerpc-none-elf -fintegrated-as \
    -m64 -mcpu=970 -mno-altivec -msoft-float \
    -ffreestanding -fno-pic -fno-pie -DEXPECT_PPC64 \
    -c "$scratch/probe.c" -o "$scratch/ppc64.o"

"$READELF" -h "$scratch/ppc32.o" > "$scratch/ppc32.elf"
"$READELF" -h "$scratch/ppc64.o" > "$scratch/ppc64.elf"

grep -Eq 'Class:.*ELF32' "$scratch/ppc32.elf"
grep -Eq 'Data:.*big endian' "$scratch/ppc32.elf"
grep -Eq 'Machine:.*PowerPC([^6]|$)' "$scratch/ppc32.elf"

grep -Eq 'Class:.*ELF64' "$scratch/ppc64.elf"
grep -Eq 'Data:.*big endian' "$scratch/ppc64.elf"
grep -Eq 'Machine:.*PowerPC64' "$scratch/ppc64.elf"

printf 'PowerPC Clang PPC32/PPC64 big-endian ABI modes: verified\n'
