#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
LDSCRIPT="$ROOT/roms/openbios/arch/ppc/qemu/ldscript"

if [[ ! -f "$LDSCRIPT" ]]; then
    echo "error: initialize roms/openbios before running this test" >&2
    exit 1
fi

# Source contract: keep executable code, constants, writable data, and the
# detached reset vector in separate permission domains.  Do not collapse the
# normal firmware into an RWE PT_LOAD just to match GNU ld's legacy shape.
grep -Fxq 'ENTRY(_start)' "$LDSCRIPT"
grep -Fxq 'PHDRS' "$LDSCRIPT"
grep -Eq '^[[:space:]]*text[[:space:]]+PT_LOAD[[:space:]]+FLAGS\(5\);$' "$LDSCRIPT"
grep -Eq '^[[:space:]]*rodata[[:space:]]+PT_LOAD[[:space:]]+FLAGS\(4\);$' "$LDSCRIPT"
grep -Eq '^[[:space:]]*data[[:space:]]+PT_LOAD[[:space:]]+FLAGS\(6\);$' "$LDSCRIPT"
grep -Eq '^[[:space:]]*reset[[:space:]]+PT_LOAD[[:space:]]+FLAGS\(5\);$' "$LDSCRIPT"
! grep -Eq 'PT_LOAD[[:space:]]+FLAGS\(7\)' "$LDSCRIPT"

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

    mapfile -t load_lines < <(awk '$1 == "LOAD" { print }' <<< "$phdrs")
    if (( ${#load_lines[@]} != 4 )); then
        printf 'error: expected 4 W^X-safe OpenBIOS PT_LOADs, found %d\n' \
            "${#load_lines[@]}" >&2
        printf '%s\n' "$phdrs" >&2
        exit 1
    fi

    mapfile -t load_vaddrs < <(
        awk '$1 == "LOAD" { print tolower($3) }' <<< "$phdrs"
    )
    [[ "${load_vaddrs[0]}" == "0xfff00000" ]]
    [[ "${load_vaddrs[3]}" == "0xfffffffc" ]]

    while IFS= read -r line; do
        flags="$(awk '{ flags=""; for (i=7; i<NF; i++) flags=flags $i; print flags }' <<< "$line")"
        if [[ "$flags" == *W* && "$flags" == *E* ]]; then
            printf 'error: OpenBIOS LOAD is writable and executable: %s\n' \
                "$line" >&2
            exit 1
        fi
    done <<< "$(printf '%s\n' "${load_lines[@]}")"
fi

printf 'OpenBIOS PPC W^X ELF load ABI: verified\n'
