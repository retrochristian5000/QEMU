#!/usr/bin/env bash
set -euo pipefail

binary=${1:?usage: test-cdrom-hdc.bash /path/to/qemu-system-i386}

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT

disk="$tmpdir/hdc.img"
iso="$tmpdir/cdrom.iso"
truncate -s 1M "$disk"
truncate -s 64K "$iso"

run_qmp_case()
{
    local name=$1
    shift
    local out="$tmpdir/$name.qmp"

    printf '%s\n' \
        '{"execute":"qmp_capabilities"}' \
        '{"execute":"query-block"}' \
        '{"execute":"quit"}' |
        "$binary" \
            -machine pc \
            -display none \
            -monitor none \
            -serial none \
            -net none \
            -S \
            -qmp stdio \
            "$@" \
            >"$out"

    printf '%s\n' "$out"
}

check_case()
{
    local out=$1
    local want_disk=$2
    local want_cd=$3

    python3 - "$out" "$want_disk" "$want_cd" <<'PY'
import json
import os
import sys

path, want_disk, want_cd = sys.argv[1:]
blocks = None
with open(path, encoding="utf-8") as stream:
    for line in stream:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = message.get("return")
        if isinstance(value, list):
            blocks = value

assert blocks is not None, "query-block response missing"

by_file = {}
for block in blocks:
    inserted = block.get("inserted") or {}
    filename = inserted.get("file")
    if filename:
        by_file[os.path.basename(filename)] = block.get("device")

assert by_file.get(os.path.basename(want_disk)) == "ide1-hd0", by_file
assert by_file.get(os.path.basename(want_cd)) == "ide1-cd1", by_file
PY
}

# Preserve the historical -cdrom placement when its preferred slot is free.
cd_only=$(run_qmp_case cdrom-only -cdrom "$iso")
python3 - "$cd_only" "$iso" <<'PY'
import json
import os
import sys

path, iso = sys.argv[1:]
blocks = None
with open(path, encoding="utf-8") as stream:
    for line in stream:
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        value = message.get("return")
        if isinstance(value, list):
            blocks = value

assert blocks is not None, "query-block response missing"
for block in blocks:
    inserted = block.get("inserted") or {}
    filename = inserted.get("file")
    if filename and os.path.basename(filename) == os.path.basename(iso):
        assert block.get("device") == "ide1-cd0", block
        break
else:
    raise AssertionError("CD-ROM image missing from query-block")
PY

# A fixed -hdc owns secondary-master; -cdrom must relocate in either CLI order.
hdc_first=$(run_qmp_case hdc-first -hdc "$disk" -cdrom "$iso")
check_case "$hdc_first" "$disk" "$iso"

cdrom_first=$(run_qmp_case cdrom-first -cdrom "$iso" -hdc "$disk")
check_case "$cdrom_first" "$disk" "$iso"

echo "-hdc / -cdrom coexistence: verified"
