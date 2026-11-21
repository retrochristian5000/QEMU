#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native GNU which. Keep the portable which.sh independent.
# Never install packages, rewrite PATH, or bootstrap GNU which with itself.
set -eu

marker=whp-qemu-gnu-which-seed-adapter
if [ "${1:-}" = --whp-gnu-which-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

gnu_which_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/}
            ;;
        *) exit 1 ;;
    esac

    # Reject the optional GNU adapter itself and the portable which bridge.
    signature=$("$candidate" --whp-gnu-which-adapter-probe 2>/dev/null || true)
    [ "$signature" != "$marker" ] || exit 1
    signature=$("$candidate" --whp-which-adapter-probe 2>/dev/null || true)
    [ "$signature" != whp-qemu-which-seed-adapter ] || exit 1

    banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    case "$banner" in
        'GNU which v'*) ;;
        *) exit 1 ;;
    esac

    # Reject banner-only shims: -a/--all and --skip-dot must really work.
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-gnu-which.XXXXXXXX") || exit 1
    trap 'rm -rf -- "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    mkdir -p "$tmp/first" "$tmp/second" || exit 1
    printf '#!/bin/sh\nexit 0\n' > "$tmp/first/whp-gnu-which-probe"
    cp "$tmp/first/whp-gnu-which-probe" "$tmp/second/whp-gnu-which-probe"
    chmod 700 "$tmp/first/whp-gnu-which-probe" "$tmp/second/whp-gnu-which-probe"
    matched=$(PATH="$tmp/first:$tmp/second" "$candidate" --all whp-gnu-which-probe) || exit 1
    expected=$(printf '%s\n%s\n' "$tmp/first/whp-gnu-which-probe" "$tmp/second/whp-gnu-which-probe")
    [ "$matched" = "$expected" ] || exit 1
    matched=$(cd "$tmp/first" &&
        PATH=".:$tmp/second" "$candidate" --skip-dot whp-gnu-which-probe) || exit 1
    [ "$matched" = "$tmp/second/whp-gnu-which-probe" ] || exit 1
    printf '%s\n' "$candidate"
)

gnu_which_select()
{
    # Explicit GNU selection is authoritative: never fall back to BSD which.
    if [ -n "${WHP_GNU_WHICH_SEED:-}" ]; then
        if selected=$(gnu_which_resolve "$WHP_GNU_WHICH_SEED"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: WHP_GNU_WHICH_SEED is not usable GNU which: %s\n' \
            "$WHP_GNU_WHICH_SEED" >&2
        return 1
    fi
    # Homebrew installs GNU which as gwhich, not as GNU coreutils 'which'.
    for candidate in gwhich /opt/homebrew/bin/gwhich /usr/local/bin/gwhich \
            /opt/local/bin/gwhich which /usr/bin/which; do
        if selected=$(gnu_which_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no native GNU which passed functional checks (optional seed)' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-gnu-which)
        gnu_which_select ;;
    --check)
        selected=$(gnu_which_select) || exit 1
        printf 'WHP GNU which seed: %s (GNU version, --all, --skip-dot verified)\n' "$selected" ;;
    *)
        selected=$(gnu_which_select) || exit 1
        exec "$selected" "$@" ;;
esac
