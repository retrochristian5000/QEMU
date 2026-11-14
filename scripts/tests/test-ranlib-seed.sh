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
grep -Eq '[(]family: (gnu|llvm|unknown)[)]' "$tmp/check.out"
grep -Eq 'native-probe=yes; family=(gnu|llvm|unknown)' "$tmp/check.err"
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

# Native archive indexing is deliberately implementation-neutral. Verify
# actual LLVM and GNU implementations are named distinctly, including when
# llvm-ranlib is a symlink/alias for llvm-ar. Do not assume the executable
# name "ranlib" means GNU, or that a normal-object probe certifies LTO.
llvm_ranlib=
if llvm_ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-seed 2>"$tmp/llvm-ar.err"); then
    for candidate in "${llvm_ar%/*}/llvm-ranlib" llvm-ranlib llvm-ranlib-22 \
        llvm-ranlib-21 llvm-ranlib-20 llvm-ranlib-19 llvm-ranlib-18; do
        if command -v "$candidate" >/dev/null 2>&1; then
            llvm_ranlib=$(command -v "$candidate")
            break
        fi
    done
fi
if [ -n "$llvm_ranlib" ]; then
    WHP_RANLIB_SEED="$llvm_ranlib" WHP_ARCHIVE_VERBOSE=1 \
        /bin/sh "$seed" --check >"$tmp/llvm-check.out" 2>"$tmp/llvm-check.err"
    grep -Fq "(family: llvm)" "$tmp/llvm-check.out"
    grep -Fq "native-probe=yes; family=llvm" "$tmp/llvm-check.err"
    # GNU --plugin must not be silently discarded by the LLVM indexer.
    for option in --plugin --plugin=/tmp/whp-missing-gnu-lto-plugin.so; do
        if WHP_RANLIB_SEED="$llvm_ranlib" /bin/sh "$seed" \
            "$option" "$tmp/not-an-archive.a" >"$tmp/plugin.out" 2>"$tmp/plugin.err"; then
            printf 'error: LLVM ranlib accepted GNU plugin option: %s\n' "$option" >&2
            exit 1
        fi
        [ ! -s "$tmp/plugin.out" ]
        grep -Fq 'GNU ranlib --plugin is unsupported by LLVM ranlib' "$tmp/plugin.err"
    done
    # llvm-ar invoked with its ar name is NOT a replacement for llvm-ranlib
    # even when both executable paths ultimately share the same binary.
    if WHP_RANLIB_SEED="$llvm_ar" /bin/sh "$seed" --print-seed \
        >"$tmp/wrong-alias.out" 2>"$tmp/wrong-alias.err"; then
        printf '%s\n' 'error: llvm-ar accepted as llvm-ranlib without ranlib alias' >&2
        exit 1
    fi
    [ ! -s "$tmp/wrong-alias.out" ]
fi

# Real GNU gcc-ranlib is still allowed and identified as GNU. A mismatch
# with installed llvm-ar is a warning after native success, not an ABI veto.
if command -v gcc-ranlib >/dev/null 2>&1; then
    gcc_ranlib=$(command -v gcc-ranlib)
    if "$gcc_ranlib" --version 2>/dev/null | grep -Fq 'GNU ranlib'; then
        WHP_RANLIB_SEED="$gcc_ranlib" /bin/sh "$seed" --check \
            >"$tmp/gcc-check.out" 2>"$tmp/gcc-check.err"
        grep -Fq '(family: gnu)' "$tmp/gcc-check.out"
        if [ -n "$llvm_ar" ]; then
            WHP_AR_SEED="$llvm_ar" WHP_RANLIB_SEED="$gcc_ranlib" \
                /bin/sh "$seed" --check >"$tmp/mixed.out" 2>"$tmp/mixed.err"
            grep -Fq 'ordinary objects passed, LTO indexing unverified' "$tmp/mixed.err"
            grep -Fq 'ar/ranlib families differ' "$tmp/mixed.err"
        fi
    fi
fi

# A GNU indexer invocation must forward GNU plugin options untouched.
cat > "$tmp/gnu-recording-ranlib" <<'EOF'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'GNU ranlib (GNU Binutils) 99.0'
    exit 0
fi
printf '%s\n' "$@" > "$WHP_TEST_RANLIB_ARGS"
EOF
chmod +x "$tmp/gnu-recording-ranlib"
WHP_TEST_RANLIB_ARGS="$tmp/forwarded.args" \
    WHP_RANLIB_SEED="$tmp/gnu-recording-ranlib" \
    /bin/sh "$seed" --plugin=/tmp/whp-plugin.so "$tmp/placeholder.a"
test "$(cat "$tmp/forwarded.args")" = \
    "$(printf '%s\n' '--plugin=/tmp/whp-plugin.so' "$tmp/placeholder.a")"

if WHP_ARCHIVE_VERBOSE=invalid /bin/sh "$seed" --print-seed \
    >"$tmp/invalid.out" 2>"$tmp/invalid.err"; then
    printf '%s\n' 'error: invalid ranlib verbosity accepted' >&2
    exit 1
fi
[ ! -s "$tmp/invalid.out" ]
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/invalid.err"

printf '%s\n' 'WHP native ranlib diagnostics: verified'
