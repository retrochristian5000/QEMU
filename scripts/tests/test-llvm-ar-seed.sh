#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Standalone host LLVM ar seed regression (no QEMU or managed LLVM build).
set -eu
root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed=$root/seeds/llvm-ar.sh
[ "$(/bin/sh "$seed" --whp-llvm-ar-adapter-probe)" = whp-qemu-llvm-ar-seed-adapter ]
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-llvm-ar-test.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

if WHP_ARCHIVE_VERBOSE=invalid /bin/sh "$seed" --print-seed \
    >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: invalid archive verbosity accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/err"

# A selected archiver is never inferred from an invalid explicit override.
for bad in /bin/false "$seed"; do
    if WHP_LLVM_AR_SEED="$bad" /bin/sh "$seed" --print-seed > "$tmp/out" 2> "$tmp/err"; then
        printf 'error: invalid LLVM ar override accepted: %s\n' "$bad" >&2
        exit 1
    fi
    [ ! -s "$tmp/out" ]
done

# A version banner alone must not admit an archiver that cannot create objects.
cat > "$tmp/banner-only" <<'EOF'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'LLVM version 99.0.0'
fi
exit 0
EOF
chmod +x "$tmp/banner-only"
if WHP_LLVM_AR_SEED="$tmp/banner-only" /bin/sh "$seed" --print-seed > "$tmp/out" 2> "$tmp/err"; then
    printf '%s\n' 'error: version-only llvm-ar accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]

# Optional means not installed is allowed, but an installed broken tool is not.
if ! selected=$(/bin/sh "$seed" --print-seed 2> "$tmp/err"); then
    for name in llvm-ar llvm-ar-22 llvm-ar-21 llvm-ar-20 llvm-ar-19 llvm-ar-18 llvm-ar-17 llvm-ar-16; do
        if command -v "$name" >/dev/null 2>&1; then
            printf 'error: available %s failed LLVM archive admission\n' "$name" >&2
            cat "$tmp/err" >&2
            exit 1
        fi
    done
    printf '%s\n' 'WHP llvm-ar seed: optional LLVM tool not installed (skipped)'
    exit 0
fi
[ -x "$selected" ]
[ "$(WHP_LLVM_AR_SEED="$selected" /bin/sh "$seed" --print-seed)" = "$selected" ]
WHP_LLVM_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" --check >"$tmp/checked.out" 2>"$tmp/checked.err"
grep -Fq "WHP installed llvm-ar seed: $selected" "$tmp/checked.out"
grep -Fq 'compile, archive, replace, index, link and execute passed' "$tmp/checked.out"
grep -Fq "WHP llvm-ar selection: provider=WHP_LLVM_AR_SEED; executable=$selected; native-probe=yes" \
    "$tmp/checked.err"
[ "$(WHP_LLVM_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 /bin/sh "$seed" \
    --print-seed 2>"$tmp/printed.err")" = "$selected" ]
grep -Fq 'native-probe=yes' "$tmp/printed.err"

# The normal adapter must forward real archive arguments, not just probe them.
printf '%s\n' 'int whp_llvm_ar_direct(void) { return 17; }' > "$tmp/direct.c"
/bin/sh "$root/seeds/cc.sh" -c "$tmp/direct.c" -o "$tmp/direct.o"
WHP_LLVM_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" rcs "$tmp/libdirect.a" "$tmp/direct.o" \
    >"$tmp/direct.out" 2>"$tmp/direct.err"
[ ! -s "$tmp/direct.out" ]
grep -Fq "WHP llvm-ar selection: provider=WHP_LLVM_AR_SEED; executable=$selected; native-probe=no" \
    "$tmp/direct.err"
grep -Fq "WHP llvm-ar invocation: executable=$selected; operation=rcs; archive=$tmp/libdirect.a; argument-count=3; admission=not-repeated" \
    "$tmp/direct.err"
[ "$(WHP_LLVM_AR_SEED="$selected" /bin/sh "$seed" t "$tmp/libdirect.a")" = direct.o ]
WHP_LLVM_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=0 /bin/sh "$seed" t \
    "$tmp/libdirect.a" >"$tmp/quiet.out" 2>"$tmp/quiet.err"
[ "$(cat "$tmp/quiet.out")" = direct.o ]
[ ! -s "$tmp/quiet.err" ]

# Broken incremental replacement must be rejected after archive creation.
cat > "$tmp/no-replace" <<'EOF'
#!/bin/sh
if [ "${1:-}" = rcs ] && [ -f "$2" ]; then
    exit 0
fi
exec "$WHP_LLVM_AR_TEST_REAL" "$@"
EOF
chmod +x "$tmp/no-replace"
if WHP_LLVM_AR_TEST_REAL="$selected" WHP_LLVM_AR_SEED="$tmp/no-replace" \
    /bin/sh "$seed" --check > "$tmp/out" 2> "$tmp/err"; then
    printf '%s\n' 'error: no-op llvm-ar replacement accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]

# A symlink launcher must locate its own checkout, not the link's directory.
mkdir "$tmp/launcher"
ln -s "$seed" "$tmp/launcher/llvm-ar.sh"
[ "$(WHP_LLVM_AR_SEED="$selected" /bin/sh "$tmp/launcher/llvm-ar.sh" --print-seed)" = "$selected" ]

printf '%s\n' 'WHP installed llvm-ar seed: verified'
