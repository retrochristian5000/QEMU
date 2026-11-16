#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# GNU Gawk selection is distinct from the early POSIX AWK bridge.
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
selector="$root/seeds/gawk.sh"
generic="$root/seeds/awk.sh"
literal_awk="$root/scripts/whp-build/seed-bin/awk"
[[ -x "$selector" ]]
[[ "$("$selector" --whp-gawk-adapter-probe)" == whp-qemu-gawk-seed-adapter ]]

tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-gawk-seed.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT

# No fake banner or generic AWK adapter may qualify as GNU.
cat > "$tmp/banner-only" <<'BAD'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf 'GNU Awk 99.99\n'
    exit 0
fi
exit 0
BAD
chmod +x "$tmp/banner-only"
for bad in "$tmp/banner-only" "$generic" "$literal_awk" "$selector" /bin/false; do
    if WHP_GAWK_SEED="$bad" "$selector" --print-seed \
        >"$tmp/out" 2>"$tmp/err"; then
        printf 'error: invalid GNU Awk provider accepted: %s\n' "$bad" >&2
        exit 1
    fi
    [[ ! -s "$tmp/out" ]]
    grep -Fq 'does not name a working GNU Awk' "$tmp/err"
done

# A supplied invalid GNU provider must not fall back to a valid POSIX awk.
if WHP_GAWK_SEED="$tmp/banner-only" GAWK= \
    "$selector" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf 'error: invalid GNU override silently fell back\n' >&2
    exit 1
fi
[[ ! -s "$tmp/out" ]]

# The general AWK seed must still admit a native POSIX implementation.
native="$(WHP_AWK_SEED= AWK= "$generic" --print-seed)"
[[ -x "$native" ]]
WHP_AWK_SEED="$native" "$generic" --check >/dev/null

# GNU Awk may be optional on the runner. When present, validate both the
# explicit selector and locked forwarding without any managed source build.
if selected="$(WHP_GAWK_SEED= GAWK= "$selector" --print-seed 2>"$tmp/err")"; then
    [[ -x "$selected" ]]
    [[ "$(WHP_GAWK_SEED="$selected" "$selector" --print-seed)" == "$selected" ]]
    WHP_GAWK_SEED="$selected" "$selector" --check | \
        grep -Fq 'asorti, gensub verified'
    result="$(WHP_GAWK_SEED="$selected" WHP_GAWK_LOCKED=1 \
        "$selector" 'BEGIN { print gensub(/[0-9]+/, "#", "g", "v123") }')"
    [[ "$result" == 'v#' ]]
    if WHP_GAWK_SEED="$selected" WHP_GAWK_LOCKED=1 \
        "$selector" 'BEGIN { exit 7 }'; then
        printf 'error: GNU Awk adapter hid a failing exit status\n' >&2
        exit 1
    else
        [[ "$?" -eq 7 ]]
    fi
else
    grep -Fq 'no working GNU Awk found' "$tmp/err"
    printf '%s\n' 'GNU Awk runtime unavailable: optional runtime check skipped'
fi

# Locked command execution must never discover another provider.
if WHP_GAWK_SEED= WHP_GAWK_LOCKED=1 "$selector" \
    'BEGIN { print 1 }' >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: missing locked GNU Awk seed accepted' >&2
    exit 1
fi
grep -Fq 'locked Gawk has no independent executable' "$tmp/err"

printf '%s\n' 'WHP separate GNU Gawk seed policy: verified'
