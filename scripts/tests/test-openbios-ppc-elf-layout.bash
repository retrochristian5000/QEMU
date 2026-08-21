#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
LDSCRIPT="$ROOT/roms/openbios/arch/ppc/qemu/ldscript"

if [[ ! -f "$LDSCRIPT" ]]; then
    echo "error: initialize roms/openbios before running this test" >&2
    exit 1
fi

# Source contract: GNU ld and LLD must receive the same explicit program-header
# layout rather than deriving different PT_LOADs from section permissions.
grep -Fxq 'ENTRY(_start)' "$LDSCRIPT"
grep -Fxq 'PHDRS' "$LDSCRIPT"
grep -Eq '^[[:space:]]*firmware[[:space:]]+PT_LOAD[[:space:]]+FLAGS\(7\);$' "$LDSCRIPT"
grep -Eq '^[[:space:]]*reset[[:space:]]+PT_LOAD[[:space:]]+FLAGS\(5\);$' "$LDSCRIPT"

# Optional artifact contract. The LLVM/OpenBIOS workflow passes the real
# LLD-linked firmware here so the program headers are checked behaviorally.
if (( $# > 0 )); then
    image=$1
    readelf=${OPENBIOS_READELF:-readelf}

    test -s "$image"
    header="$(LC_ALL=C "$readelf" -hW "$image")"
    phdrs="$(LC_ALL=C "$readelf" -lW "$image")"

    grep -Eq 'Class:[[:space:]]+ELF32' <<< "$header"
    grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$header"
    grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$header"
    grep -Eq 'Entry point address:[[:space:]]+0xfff00100' <<< "$header"

    mapfile -t load_vaddrs < <(
        awk '$1 == "LOAD" { print tolower($3) }' <<< "$phdrs"
    )
    if (( ${#load_vaddrs[@]} != 2 )); then
        printf 'error: expected 2 OpenBIOS PT_LOADs, found %d\n' \
            "${#load_vaddrs[@]}" >&2
        printf '%s\n' "$phdrs" >&2
        exit 1
    fi
    [[ "${load_vaddrs[0]}" == "0xfff00000" ]]
    [[ "${load_vaddrs[1]}" == "0xfffffffc" ]]
fi

printf 'OpenBIOS PPC ELF load ABI: verified\n'
