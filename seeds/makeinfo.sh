#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Choose and validate an installed GNU Texinfo makeinfo for native builds.
# This is a build-machine seed, not a request to install documentation tools
# into QEMU's runtime prefix or to bootstrap Texinfo from its own sources.
set -eu

marker=whp-qemu-makeinfo-seed-adapter
if [ "${1:-}" = --whp-makeinfo-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_makeinfo()
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
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    # Reject self/symlink recursion before asking the selected tool for
    # --version, preserving the invoked executable basename (argv[0]).
    probe=$("$candidate" --whp-makeinfo-adapter-probe 2>/dev/null || :)
    [ "$probe" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

gnu_makeinfo_version()
(
    candidate=$1
    banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        'makeinfo (GNU texinfo) '*|'texi2any (GNU texinfo) '*|\
        'makeinfo (GNU Texinfo) '*|'texi2any (GNU Texinfo) '*) ;;
        *) exit 1 ;;
    esac
    version=${first##* }
    case "$version" in
        [0-9]*.[0-9]*)
            case "$version" in
                *[!0-9.]*|*..*|*.) exit 1 ;;
            esac ;;
        *) exit 1 ;;
    esac
    printf '%s\n' "$first"
)

probe_texinfo_conversion()
(
    candidate=$1
    whp_tmp=$(mktemp -d "${TMPDIR:-/tmp}/whp-qemu-makeinfo.XXXXXXXX") || {
        printf '%s\n' 'error: cannot create makeinfo probe directory' >&2
        exit 1
    }
    trap 'rm -rf "$whp_tmp"' 0
    cat >"$whp_tmp/probe.texi" <<'EOF'
\input texinfo
@setfilename probe.info
@node Top
@top WHP native Texinfo test
@bye
EOF
    if "$candidate" --no-split -o "$whp_tmp/probe.info" \
        "$whp_tmp/probe.texi" >"$whp_tmp/stdout" 2>"$whp_tmp/stderr" &&
        [ -s "$whp_tmp/probe.info" ]; then
        exit 0
    fi
    printf 'error: GNU Texinfo makeinfo cannot convert native documentation: %s\n' \
        "$candidate" >&2
    if [ -s "$whp_tmp/stderr" ]; then
        cat "$whp_tmp/stderr" >&2
    fi
    exit 1
)

explicit=${WHP_MAKEINFO_SEED:-${MAKEINFO:-}}
if [ -n "$explicit" ]; then
    selected=$(resolve_makeinfo "$explicit") || {
        printf 'error: invalid explicit GNU makeinfo seed: %s\n' "$explicit" >&2
        exit 1
    }
else
    selected=$(resolve_makeinfo makeinfo) || {
        # texi2any is GNU makeinfo's implementation name on some systems.
        selected=$(resolve_makeinfo texi2any) || {
            printf '%s\n' 'error: GNU Texinfo makeinfo is required to build maintainer documentation' >&2
            exit 1
        }
    }
fi

identity=$(gnu_makeinfo_version "$selected") || {
    printf 'error: selected tool is not GNU Texinfo makeinfo: %s\n' "$selected" >&2
    exit 1
}
probe_texinfo_conversion "$selected" || exit 1

case "${1:-}" in
    --print-seed|--print-makeinfo) printf '%s\n' "$selected" ;;
    --check)
        printf 'WHP GNU Texinfo makeinfo seed: %s\n%s\n' "$selected" "$identity" ;;
    *) exec "$selected" "$@" ;;
esac
