#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select native GNU Awk only. The early POSIX AWK bootstrap uses awk.sh.
# No managed-Gawk build or self-bootstrap is permitted in this seed.
set -eu

marker=whp-qemu-gawk-seed-adapter
if [ "${1:-}" = --whp-gawk-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_gawk()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null || true) ;;
    esac
    [ -n "$candidate" ] && [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/}
            ;;
        *) exit 1 ;;
    esac
    # Never claim an adapter or the general POSIX AWK bridge is GNU Awk.
    case "$candidate" in
        */seeds/gawk.sh|*/seeds/awk.sh|*/scripts/whp-build/seed-bin/gawk|*/scripts/whp-build/seed-bin/awk)
            exit 3 ;;
    esac
    signature=$("$candidate" --whp-gawk-adapter-probe 2>/dev/null || true)
    [ "$signature" != "$marker" ] || exit 3
    signature=$("$candidate" --whp-awk-adapter-probe 2>/dev/null || true)
    [ "$signature" != whp-qemu-awk-seed-adapter ] || exit 3

    # GNU identity alone is not enough: fail closed on banner-only shims,
    # BSD awk, mawk and nawk, even if they support the POSIX AWK subset.
    banner=$("$candidate" --version 2>/dev/null) || exit 1
    case "$banner" in "GNU Awk "*) ;; *) exit 1 ;; esac
    result=$(LC_ALL=C "$candidate" '
        BEGIN {
            item["b"] = 1
            item["a"] = 2
            count = asorti(item, ordered)
            output = gensub(/[0-9]+/, "#", "g", "a12 b34")
            if (count != 2 || ordered[1] != "a" || ordered[2] != "b" ||
                output != "a# b#") {
                exit 9
            }
            print "whp-gnu-awk-ok"
        }
    ') || exit 1
    [ "$result" = whp-gnu-awk-ok ] || exit 1
    printf '%s\n' "$candidate"
)

select_gawk()
{
    # GNU-only selectors do not inherit generic AWK or WHP_AWK_SEED as
    # mandatory overrides. A generic native AWK remains valid without Gawk.
    for setting in WHP_GAWK_SEED GAWK; do
        case "$setting" in
            WHP_GAWK_SEED) requested=${WHP_GAWK_SEED:-} ;;
            GAWK) requested=${GAWK:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(resolve_gawk "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s does not name a working GNU Awk: %s\n' \
            "$setting" "$requested" >&2
        return 1
    done

    # A pre-installed GNU Awk may be gawk, a Homebrew/MacPorts formula,
    # or even the system awk. Preserve an explicit provider decision.
    for requested in gawk /opt/homebrew/bin/gawk /usr/local/bin/gawk \
            /opt/local/bin/gawk "${WHP_AWK_SEED:-}" awk /usr/bin/awk /bin/awk; do
        [ -n "$requested" ] || continue
        if selected=$(resolve_gawk "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' \
        'error: no working GNU Awk found; use WHP_GAWK_SEED or enable the later managed Gawk stage' >&2
    return 1
}

case "${1:-}" in
    --print-seed)
        select_gawk ;;
    --check)
        selected=$(select_gawk) || exit 1
        printf 'WHP GNU Awk seed: %s (GNU identity, asorti, gensub verified)\n' \
            "$selected" ;;
    *)
        # Normal tool invocations preserve argv and exit code with no
        # repeated semantic probe after the managed provider is locked.
        if [ "${WHP_GAWK_LOCKED:-0}" = 1 ]; then
            selected=${WHP_GAWK_SEED:-}
            case "$selected" in
                ""|*/seeds/gawk.sh|*/seeds/awk.sh|*/scripts/whp-build/seed-bin/gawk|*/scripts/whp-build/seed-bin/awk)
                    printf '%s\n' 'error: locked Gawk has no independent executable' >&2
                    exit 1 ;;
            esac
            [ -f "$selected" ] && [ -x "$selected" ] || {
                printf 'error: locked Gawk is not executable: %s\n' "$selected" >&2
                exit 1
            }
        else
            selected=$(select_gawk) || exit 1
        fi
        exec "$selected" "$@" ;;
esac
