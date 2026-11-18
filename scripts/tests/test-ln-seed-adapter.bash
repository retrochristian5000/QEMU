#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
seed="$root/seeds/ln.sh"
bridge="$root/scripts/whp-build/seed-bin/ln"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-ln-regression.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT

selected="$(env -u WHP_LN_SEED -u WHP_LN_LOCKED /bin/sh "$seed" --print-seed)"
[[ -x "$selected" ]]
[[ "$(WHP_LN_SEED="$selected" /bin/sh "$seed" --print-seed)" == "$selected" ]]
WHP_LN_SEED="$selected" /bin/sh "$seed" --check |
    grep -Fq 'symlink, dangling link, -sf, hardlink verified'

mkdir -p "$tmp/nested directory"
printf 'first\n' > "$tmp/nested directory/source file"
WHP_LN_SEED="$selected" WHP_LN_LOCKED=1 \
    "$bridge" -s 'source file' "$tmp/nested directory/symbolic link"
[[ -L "$tmp/nested directory/symbolic link" ]]
[[ "$(readlink "$tmp/nested directory/symbolic link")" == 'source file' ]]
[[ "$(cat "$tmp/nested directory/symbolic link")" == first ]]

# The PATH bridge, not a competing implementation, handles literal ln calls.
WHP_LN_SEED="$selected" WHP_LN_LOCKED=1 \
    PATH="$root/scripts/whp-build/seed-bin:$PATH" \
    /bin/sh -c 'ln -s "$1" "$2"' qemu-ln-smoke \
    'source file' "$tmp/nested directory/via-path"
[[ -L "$tmp/nested directory/via-path" ]]
[[ "$(cat "$tmp/nested directory/via-path")" == first ]]

# POSIX -f replaces an ordinary file; it must not quietly create a second file.
printf 'stale\n' > "$tmp/nested directory/replace"
WHP_LN_SEED="$selected" WHP_LN_LOCKED=1 \
    "$bridge" -sf 'source file' "$tmp/nested directory/replace"
[[ -L "$tmp/nested directory/replace" ]]
[[ "$(readlink "$tmp/nested directory/replace")" == 'source file' ]]

WHP_LN_SEED="$selected" WHP_LN_LOCKED=1 \
    "$bridge" "$tmp/nested directory/source file" "$tmp/hard copy"
printf 'shared\n' > "$tmp/hard copy"
[[ "$(cat "$tmp/nested directory/source file")" == shared ]]
rm "$tmp/nested directory/source file"
[[ "$(cat "$tmp/hard copy")" == shared ]]

# Explicit GNU Coreutils name is usable, but native ln retains preference.
mkdir -p "$tmp/tools with spaces"
cat > "$tmp/tools with spaces/gln" <<'FAKE'
#!/bin/sh
exec "$WHP_LN_TEST_PROVIDER" "$@"
FAKE
chmod +x "$tmp/tools with spaces/gln"
gnu="$(WHP_LN_TEST_PROVIDER="$selected" \
    WHP_LN_SEED="$tmp/tools with spaces/gln" \
    /bin/sh "$seed" --print-seed)"
[[ "$gnu" == "$tmp/tools with spaces/gln" ]]
native="$(PATH="$tmp/tools with spaces:$PATH" \
    env -u WHP_LN_SEED -u WHP_LN_LOCKED /bin/sh "$seed" --print-seed)"
[[ "$native" == "$selected" ]]

# Nonfunctional implementations must not qualify based only on exit zero.
cat > "$tmp/false-success-ln" <<'FAKE'
#!/bin/sh
exit 0
FAKE
chmod +x "$tmp/false-success-ln"
if WHP_LN_SEED="$tmp/false-success-ln" /bin/sh "$seed" --print-seed \
    > "$tmp/out" 2> "$tmp/error"; then
    printf '%s\n' 'error: false-success ln accepted' >&2
    exit 1
fi
grep -Fq 'WHP_LN_SEED is not a usable host ln' "$tmp/error"

# Invalid explicit choices and both adapter aliases fail closed.
ln -s "$seed" "$tmp/seed-alias"
ln -s "$bridge" "$tmp/bridge-alias"
for bad in /nonexistent/ln "$seed" "$bridge" \
    "$tmp/seed-alias" "$tmp/bridge-alias"; do
    if WHP_LN_SEED="$bad" /bin/sh "$seed" --print-seed \
        > "$tmp/out" 2> "$tmp/error"; then
        printf 'error: invalid ln seed accepted: %s\n' "$bad" >&2
        exit 1
    fi
    grep -Fq 'WHP_LN_SEED is not a usable host ln' "$tmp/error"
done
for runner in "$seed" "$bridge"; do
    if WHP_LN_LOCKED=1 WHP_LN_SEED= /bin/sh "$runner" -s source target \
        > "$tmp/out" 2> "$tmp/error"; then
        printf 'error: locked ln silently fell back to host ln\n' >&2
        exit 1
    fi
    grep -Fq 'locked ln has no usable seed' "$tmp/error"
done

# Verify first-stage wiring without changing Autoconf/Libtool's LN_S policy.
python3 - "$root/build.sh" <<'PY'
from pathlib import Path
import sys
build = Path(sys.argv[1]).read_text(encoding="utf-8")
assert 'WHP_LN_SEED=$("$SOURCE_DIR/seeds/ln.sh" --print-seed)' in build
assert 'WHP_LN_LOCKED=1' in build
assert 'export WHP_LN_SEED WHP_LN_LOCKED' in build
assert 'WHP_LN_BRIDGE="$SOURCE_DIR/scripts/whp-build/seed-bin/ln"' in build
assert build.index('WHP_LN_SEED=$("$SOURCE_DIR/seeds/ln.sh"') < build.index('whp_select_seed_git()')
assert 'LN_S=' not in build
PY
printf '%s\n' 'QEMU ln seed regression: passed'
