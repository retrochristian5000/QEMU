#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Minimal host-AWK seed bridge; never bootstrap AWK with AWK itself.
set -eu

WHP_AWK_ADAPTER_MARKER=whp-qemu-awk-seed-adapter

if [ "${1:-}" = --whp-awk-adapter-probe ]; then
    printf '%s\n' "$WHP_AWK_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    marker=$("$1" --whp-awk-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_AWK_ADAPTER_MARKER" ]
}

semantic_probe()
(
    candidate=$1
    LC_ALL=C
    export LC_ALL

    # QEMU's menuconfig and firmware helpers need POSIX fields, -F, -v,
    # regular expressions, record counters, substitution, and arrays.
    result=$(printf 'alpha|beta\n' |
        "$candidate" -F '|' -v wanted=beta \
            '$1 == "alpha" && $2 == wanted { printf "%s:%d:%d\n", $2, NF, NR }'
    ) || exit 1
    [ "$result" = beta:2:1 ] || exit 1

    result=$(printf 'A/B C\n' |
        "$candidate" '{ gsub(/[\/ ]/, "-", $0); print $0 }'
    ) || exit 1
    [ "$result" = A-B-C ] || exit 1

    result=$(printf 'one\ntwo\n' |
        "$candidate" '
            BEGIN {
                count = split("x,y", field, ",")
                if (count != 2 || field[2] != "y") exit 3
            }
            FNR == 2 && $0 ~ /^two$/ { print FNR }
        '
    ) || exit 1
    [ "$result" = 2 ] || exit 1
)

resolve_candidate()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null || true) ;;
    esac
    [ -n "$candidate" ] && [ -x "$candidate" ] || exit 1

    case "$candidate" in
        /*) ;;
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/}
            ;;
        *) exit 1 ;;
    esac

    is_self "$candidate" && exit 3
    semantic_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

select_seed()
{
    for name in WHP_AWK_SEED AWK; do
        case "$name" in
            WHP_AWK_SEED) requested=${WHP_AWK_SEED:-} ;;
            AWK) requested=${AWK:-} ;;
        esac
        [ -n "$requested" ] || continue
        if seed=$(resolve_candidate "$requested"); then
            printf '%s\n' "$seed"
            return 0
        else
            code=$?
        fi
        if [ "$code" -eq 3 ]; then
            printf 'error: %s points back to the QEMU awk bridge\n' "$name" >&2
        else
            printf 'error: %s is not a usable AWK: %s\n' "$name" "$requested" >&2
        fi
        return 1
    done

    for candidate in gawk /usr/bin/awk /bin/awk nawk mawk awk; do
        if seed=$(resolve_candidate "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable host AWK supports the WHP bootstrap semantics' >&2
    return 1
}

case "${1:-}" in
    --print-seed)
        select_seed
        exit $? ;;
    --check)
        seed=$(select_seed) || exit 1
        printf 'WHP AWK seed: %s\n' "$seed"
        exit 0 ;;
esac

# A normal build validates the AWK seed once. Literal awk calls and $AWK
# then execute the identical binary without repeating probes.
if [ "${WHP_AWK_LOCKED:-0}" = 1 ]; then
    [ -n "${WHP_AWK_SEED:-}" ] || {
        printf '%s\n' 'error: locked AWK has no selected seed' >&2
        exit 1
    }
    case "$WHP_AWK_SEED" in
        */awk.sh|*/scripts/whp-build/seed-bin/awk)
            printf '%s\n' 'error: locked AWK points to the awk bridge' >&2
            exit 1 ;;
    esac
    [ -x "$WHP_AWK_SEED" ] || {
        printf 'error: locked AWK is not executable: %s\n' "$WHP_AWK_SEED" >&2
        exit 1
    }
    exec "$WHP_AWK_SEED" "$@"
fi

seed=$(select_seed) || exit 1
exec "$seed" "$@"
