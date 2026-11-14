#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Verify native ranlib selection, stdout cleanliness and failure diagnostics.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed=$root/seeds/ranlib.sh
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ranlib-observability.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

selected=$(/bin/sh "$seed" --print-seed) || exit 1
[ -x "$selected" ]
WHP_RANLIB_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" --check >"$tmp/check.out" 2>"$tmp/check.err"
grep -Fq "WHP native ranlib seed: $selected" "$tmp/check.out"
grep -Fq 'native archive create, index, link and execute passed' "$tmp/check.out"
grep -Fq "WHP ranlib selection: provider=WHP_RANLIB_SEED; executable=$selected; native-probe=yes" \
    "$tmp/check.err"

# Retain explicit native precedence while surfacing contradictory aliases.
conflicting=$(WHP_RANLIB_SEED="$selected" RANLIB_FOR_BUILD=/bin/false \
    /bin/sh "$seed" --print-seed 2>"$tmp/conflict.err")
[ "$conflicting" = "$selected" ]
grep -Fq 'WHP_RANLIB_SEED overrides conflicting RANLIB_FOR_BUILD' "$tmp/conflict.err"
WHP_RANLIB_SEED="$selected" RANLIB_FOR_BUILD="$selected" \
    /bin/sh "$seed" --print-seed >"$tmp/same.out" 2>"$tmp/same.err"
[ "$(cat "$tmp/same.out")" = "$selected" ]
! grep -Fq 'overrides conflicting' "$tmp/same.err"

# When the seed path is captured, verbosity must never contaminate stdout.
printed=$(WHP_RANLIB_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" --print-seed 2>"$tmp/select.err")
[ "$printed" = "$selected" ]
grep -Fq 'native-probe=yes' "$tmp/select.err"

# An executable that cannot index an archive must fail with a named stage,
# not merely a blank response or an unrelated Perl error.
if WHP_RANLIB_SEED=/bin/false WHP_ARCHIVE_VERBOSE=0 /bin/sh "$seed" --print-seed \
    >"$tmp/bad.out" 2>"$tmp/bad.err"; then
    printf '%s\n' 'error: unusable ranlib accepted' >&2
    exit 1
fi
[ ! -s "$tmp/bad.out" ]
grep -Fq 'stage=index-archive; executable=/bin/false' "$tmp/bad.err"

if WHP_ARCHIVE_VERBOSE=invalid /bin/sh "$seed" --print-seed \
    >"$tmp/invalid.out" 2>"$tmp/invalid.err"; then
    printf '%s\n' 'error: invalid ranlib verbosity accepted' >&2
    exit 1
fi
[ ! -s "$tmp/invalid.out" ]
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/invalid.err"

printf '%s\n' 'WHP native ranlib diagnostics: verified'
