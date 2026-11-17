#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native Yacc seed: QEMU's parser generators require GNU Bison >= 3.
# Do not silently substitute an older POSIX yacc for Bison-only consumers.
set -eu

marker=whp-qemu-yacc-seed-adapter
if [ "${1:-}" = --whp-yacc-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_yacc()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in *[[:space:]]*) exit 1 ;; esac
    case "$value" in
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    probe=$("$candidate" --whp-yacc-adapter-probe 2>/dev/null || true)
    [ "$probe" != "$marker" ] || exit 1
    version=$("$candidate" --version 2>/dev/null) || exit 1
    first=${version%%'
'*}
    case "$first" in
        'bison (GNU Bison) '*|'bison (GNU Bison)'*) ;;
        *) exit 1 ;;
    esac
    number=${first##* }
    major=${number%%.*}
    case "$major" in
        ''|*[!0-9]*) exit 1 ;;
    esac
    [ "$major" -ge 3 ] || exit 1
    printf '%s\n' "$candidate"
)

select_yacc()
{
    for name in WHP_YACC_SEED YACC; do
        case "$name" in
            WHP_YACC_SEED) value=${WHP_YACC_SEED:-} ;;
            YACC) value=${YACC:-} ;;
        esac
        [ -n "$value" ] || continue
        if selected=$(resolve_yacc "$value"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s must select GNU Bison >= 3: %s\n' "$name" "$value" >&2
        return 1
    done

    # Homebrew Bison can be keg-only; Apple's /usr/bin/bison is often
    # older than the parser generator required by this build.
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        case "${WHP_MACOS_DEPENDENCY_PROVIDER:-auto}" in
            macports|system) ;;
            *)
                seed_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P) || return 1
                if value=$(/bin/sh "$seed_dir/brew.sh" --formula-bin bison bison 2>/dev/null); then
                    if selected=$(resolve_yacc "$value"); then
                        printf '%s\n' "$selected"
                        return 0
                    fi
                fi
                ;;
        esac
    fi

    # An independent native GNU Bison remains a valid fallback.
    for value in bison /usr/bin/bison; do
        if selected=$(resolve_yacc "$value"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable GNU Bison >= 3 for the WHP Yacc seed' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-yacc)
        select_yacc ;;
    --check)
        selected=$(select_yacc) || exit 1
        printf 'WHP Yacc seed (Bison): %s\n' "$selected" ;;
    *)
        selected=$(select_yacc) || exit 1
        exec "$selected" "$@" ;;
esac
