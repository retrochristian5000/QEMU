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

# An inherited native AR_FOR_BUILD must not silently hide a different
# explicit WHP selection. Keep the winning selection and disclose the clash.
conflicting=$(WHP_AR_SEED="$selected" AR_FOR_BUILD=/bin/false \
    /bin/sh "$seed" --print-seed 2>"$tmp/conflict.err")
[ "$conflicting" = "$selected" ]
grep -Fq 'WHP_AR_SEED overrides conflicting AR_FOR_BUILD' "$tmp/conflict.err"
# Identical explicit aliases do not require a conflict warning.
WHP_AR_SEED="$selected" AR_FOR_BUILD="$selected" /bin/sh "$seed" --print-seed \
    >"$tmp/same.out" 2>"$tmp/same.err"
[ "$(cat "$tmp/same.out")" = "$selected" ]
! grep -Fq 'overrides conflicting' "$tmp/same.err"

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
grep -Fq 'stage=create-archive; executable=/bin/false' "$tmp/bad.err"

# A real tool error must be reported even without verbose mode; the failing
# child stderr must not disappear into /dev/null.
cat >"$tmp/broken-ar" <<'EOF'
#!/bin/sh
if [ "$1" = rc ]; then
    printf '%s\n' 'deliberate archive creation failure' >&2
    exit 42
fi
exec "$WHP_AR_TEST_REAL_AR" "$@"
EOF
chmod +x "$tmp/broken-ar"
if WHP_AR_TEST_REAL_AR="$selected" WHP_AR_SEED="$tmp/broken-ar" \
    WHP_ARCHIVE_VERBOSE=0 /bin/sh "$seed" --print-seed \
    >"$tmp/broken.out" 2>"$tmp/broken.err"; then
    printf '%s\n' 'error: broken archiver passed native probe' >&2
    exit 1
fi
[ ! -s "$tmp/broken.out" ]
grep -Fq 'stage=create-archive' "$tmp/broken.err"
grep -Fq 'exit-status=42' "$tmp/broken.err"
grep -Fq 'deliberate archive creation failure' "$tmp/broken.err"

printf '%s\n' 'WHP native ar selection and forwarding diagnostics: verified'
