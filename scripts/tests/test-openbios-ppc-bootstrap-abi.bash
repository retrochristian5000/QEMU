#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
OPENBIOS="$ROOT/roms/openbios"
ABI_TEST="$OPENBIOS/tests/test-ppc-bootstrap-abi.bash"
SWITCH_ARCH="$OPENBIOS/config/scripts/switch-arch"
PPC_TYPES="$OPENBIOS/include/arch/ppc/types.h"

if [[ ! -f "$SWITCH_ARCH" ]]; then
    printf '%s\n' \
        'error: OpenBIOS submodule is not initialized for PPC bootstrap ABI tests.' \
        'run: git submodule update --init roms/openbios' >&2
    exit 1
fi
if [[ ! -f "$ABI_TEST" ]]; then
    printf '%s\n' \
        'error: pinned OpenBIOS revision lacks the PPC bootstrap ABI guard.' >&2
    exit 1
fi

grep -Fq 'cellbits()' "$SWITCH_ARCH"
grep -Fq 'targetlongbits=$(cellbits $target)' "$SWITCH_ARCH"
grep -Eq '^typedef[[:space:]]+uint32_t[[:space:]]+ucell;' "$PPC_TYPES"
grep -Eq '^#define[[:space:]]+BITS[[:space:]]+32$' "$PPC_TYPES"

bash "$ABI_TEST"

printf 'QEMU/OpenBIOS PPC bootstrap width/endian ABI: verified\n'
