#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native GNU M4 seed for maintainer-source Autotools generation.
set -eu

marker=whp-qemu-m4-seed-adapter
if [ "${1:-}" = --whp-m4-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

m4_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        *[[:space:]]*) exit 1 ;;
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-m4-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    banner=$("$candidate" --gnu --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        *'GNU M4'*) ;;
        *) exit 1 ;;
    esac
    version=${first##* }
    major=${version%%.*}
    remainder=${version#*.}
    [ "$remainder" != "$version" ] || exit 1
    minor=${remainder%%.*}
    patch=0
    case "$remainder" in
        *.*) patch=${remainder#*.}; patch=${patch%%[!0-9]*} ;;
    esac
    case "$major:$minor:$patch" in
        *[!0-9:]*|:*|*::*) exit 1 ;;
    esac
    [ -n "$major" ] && [ -n "$minor" ] || exit 1
    if [ "$major" -eq 1 ]; then
        if [ "$minor" -lt 4 ]; then exit 1; fi
        if [ "$minor" -eq 4 ] && [ "$patch" -lt 16 ]; then exit 1; fi
    elif [ "$major" -lt 1 ]; then
        exit 1
    fi
    result=$(printf '%s\n' "patsubst(\`ab12cd', \`[0-9]+', \`X')" |
        "$candidate" --gnu --fatal-warnings 2>/dev/null) || exit 1
    [ "$result" = abXcd ] || exit 1
    printf '%s\n' "$candidate"
)

m4_select()
{
    # Explicit values are authoritative and must never fall through to PATH.
    for variable in WHP_M4_SEED M4; do
        case "$variable" in
            WHP_M4_SEED) requested=${WHP_M4_SEED:-} ;;
            M4) requested=${M4:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(m4_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s does not select usable GNU M4 >= 1.4.16: %s\n' "$variable" "$requested" >&2
        return 1
    done

    # macOS Homebrew M4 is often keg-only. Avoid Apple's compatibility
    # implementation outranking a managed GNU M4 installation.
    case "$(uname -s)" in
        Darwin)
            for candidate in \
                "${HOMEBREW_PREFIX:-/opt/homebrew}/opt/m4/bin/m4" \
                /opt/homebrew/opt/m4/bin/m4 \
                /usr/local/opt/m4/bin/m4; do
                if selected=$(m4_resolve "$candidate"); then
                    printf '%s\n' "$selected"
                    return 0
                fi
            done
            ;;
    esac

    for candidate in m4 gm4; do
        if selected=$(m4_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: GNU M4 >= 1.4.16 with working macro expansion is required for this seed' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-m4) m4_select ;;
    --check)
        selected=$(m4_select) || exit 1
        printf 'WHP GNU M4 seed: %s\n' "$selected" ;;
    *)
        selected=$(m4_select) || exit 1
        exec "$selected" "$@" ;;
esac
