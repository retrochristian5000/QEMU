#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# GNU-specific archiver selection, native admission, and nonrecursive forwarding.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed="$root/seeds/GNUar.sh"
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-GNUar-seed.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15

[ "$(/bin/sh "$seed" --whp-gnu-ar-adapter-probe)" = whp-qemu-gnu-ar-seed-adapter ]
[ "$(/bin/sh "$seed" --whp-ar-adapter-probe)" = whp-qemu-gnu-ar-seed-adapter ]

real_ar=$(command -v ar) || exit 1
export WHP_GNU_AR_TEST_REAL_AR="$real_ar"
mkdir "$tmp/bin"
cat > "$tmp/bin/gar" <<'SH'
#!/bin/sh
# This fixture labels an already installed native archiver; its native
# capabilities are tested separately, not inferred from the banner.
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'GNU ar (GNU Binutils) 2.43'
    exit 0
fi
exec "$WHP_GNU_AR_TEST_REAL_AR" "$@"
SH
chmod +x "$tmp/bin/gar"
export PATH="$tmp/bin:$PATH"
selected="$tmp/bin/gar"

[ "$(WHP_GNU_AR_SEED="$selected" /bin/sh "$seed" --print-candidate)" = "$selected" ]
[ "$(WHP_GNU_AR_SEED="$selected" /bin/sh "$seed" --print-seed)" = "$selected" ]
WHP_GNU_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 /bin/sh "$seed" --check \
    >"$tmp/check.out" 2>"$tmp/check.err"
grep -Fq 'GNU Binutils; native archive/link verified' "$tmp/check.out"
grep -Fq "WHP GNU ar selection: provider=WHP_GNU_AR_SEED; executable=$selected; native-probe=yes" "$tmp/check.err"

# The uppercase entrypoint cannot silently replace generic native ar.
[ "$(WHP_GNU_AR_SEED="$selected" /bin/sh "$root/seeds/ar.sh" --print-seed)" != "$seed" ]

# Ordinary invocations forward rather than recompiling the entire probe.
printf '%s\n' 'int whp_gnu_ar_member(void) { return 13; }' > "$tmp/member.c"
/bin/sh "$root/seeds/cc.sh" -c "$tmp/member.c" -o "$tmp/member.o"
WHP_GNU_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=1 /bin/sh "$seed" \
    rcs "$tmp/libmember.a" "$tmp/member.o" >"$tmp/forward.out" 2>"$tmp/forward.err"
[ ! -s "$tmp/forward.out" ]
grep -Fq "WHP GNU ar selection: provider=WHP_GNU_AR_SEED; executable=$selected; native-probe=no" "$tmp/forward.err"
grep -Fq 'admission=not-repeated' "$tmp/forward.err"
# This fixture forwards to the host archiver. Darwin's native ar may include
# its precisely named symbol-table metadata member in the table listing.
listing=$(WHP_GNU_AR_SEED="$selected" /bin/sh "$seed" t "$tmp/libmember.a")
if [ "$listing" != member.o ]; then
    if [ "$(uname -s 2>/dev/null || true)" != Darwin ] ||
       [ "$listing" != "$(printf '__.SYMDEF SORTED\nmember.o')" ]; then
        printf 'error: unexpected GNU ar fixture members: %s\n' "$listing" >&2
        exit 1
    fi
fi
WHP_GNU_AR_SEED="$selected" /bin/sh "$seed" p "$tmp/libmember.a" member.o >"$tmp/recovered.o"
cmp -s "$tmp/member.o" "$tmp/recovered.o"

# Path symlinks locate their own checkout. The selected GNU tool cannot
# itself be the adapter or an alias of it.
ln -s "$seed" "$tmp/launcher"
[ "$(WHP_GNU_AR_SEED="$selected" /bin/sh "$tmp/launcher" --print-candidate)" = "$selected" ]
for bad in "$seed" "$tmp/launcher" "$root/seeds/ar.sh" "$tmp/no-such-ar"; do
    if WHP_GNU_AR_SEED="$bad" /bin/sh "$seed" --print-candidate >"$tmp/out" 2>"$tmp/err"; then
        printf 'error: GNUar accepted self/generic/invalid provider: %s\n' "$bad" >&2
        exit 1
    fi
    [ ! -s "$tmp/out" ]
done

cat > "$tmp/non-gnu" <<'SH'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'LLVM version 99.0'
    exit 0
fi
exec "$WHP_GNU_AR_TEST_REAL_AR" "$@"
SH
chmod +x "$tmp/non-gnu"
if WHP_GNU_AR_SEED="$tmp/non-gnu" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: GNU-specific ar seed accepted LLVM identity' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]

# A forged GNU banner without functional archive operations cannot qualify.
cat > "$tmp/banner-only" <<'SH'
#!/bin/sh
if [ "${1:-}" = --version ]; then
    printf '%s\n' 'GNU ar (GNU Binutils) 2.43'
    exit 0
fi
exit 0
SH
chmod +x "$tmp/banner-only"
[ "$(WHP_GNU_AR_SEED="$tmp/banner-only" /bin/sh "$seed" --print-candidate)" = "$tmp/banner-only" ]
if WHP_GNU_AR_SEED="$tmp/banner-only" /bin/sh "$seed" --print-seed >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: GNU banner-only tool passed native archive admission' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
grep -Fq 'native archive probe failed' "$tmp/err"

if WHP_GNU_AR_SEED="$selected" WHP_ARCHIVE_VERBOSE=invalid \
        /bin/sh "$seed" --print-candidate >"$tmp/out" 2>"$tmp/err"; then
    printf '%s\n' 'error: invalid archive verbosity was accepted' >&2
    exit 1
fi
grep -Fq 'WHP_ARCHIVE_VERBOSE must be 0 or 1' "$tmp/err"

# Automatic selection still detects a working GNU-labeled candidate; the
# controlled fixture guarantees the result even without installed Binutils.
automatic=$(WHP_GNU_AR_SEED= /bin/sh "$seed" --print-candidate) || exit 1
[ -x "$automatic" ]

printf '%s\n' 'WHP GNU-specific ar seed: identity, native archive, forwarding and rejection verified'
