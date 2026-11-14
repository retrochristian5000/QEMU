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

# A failing ranlib must show the indexing stage, independent of where an
# operating system installs the external false utility.
printf '#!/bin/sh\nexit 1\n' > "$tmp/failing-ranlib"
chmod +x "$tmp/failing-ranlib"
if WHP_RANLIB_SEED="$tmp/failing-ranlib" WHP_ARCHIVE_VERBOSE=0 /bin/sh "$seed" --print-seed \
    >"$tmp/bad.out" 2>"$tmp/bad.err"; then
    printf '%s\n' 'error: unusable ranlib accepted' >&2
    exit 1
fi
[ ! -s "$tmp/bad.out" ]
grep -Fq "stage=index-archive; executable=$tmp/failing-ranlib" "$tmp/bad.err"

# The indexer returning success without writing a table must not pass.
# The rcS input archive has no index even if the selected ar is llvm-ar.
printf '#!/bin/sh\nexit 0\n' > "$tmp/noop-ranlib"
chmod +x "$tmp/noop-ranlib"
if WHP_RANLIB_SEED="$tmp/noop-ranlib" /bin/sh "$seed" --print-seed \
    >"$tmp/noop.out" 2>"$tmp/noop.err"; then
    printf '%s\n' 'error: no-op ranlib accepted unindexed archive' >&2
    exit 1
fi
[ ! -s "$tmp/noop.out" ]
grep -Fq 'stage=index-unchanged' "$tmp/noop.err"

# Verify the same index contract when llvm-ar is deliberately supplied as
# the native ar provider. This must not let llvm-ar's default auto-indexing
# conceal an ineffective ranlib. Optional on machines lacking LLVM tools.
if llvm_ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-seed 2>"$tmp/llvm-ar.err"); then
    WHP_AR_SEED="$llvm_ar" WHP_RANLIB_SEED="$selected" \
        /bin/sh "$seed" --check >"$tmp/llvm-pair.out" 2>"$tmp/llvm-pair.err" || {
        cat "$tmp/llvm-pair.err" >&2
        exit 1
    }
    if WHP_AR_SEED="$llvm_ar" WHP_RANLIB_SEED="$tmp/noop-ranlib" \
        /bin/sh "$seed" --print-seed >"$tmp/llvm-noop.out" 2>"$tmp/llvm-noop.err"; then
        printf '%s\n' 'error: no-op ranlib accepted llvm-ar archive' >&2
        exit 1
    fi
    [ ! -s "$tmp/llvm-noop.out" ]
    grep -Fq 'stage=index-unchanged' "$tmp/llvm-noop.err"
fi

if WHP_ARCHIVE_VERBOSE=invalid /bin/sh "$seed" --print-seed \
    >"$tmp/invalid.out" 2>"$tmp/invalid.err"; then
    printf '%s\n' 'error: invalid ranlib verbosity accepted' >&2
    exit 1
fi
[ ! -s "$tmp/invalid.out" ]
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/invalid.err"

printf '%s\n' 'WHP native ranlib diagnostics: verified'
