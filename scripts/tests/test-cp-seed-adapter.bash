#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
seed="$root/seeds/cp.sh"
bridge="$root/scripts/whp-build/seed-bin/cp"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-cp-regression.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT

# The real selected implementation handles basic, recursive, and -p copies.
selected="$(env -u WHP_CP_SEED -u WHP_CP_LOCKED "$seed" --print-seed)"
[[ -x "$selected" ]]
[[ "$(WHP_CP_SEED="$selected" "$seed" --print-seed)" == "$selected" ]]
WHP_CP_SEED="$selected" "$seed" --check | grep -Fq 'WHP cp seed:'
printf 'payload\n' > "$tmp/in"
WHP_CP_SEED="$selected" WHP_CP_LOCKED=1 "$bridge" "$tmp/in" "$tmp/out"
[[ "$(cat "$tmp/out")" == payload ]]

# GNU Coreutils' g-prefixed command is an alternative only when explicitly
# selected or after the native candidate list fails. Keep native precedence.
mkdir -p "$tmp/gnu-bin"
cat > "$tmp/gnu-bin/gcp" <<'GNUCP'
#!/bin/sh
exec "$WHP_CP_TEST_PROVIDER" "$@"
GNUCP
chmod +x "$tmp/gnu-bin/gcp"
gnu_cp="$(PATH="$tmp/gnu-bin:$PATH" WHP_CP_TEST_PROVIDER="$selected" \
    WHP_CP_SEED=gcp "$seed" --print-seed)"
[[ "$gnu_cp" == "$tmp/gnu-bin/gcp" ]]
PATH="$tmp/gnu-bin:$PATH" WHP_CP_TEST_PROVIDER="$selected" \
    WHP_CP_SEED="$gnu_cp" WHP_CP_LOCKED=1 \
    "$bridge" "$tmp/in" "$tmp/gnu-out"
[[ "$(cat "$tmp/gnu-out")" == payload ]]
native_with_gnu="$(PATH="$tmp/gnu-bin:$PATH" \
    env -u WHP_CP_SEED -u WHP_CP_LOCKED "$seed" --print-seed)"
[[ "$native_with_gnu" == "$selected" ]]


# An invalid explicit override fails closed; never silently selects /bin/cp.
if WHP_CP_SEED=/no/such/cp "$seed" --print-seed >"$tmp/out" 2>"$tmp/error"; then
    echo 'error: invalid cp override unexpectedly accepted' >&2
    exit 1
fi
grep -Fq 'WHP_CP_SEED is not a usable host cp' "$tmp/error"

# A lost locked seed must not cause the adapter to discover a different cp.
for runner in "$seed" "$bridge"; do
    if WHP_CP_LOCKED=1 WHP_CP_SEED= "$runner" "$tmp/in" "$tmp/unexpected" >"$tmp/out" 2>"$tmp/error"; then
        echo 'error: locked cp without a selected seed was accepted' >&2
        exit 1
    fi
done
if WHP_CP_LOCKED=1 WHP_CP_SEED= "$seed" "$tmp/in" "$tmp/unexpected" >"$tmp/out" 2>"$tmp/error"; then
    echo 'error: cp seed silently fell back to a host tool' >&2
    exit 1
fi
grep -Fq 'locked cp has no selected seed' "$tmp/error"

# Neither bridge nor seed may be used as its own underlying implementation.
for bad in "$seed" "$bridge"; do
    if WHP_CP_SEED="$bad" "$seed" --print-seed >"$tmp/out" 2>"$tmp/error"; then
        echo 'error: recursive cp seed unexpectedly accepted' >&2
        exit 1
    fi
done

# The wrapper is a pure exec of the locked command, retaining argv semantics.
mkdir "$tmp/source"
printf 'nested\n' > "$tmp/source/entry"
WHP_CP_SEED="$selected" WHP_CP_LOCKED=1 "$bridge" -R "$tmp/source" "$tmp/tree"
[[ "$(cat "$tmp/tree/entry")" == nested ]]

# The root bootstrap binds the seed once before the source updater.
python3 - "$root/build.sh" <<'PY'
from pathlib import Path
import sys
content = Path(sys.argv[1]).read_text()
assert 'WHP_CP_SEED=$("$SOURCE_DIR/seeds/cp.sh" --print-seed)' in content
assert 'WHP_CP_LOCKED=1' in content
assert 'export WHP_CP_SEED WHP_CP_LOCKED' in content
assert content.index('WHP_CP_SEED=$("$SOURCE_DIR/seeds/cp.sh"') < content.index('whp_select_seed_git()')
PY
echo 'QEMU cp seed regression: passed'
