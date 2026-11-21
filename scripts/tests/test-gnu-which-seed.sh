#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# GNU which is optional; a generic BSD/POSIX lookup is always independent.
set -eu

root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P) || exit 1
portable=$root/seeds/which.sh
gnu=$root/seeds/GNUwhich.sh

[ "$(/bin/sh "$gnu" --whp-gnu-which-adapter-probe)" = whp-qemu-gnu-which-seed-adapter ]
[ "$(/bin/sh "$portable" --whp-which-adapter-probe)" = whp-qemu-which-seed-adapter ]
/bin/sh -n "$gnu"

# --skip-dot is GNU-specific: portable which must reject it without relabeling.
if /bin/sh "$portable" --skip-dot sh >/dev/null 2>&1; then
    printf '%s\n' 'error: portable which accepted GNU --skip-dot' >&2
    exit 1
fi

tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-gnu-which-test.XXXXXXXX") || exit 1
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15
printf '#!/bin/sh\nif [ "${1:-}" = --version ]; then printf "GNU which v99.99\n"; exit 0; fi\nexit 0\n' > "$tmp/banner-only"
chmod 700 "$tmp/banner-only"

# Must fail closed on copied adapters, fake banners, and non-GNU commands.
cp "$gnu" "$tmp/gnu-copied"
chmod 700 "$tmp/gnu-copied"
for invalid in "$portable" "$gnu" "$tmp/gnu-copied" "$tmp/banner-only" /bin/sh; do
    if WHP_GNU_WHICH_SEED="$invalid" /bin/sh "$gnu" --print-seed \
        > "$tmp/out" 2> "$tmp/err"; then
        printf 'error: invalid GNU which provider accepted: %s\n' "$invalid" >&2
        exit 1
    fi
    [ ! -s "$tmp/out" ]
    grep -Fq 'WHP_GNU_WHICH_SEED is not usable' "$tmp/err"
done

# GNU which is not required on macOS or a bare native bootstrap host.
if selected=$(WHP_GNU_WHICH_SEED= /bin/sh "$gnu" --print-seed 2>"$tmp/err"); then
    [ -f "$selected" ] && [ -x "$selected" ]
    [ "$(WHP_GNU_WHICH_SEED="$selected" /bin/sh "$gnu" --print-seed)" = "$selected" ]
    WHP_GNU_WHICH_SEED="$selected" /bin/sh "$gnu" --check \
        | grep -Fq 'GNU version, --all, --skip-dot verified'
    banner=$(WHP_GNU_WHICH_SEED="$selected" /bin/sh "$gnu" --version)
    case "$banner" in 'GNU which v'*) ;; *) exit 1 ;; esac
else
    grep -Fq 'no native GNU which passed functional checks' "$tmp/err"
    printf '%s\n' 'GNU which runtime unavailable: optional execution skipped'
fi
[ -n "$(/bin/sh "$portable" sh)" ]
printf '%s\n' 'WHP independent GNU which seed: verified'
