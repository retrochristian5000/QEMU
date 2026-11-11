#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/qemu-version-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

git -C "$tmp" init -q
git -C "$tmp" config user.email qemu-version-test@example.invalid
git -C "$tmp" config user.name 'QEMU version test'
printf 'probe\n' > "$tmp/probe"
git -C "$tmp" add probe
git -C "$tmp" commit -qm probe

"$ROOT/scripts/qemu-version.sh" "$tmp" '' '11.0.0' \
    > "$tmp/qemu-version.h" 2> "$tmp/qemu-version.err"

grep -Fxq '#define QEMU_PKGVERSION ""' "$tmp/qemu-version.h"
grep -Fxq '#define QEMU_FULL_VERSION "11.0.0"' "$tmp/qemu-version.h"
if [[ -s "$tmp/qemu-version.err" ]]; then
    printf '%s\n' 'qemu-version.sh emitted stderr for a valid tagless checkout:' >&2
    cat "$tmp/qemu-version.err" >&2
    exit 1
fi

printf 'qemu version tagless checkout: passed\n'
