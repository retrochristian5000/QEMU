#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Offline native AWK bridge regression: never change the source checkout.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
bridge="$ROOT/seeds/awk.sh"
shim="$ROOT/scripts/whp-build/seed-bin/awk"
test -x "$bridge" && test -x "$shim"
test "$("$bridge" --whp-awk-adapter-probe)" = whp-qemu-awk-seed-adapter
test "$("$shim" --whp-awk-adapter-probe)" = whp-qemu-awk-seed-adapter

seed="$(WHP_AWK_SEED= AWK= "$bridge" --print-seed)"
test -x "$seed"
test "$(WHP_AWK_SEED="$seed" "$bridge" --print-seed)" = "$seed"
WHP_AWK_SEED="$seed" "$bridge" --check >/dev/null

# Exercise the field, array, counter, regex and substitution operations used
# by QEMU's shell menuconfig and pre-configure OpenBIOS/LLVM helpers.
test "$(printf 'alpha|beta\n' |
    WHP_AWK_SEED="$seed" "$bridge" -F '|' -v wanted=beta \
        '$2 == wanted { printf "%s:%d:%d\n", $1, NF, NR }')" = 'alpha:2:1'
test "$(printf 'A/B C\n' |
    WHP_AWK_SEED="$seed" "$bridge" '{ gsub(/[\/ ]/, "-", $0); print }')" = A-B-C
test "$(printf 'one\ntwo\n' |
    WHP_AWK_SEED="$seed" "$bridge" '
        BEGIN { n=split("x,y", a, ","); if (n!=2 || a[2]!="y") exit 3 }
        FNR==2 && $0 ~ /^two$/ { print FNR }
    ')" = 2

# Literal awk and $AWK must route to the identical verified native binary.
test "$(WHP_AWK_LOCKED=1 WHP_AWK_SEED="$seed" AWK="$seed" \
    PATH="${shim%/*}:$PATH" sh -c 'command -v awk')" = "$shim"
test "$(printf 'a:b\n' |
    WHP_AWK_LOCKED=1 WHP_AWK_SEED="$seed" AWK="$seed" \
        PATH="${shim%/*}:$PATH" awk -F: '{print $2}')" = b

# Exact AWK failure codes must not be normalized by the bridge or shim.
for runner in "$bridge" "$shim"; do
    if WHP_AWK_LOCKED=1 WHP_AWK_SEED="$seed" "$runner" 'BEGIN { exit 7 }'; then
        echo 'error: AWK failure exit code was hidden' >&2
        exit 1
    else
        code=$?
        test "$code" -eq 7
    fi
done

tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-awk-seed.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT

# The POSIX shell menu really consumes the literal AWK shim before configure.
WHP_AWK_LOCKED=1 WHP_AWK_SEED="$seed" AWK="$seed" \
    PATH="${shim%/*}:$PATH" \
    sh "$ROOT/scripts/whp-config/menuconfig.sh" "$tmp/.whpconfig" --dump \
    > "$tmp/menu"
grep -Fq 'Host features' "$tmp/menu"
grep -Fq 'BOOTSTRAP_PYTHON' "$tmp/menu"

cat > "$tmp/fake-awk" <<'SH'
#!/bin/sh
if [ "$1" = --version ]; then echo 'GNU Awk 99'; exit 0; fi
exit 9
SH
chmod +x "$tmp/fake-awk"
if WHP_AWK_SEED="$tmp/fake-awk" "$bridge" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    echo 'error: fake AWK without semantics was admitted' >&2
    exit 1
fi
test ! -s "$tmp/out"
grep -Fq 'not a usable AWK' "$tmp/err"

for bad in "$bridge" "$shim"; do
    if WHP_AWK_SEED="$bad" "$bridge" --print-seed >"$tmp/out" 2>"$tmp/err"; then
        echo 'error: recursive AWK bridge accepted' >&2
        exit 1
    fi
    test ! -s "$tmp/out"
    grep -Fq 'points back to the QEMU awk bridge' "$tmp/err"
done

# An invalid explicit AWK must never be ignored in favor of a different host.
if WHP_AWK_SEED= AWK="$tmp/fake-awk" "$bridge" --print-seed \
    >"$tmp/out" 2>"$tmp/err"; then
    echo 'error: invalid explicitly selected AWK silently fell back' >&2
    exit 1
fi
test ! -s "$tmp/out"

# The locked launcher must reject a missing seed and a loop to itself.
if WHP_AWK_LOCKED=1 WHP_AWK_SEED="$shim" "$shim" 'BEGIN {print 1}' \
    >"$tmp/out" 2>"$tmp/err"; then
    echo 'error: locked AWK launcher recursed' >&2
    exit 1
fi
grep -Fq 'locked AWK points to the awk bridge' "$tmp/err"

printf '%s\n' 'WHP awk seed bridge: verified'
