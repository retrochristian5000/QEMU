#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Verify ar selection, actual forwarding, and opt-in native provenance.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed=$root/seeds/ar.sh
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ar-observability.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

# An ordinary selection must return only the executable path on stdout.
selected=$(/bin/sh "$seed" --print-seed) || exit 1
[ -x "$selected" ]
[ -n "$selected" ]

# Detailed admission identifies the source, tool, compiler, host and proof.
WHP_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 /bin/sh "$seed" --check \
    >"$tmp/check.out" 2>"$tmp/check.err"
grep -Fq "WHP native ar seed: $selected" "$tmp/check.out"
grep -Fq "WHP ar validation: compiler=" "$tmp/check.out"
grep -Fq 'compile, archive, replace, index, link and execute passed' "$tmp/check.out"
grep -Fq "WHP ar selection: provider=WHP_AR_SEED; executable=$selected; native-probe=yes" \
    "$tmp/check.err"

# Diagnostics cannot corrupt the path emitted for callers using $(--print-seed).
printed=$(WHP_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" --print-seed 2>"$tmp/select.err")
[ "$printed" = "$selected" ]
grep -Fq 'native-probe=yes' "$tmp/select.err"

printf '%s\n' 'int whp_ar_forwarded(void) { return 19; }' >"$tmp/member.c"
/bin/sh "$root/seeds/cc.sh" -c "$tmp/member.c" -o "$tmp/member.o"
WHP_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" rcs "$tmp/libforwarded.a" "$tmp/member.o" \
    >"$tmp/forward.out" 2>"$tmp/forward.err"
[ ! -s "$tmp/forward.out" ]
[ "$(/bin/sh "$seed" t "$tmp/libforwarded.a")" = member.o ]
grep -Fq "WHP ar selection: provider=WHP_AR_SEED; executable=$selected; native-probe=no" \
    "$tmp/forward.err"
grep -Fq "WHP ar invocation: executable=$selected; operation=rcs; archive=$tmp/libforwarded.a; argument-count=3; admission=not-repeated" \
    "$tmp/forward.err"

# Without verbosity no forwarding trace belongs on stderr.
WHP_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=0 /bin/sh "$seed" t \
    "$tmp/libforwarded.a" >"$tmp/quiet.out" 2>"$tmp/quiet.err"
[ "$(cat "$tmp/quiet.out")" = member.o ]
[ ! -s "$tmp/quiet.err" ]

if WHP_ARCHIVE_VERBOSE=invalid /bin/sh "$seed" --print-seed \
    >"$tmp/invalid.out" 2>"$tmp/invalid.err"; then
    printf '%s\n' 'error: invalid archive verbosity accepted' >&2
    exit 1
fi
[ ! -s "$tmp/invalid.out" ]
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/invalid.err"

# A named non-archiver must not qualify as native merely because it is executable.
if WHP_AR_SEED=/bin/false /bin/sh "$seed" --check \
    >"$tmp/bad.out" 2>"$tmp/bad.err"; then
    printf '%s\n' 'error: non-native ar override accepted' >&2
    exit 1
fi
[ ! -s "$tmp/bad.out" ]

printf '%s\n' 'WHP native ar selection and forwarding diagnostics: verified'
