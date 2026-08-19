#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
OPENBIOS="$ROOT/roms/openbios"
ABI_TEST="$OPENBIOS/tests/test-ppc-context-abi.bash"

if [[ ! -f "$OPENBIOS/arch/ppc/qemu/context.h" ]]; then
    printf '%s\n' \
        'error: OpenBIOS submodule is not initialized for PPC context ABI tests.' \
        'run: git submodule update --init roms/openbios' >&2
    exit 1
fi
if [[ ! -f "$ABI_TEST" ]]; then
    printf '%s\n' \
        'error: pinned OpenBIOS revision lacks the PPC context ABI guard.' >&2
    exit 1
fi

grep -Fq 'unsigned long regs[35];' "$OPENBIOS/arch/ppc/qemu/context.h"
grep -Fq '#define PPC_STACK_ALIGNMENT 16' "$OPENBIOS/arch/ppc/qemu/context.c"
grep -Fq '#define SAVE_SPACE 156' "$OPENBIOS/arch/ppc/qemu/context.c"
grep -Fq '#define SAVE_SPACE 156' "$OPENBIOS/arch/ppc/qemu/switch.S"

bash "$ABI_TEST"

printf 'QEMU/OpenBIOS PPC context ABI: verified\n'
