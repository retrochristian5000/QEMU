#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native LLVM indexer, provider separation and no-op detection.
set -eu
root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed=$root/seeds/llvm-ranlib.sh
llvm_ar_seed=$root/seeds/llvm-ar.sh
[ "$(/bin/sh "$seed" --whp-llvm-ranlib-adapter-probe)" = whp-qemu-llvm-ranlib-seed-adapter ]
sh -n "$seed"
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-llvm-ranlib-test.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

if WHP_ARCHIVE_VERBOSE=invalid /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: invalid archive trace setting accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/err"

# Explicit bad indexers fail without generic ranlib/PATH fallback.
for invalid in /bin/false "$seed"; do
    if WHP_LLVM_RANLIB_SEED="$invalid" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
        printf 'error: invalid explicit LLVM ranlib accepted: %s\n' "$invalid" >&2
        exit 1
    fi
    [ ! -s "$tmp/out" ]
done
# A generic Apple ranlib may itself be LLVM-backed; only reject non-LLVM.
if command -v ranlib >/dev/null 2>&1 &&
   ! ranlib --version 2>/dev/null | grep -Fq 'LLVM version '; then
    if WHP_LLVM_RANLIB_SEED="$(command -v ranlib)" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
        printf '%s\n' 'error: non-LLVM ranlib accepted' >&2
        exit 1
    fi
    [ ! -s "$tmp/out" ]
fi

for option in --plugin --plugin=/tmp/whp-gnu-plugin.so; do
    if /bin/sh "$seed" "$option" "$tmp/missing.a" >"$tmp/out" 2>"$tmp/err"; then
        printf '%s\n' 'error: LLVM ranlib accepted GNU plugin flag' >&2
        exit 1
    fi
    [ ! -s "$tmp/out" ]
    grep -Fq 'GNU ranlib --plugin is not an LLVM ranlib option' "$tmp/err"
done

# The installed pair is optional: never rebuild LLVM just to qualify a seed.
if ! llvm_ar=$(/bin/sh "$llvm_ar_seed" --print-seed 2>"$tmp/llvm-ar.err"); then
    printf '%s\n' 'WHP llvm-ranlib seed: optional llvm-ar unavailable (skipped)'
    exit 0
fi
if ! selected=$(/bin/sh "$seed" --print-seed 2>"$tmp/select.err"); then
    printf '%s\n' 'error: llvm-ar exists but no compatible llvm-ranlib passed' >&2
    cat "$tmp/select.err" >&2
    exit 1
fi
[ -x "$selected" ]
[ "$(WHP_LLVM_RANLIB_SEED="$selected" /bin/sh "$seed" --print-seed)" = "$selected" ]
WHP_LLVM_RANLIB_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" --check >"$tmp/check.out" 2>"$tmp/check.err"
grep -Fq "WHP installed llvm-ranlib seed: $selected" "$tmp/check.out"
grep -Fq 'native archive index, link and execute passed' "$tmp/check.out"
grep -Fq "WHP llvm-ranlib selection: provider=WHP_LLVM_RANLIB_SEED; executable=$selected; ar=$llvm_ar;" "$tmp/check.err"
grep -Fq 'native-probe=yes' "$tmp/check.err"

# llvm-ar is not llvm-ranlib even if the leaf symlink shares an executable.
if WHP_LLVM_RANLIB_SEED="$llvm_ar" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: llvm-ar name accepted as llvm-ranlib' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'llvm-ar executable is not a ranlib alias' "$tmp/err"

printf '%s\n' 'int whp_llvm_ranlib_test(void) { return 2; }' >"$tmp/probe.c"
/bin/sh "$root/seeds/cc.sh" -c "$tmp/probe.c" -o "$tmp/probe.o"
"$llvm_ar" rcS "$tmp/probe.a" "$tmp/probe.o"
before=$(cksum "$tmp/probe.a")
WHP_LLVM_RANLIB_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 \
    /bin/sh "$seed" "$tmp/probe.a" >"$tmp/forward.out" 2>"$tmp/forward.err"
after=$(cksum "$tmp/probe.a")
[ "$before" != "$after" ]
[ ! -s "$tmp/forward.out" ]
grep -Fq 'native-probe=no' "$tmp/forward.err"
grep -Fq 'admission=not-repeated' "$tmp/forward.err"

cat >"$tmp/wrong-major" <<'EOT'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'LLVM version 999.0.0'
    exit 0
fi
exit 0
EOT
chmod +x "$tmp/wrong-major"
if WHP_LLVM_RANLIB_SEED="$tmp/wrong-major" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: LLVM major mismatch accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'LLVM ranlib/ar version mismatch' "$tmp/err"

# Version banners are not sufficient: indexing must change a rcS archive.
real_major=$("$llvm_ar" --version | sed -n 's/.*LLVM version \([0-9][0-9]*\).*/\1/p' | sed -n '1p')
cat >"$tmp/noop-ranlib" <<'EOT'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'LLVM version WHP_REAL_MAJOR.0.0'
    exit 0
fi
exit 0
EOT
sed "s/WHP_REAL_MAJOR/$real_major/" "$tmp/noop-ranlib" >"$tmp/noop-versioned"
chmod +x "$tmp/noop-versioned"
if WHP_LLVM_RANLIB_SEED="$tmp/noop-versioned" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: no-op llvm-ranlib passed' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'stage=index-unchanged' "$tmp/err"

mkdir "$tmp/launcher"
ln -s "$seed" "$tmp/launcher/llvm-ranlib.sh"
[ "$(WHP_LLVM_RANLIB_SEED="$selected" /bin/sh "$tmp/launcher/llvm-ranlib.sh" --print-seed)" = "$selected" ]

printf '%s\n' 'WHP installed llvm-ranlib seed: verified'
