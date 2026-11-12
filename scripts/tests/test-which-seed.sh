#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Host-independent checks for the POSIX which seed; no QEMU build required.
set -eu
root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
seed=$root/seeds/which.sh

[ "$(/bin/sh "$seed" --whp-which-adapter-probe)" = whp-qemu-which-seed-adapter ]
selected=$(/bin/sh "$seed" --print-seed)
[ -f "$selected" ]
[ "$(/bin/sh "$seed" --check)" = "WHP native which seed: $selected" ]

tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-which-seed.XXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15
mkdir -p "$tmp/first" "$tmp/second" "$tmp/with spaces" "$tmp/empty"
printf '#!/bin/sh\nexit 0\n' > "$tmp/first/whp-present"
cp "$tmp/first/whp-present" "$tmp/second/whp-present"
cp "$tmp/first/whp-present" "$tmp/with spaces/whp-present"
chmod +x "$tmp/first/whp-present" "$tmp/second/whp-present" "$tmp/with spaces/whp-present"
printf '%s\n' '#!/bin/sh' > "$tmp/first/not-executable"
mkdir "$tmp/first/directory-only"

# One match, ordered -a matches, spaced PATH entries, and executable-only.
[ "$(PATH="$tmp/first:$tmp/second" /bin/sh "$seed" whp-present)" = "$tmp/first/whp-present" ]
[ "$(PATH="$tmp/first:$tmp/second" /bin/sh "$seed" -a whp-present)" = "$(printf '%s\n%s' "$tmp/first/whp-present" "$tmp/second/whp-present")" ]
[ "$(PATH="$tmp/with spaces:$tmp/second" /bin/sh "$seed" whp-present)" = "$tmp/with spaces/whp-present" ]
if PATH="$tmp/first" /bin/sh "$seed" not-executable >"$tmp/out"; then
    printf '%s\n' 'error: non-executable accepted by which seed' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]
if PATH="$tmp/first" /bin/sh "$seed" directory-only >"$tmp/out"; then
    printf '%s\n' 'error: executable directory accepted by which seed' >&2
    exit 1
fi

# A missing name must fail even when another name succeeded; -s is silent.
if PATH="$tmp/first" /bin/sh "$seed" whp-present whp-absent >"$tmp/out"; then
    printf '%s\n' 'error: missing command accepted by which seed' >&2
    exit 1
fi
[ "$(cat "$tmp/out")" = "$tmp/first/whp-present" ]
PATH="$tmp/first" /bin/sh "$seed" -s whp-present >"$tmp/out"
[ ! -s "$tmp/out" ]
if PATH="$tmp/first" /bin/sh "$seed" -s whp-absent >"$tmp/out"; then
    printf '%s\n' 'error: silent missing command accepted' >&2
    exit 1
fi
[ ! -s "$tmp/out" ]

# Explicit pathname, names beginning with a dash, empty and relative PATH.
cp "$tmp/first/whp-present" "$tmp/first/-hyphen"
chmod +x "$tmp/first/-hyphen"
[ "$(PATH="$tmp/first" /bin/sh "$seed" -- -hyphen)" = "$tmp/first/-hyphen" ]
[ "$(/bin/sh "$seed" "$tmp/first/whp-present")" = "$tmp/first/whp-present" ]
(
    cd "$tmp/first"
    [ "$(PATH= /bin/sh "$seed" whp-present)" = "$tmp/first/whp-present" ]
    [ "$(PATH=.:$tmp/second /bin/sh "$seed" whp-present)" = "$tmp/first/whp-present" ]
)
if /bin/sh "$seed" -Z whp-present >/dev/null 2>"$tmp/err"; then
    printf '%s\n' 'error: invalid which option accepted' >&2
    exit 1
fi
[ -s "$tmp/err" ]

# Resolve a symlink launcher and reject a cyclic chain without recursion.
ln -s "$seed" "$tmp/which-link"
[ "$(/bin/sh "$tmp/which-link" --print-seed)" = "$selected" ]
ln -s "$tmp/loop-b" "$tmp/loop-a"
ln -s "$tmp/loop-a" "$tmp/loop-b"
if /bin/sh "$tmp/loop-a" --print-seed >/dev/null 2>&1; then
    printf '%s\n' 'error: recursive which launcher accepted' >&2
    exit 1
fi

printf '%s\n' 'WHP portable which seed: verified'
