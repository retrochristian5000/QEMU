#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
scratch="$(mktemp -d)"
trap 'rm -rf "$scratch"' EXIT
# Exercise the production layout checks using synthetic readelf rows.
awk '/^load_count=0$/ {active=1} /^mkdir -p "\$\(dirname "\$OPENBIOS_OUTPUT"\)"$/ {active=0} active' \
    "$root/scripts/build-openbios.bash" > "$scratch/check.bash"
grep -q '^load_count=0$' "$scratch/check.bash"
grep -q 'file_end >= 0xfff00104' "$scratch/check.bash"
check()
{
    local rows="$1"
    (
        start_address=0xfff00200
        start_value=$((start_address))
        elf_entry_address=$start_address
        elf_entry_value=$start_value
        OPENBIOS_FIRMWARE_VALIDATION=compatible
        program_headers="$rows"
        source "$scratch/check.bash"
    )
}
valid='  LOAD 0x1000 0xfff00000 0xfff00000 0x00300 0x00300 R E 0x1000'
check "$valid"
for invalid in \
    '  LOAD 0x1000 0xfff00200 0xfff00200 0x00100 0x00100 R E 0x1000' \
    '  LOAD 0x1000 0xfff00000 0xfff00000 0x00102 0x00300 R E 0x1000' \
    '  LOAD 0x1000 0xfff00000 0xfff00000 0x00300 0x00300 RW 0x1000' \
    '  LOAD 0x1000 0xfff00000 0xfff01000 0x00300 0x00300 R E 0x1000'; do
    if check "$invalid" >/dev/null 2>&1; then
        printf 'error: accepted invalid OpenBIOS layout: %s\n' "$invalid" >&2
        exit 1
    fi
done
printf '%s\n' 'OpenBIOS reset layout checks passed'
