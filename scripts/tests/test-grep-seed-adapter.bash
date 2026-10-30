#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Check the native grep seed without building or modifying any source tree.
set -euo pipefail
ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
bridge="$ROOT/grep.sh"
shim="$ROOT/scripts/whp-build/seed-bin/grep"
test -x "$bridge" && test -x "$shim"

seed="$(WHP_GREP_SEED= GREP= "$bridge" --print-seed)"
test -x "$seed"
test "$(WHP_GREP_SEED="$seed" "$bridge" --print-seed)" = "$seed"
WHP_GREP_SEED="$seed" "$bridge" --check >/dev/null

test "$(printf 'alpha\nbeta\n' | WHP_GREP_SEED="$seed" "$bridge" -F -x beta)" = beta
test "$(printf 'a+b\n' | WHP_GREP_SEED="$seed" "$bridge" -E '^a\+b$')" = 'a+b'
test "$(printf 'Alpha\n' | WHP_GREP_SEED="$seed" "$bridge" -i -x alpha)" = Alpha
test "$(printf 'alpha\nbeta\n' | WHP_GREP_SEED="$seed" "$bridge" -v '^beta$')" = alpha
test "$(printf '%s\n' '-literal' | WHP_GREP_SEED="$seed" "$bridge" -F -e '-literal')" = '-literal'

# Literal PATH grep and $GREP have the same selected provenance.
actual="$(WHP_GREP_LOCKED=1 WHP_GREP_SEED="$seed" GREP="$seed" \
    PATH="${shim%/*}:$PATH" sh -c 'command -v grep')"
test "$actual" = "$shim"
test "$(printf 'alpha\nbeta\n' | WHP_GREP_LOCKED=1 WHP_GREP_SEED="$seed" \
    GREP="$seed" PATH="${shim%/*}:$PATH" grep -F -x beta)" = beta

# No match must remain exit 1, including via the shim; do not normalize it.
if printf 'alpha\n' | WHP_GREP_LOCKED=1 WHP_GREP_SEED="$seed" "$shim" -q zzz; then
    echo 'error: grep unexpectedly matched missing pattern' >&2; exit 1
else
    code=$?
    test "$code" -eq 1
fi

tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-grep-seed.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT
cat > "$tmp/fake-grep" <<'SH'
#!/bin/sh
if [ "$1" = --version ]; then
    echo 'grep (GNU grep) 99'
    exit 0
fi
exit 9
SH
chmod +x "$tmp/fake-grep"
if WHP_GREP_SEED="$tmp/fake-grep" "$bridge" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    echo 'error: fake version-only grep accepted' >&2; exit 1
fi
test ! -s "$tmp/out"
test "$(grep -c 'not a usable grep' "$tmp/err")" -eq 1

for bad in "$bridge" "$shim"; do
    if WHP_GREP_SEED="$bad" "$bridge" --print-seed >"$tmp/out" 2>"$tmp/err"; then
        echo 'error: recursive grep bridge accepted' >&2; exit 1
    fi
    test ! -s "$tmp/out"
    test "$(grep -c 'points back to the QEMU grep adapter' "$tmp/err")" -eq 1
done
if WHP_GREP_SEED= GREP="$tmp/fake-grep" "$bridge" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    echo 'error: invalid explicit GREP silently fell back' >&2; exit 1
fi
test ! -s "$tmp/out"

printf '%s\n' 'WHP grep seed bridge: verified'
