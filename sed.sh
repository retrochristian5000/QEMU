#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Pre-GNU-sed adapter for the WHP QEMU bootstrap graph.
#
# Prefer a semantically verified external sed. If no usable sed exists, fall
# back to a deliberately small POSIX-shell stream editor that implements only
# the syntax needed by QEMU's seed probes and Automake's first-stage bootstrap.
# Unsupported syntax is a hard error: this fallback must never guess and
# silently corrupt generated files. Once pinned GNU sed is available, QEMU
# exports that binary directly and this adapter leaves the active build path.

set -eu
set -f

WHP_SED_ADAPTER_MARKER=whp-qemu-sed-seed-adapter
WHP_SED_SHELL_VERSION=1

self_path()
{
    case "$0" in
        /*) printf '%s\n' "$0" ;;
        */*)
            self_dir=${0%/*}
            self_base=${0##*/}
            self_dir=$(CDPATH= cd -- "$self_dir" 2>/dev/null && pwd) || return 1
            printf '%s/%s\n' "$self_dir" "$self_base"
            ;;
        *)
            self_resolved=$(command -v "$0" 2>/dev/null || true)
            [ -n "$self_resolved" ] || return 1
            case "$self_resolved" in
                /*) printf '%s\n' "$self_resolved" ;;
                *) printf '%s/%s\n' "$(pwd)" "$self_resolved" ;;
            esac
            ;;
    esac
}

if [ "${1:-}" = --whp-sed-adapter-probe ]; then
    printf '%s\n' "$WHP_SED_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-sed-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_SED_ADAPTER_MARKER" ]
}

resolve_candidate()
{
    value=$1
    [ -n "$value" ] || return 1
    if [ -x "$value" ]; then
        candidate=$value
    else
        case "$value" in *[[:space:]]*) return 1 ;; esac
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    is_self "$candidate" && return 3
    result=$(printf 'alpha\n' | "$candidate" -n 's/^alpha$/beta/p' 2>/dev/null || true)
    [ "$result" = beta ] || return 1
    printf '%s\n' "$candidate"
}

select_external_seed()
{
    [ "${WHP_SED_FORCE_SHELL:-0}" != 1 ] || return 1
    if [ -n "${WHP_SED_SEED:-}" ]; then
        if seed=$(resolve_candidate "$WHP_SED_SEED"); then
            printf '%s\n' "$seed"; return 0
        else
            rc=$?
            [ "$rc" -eq 3 ] && return 1
            printf 'error: WHP_SED_SEED is not a usable sed: %s\n' "$WHP_SED_SEED" >&2
            return 2
        fi
    fi
    if [ -n "${SED:-}" ]; then
        if seed=$(resolve_candidate "$SED"); then
            printf '%s\n' "$seed"; return 0
        else
            rc=$?
            [ "$rc" -eq 3 ] && return 1
        fi
    fi
    for value in gsed /usr/bin/sed /bin/sed sed; do
        if seed=$(resolve_candidate "$value"); then
            printf '%s\n' "$seed"; return 0
        fi
    done
    return 1
}

seed=
if seed=$(select_external_seed); then
    have_external=1
else
    rc=$?
    [ "$rc" -eq 1 ] || exit 1
    have_external=0
fi
self=$(self_path 2>/dev/null || printf '%s\n' "$0")

case "${1:-}" in
    --print-seed)
        if [ "$have_external" = 1 ]; then printf '%s\n' "$seed"; else printf '%s\n' "$self"; fi
        exit 0 ;;
    --check)
        if [ "$have_external" = 1 ]; then printf 'WHP sed seed: external %s\n' "$seed"; else printf 'WHP sed seed: shell fallback %s\n' "$self"; fi
        exit 0 ;;
    --capabilities)
        printf '%s\n' 'shell-fallback: -n -e/-ne 1p literal/anchored s/// basename sanitization automake-version backref-key'
        exit 0 ;;
    --version)
        if [ "$have_external" = 1 ]; then exec "$seed" --version; fi
        printf 'WHP shell sed bootstrap %s\n' "$WHP_SED_SHELL_VERSION"
        exit 0 ;;
esac

if [ "$have_external" = 1 ]; then exec "$seed" "$@"; fi

fallback_error()
{
    printf 'error: WHP shell sed fallback does not support: %s\n' "$1" >&2
    exit 2
}

literal_replace_all()
{
    lr_text=$1 lr_needle=$2 lr_repl=$3 lr_out=
    [ -n "$lr_needle" ] || { printf '%s\n' "$lr_text"; return 0; }
    while case "$lr_text" in *"$lr_needle"*) true ;; *) false ;; esac; do
        lr_prefix=${lr_text%%"$lr_needle"*}
        lr_out=$lr_out$lr_prefix$lr_repl
        lr_text=${lr_text#*"$lr_needle"}
    done
    printf '%s%s\n' "$lr_out" "$lr_text"
}

sanitize_tag()
{
    st_rest=$1 st_out=
    while [ -n "$st_rest" ]; do
        st_tail=${st_rest#?}
        st_char=${st_rest%"$st_tail"}
        st_rest=$st_tail
        case "$st_char" in [A-Za-z0-9_.-]) st_out=$st_out$st_char ;; *) st_out=$st_out- ;; esac
    done
    printf '%s\n' "$st_out"
}

emit_current()
{
    if [ "$had_newline" = 1 ]; then printf '%s\n' "$current"; else printf '%s' "$current"; fi
}

apply_subst()
{
    subst=$1
    body=${subst#s}
    [ -n "$body" ] || fallback_error "$subst"
    tail=${body#?}
    delim=${body%"$tail"}
    case "$tail" in *"$delim"*) ;; *) fallback_error "$subst" ;; esac
    pattern=${tail%%"$delim"*}
    rem=${tail#*"$delim"}
    case "$rem" in *"$delim"*) ;; *) fallback_error "$subst" ;; esac
    replacement=${rem%%"$delim"*}
    flags=${rem#*"$delim"}
    case "$flags" in ''|g|p|gp|pg) ;; *) fallback_error "$subst" ;; esac
    want_global=0; want_print=0
    case "$flags" in *g*) want_global=1 ;; esac
    case "$flags" in *p*) want_print=1 ;; esac
    substituted=0

    case "$pattern" in
        '^.*/')
            case "$current" in */*) current=${current##*/}; substituted=1 ;; esac
            ;;
        '[^A-Za-z0-9_.-]')
            [ "$want_global" = 1 ] || fallback_error "$subst"
            new=$(sanitize_tag "$current")
            [ "$new" = "$current" ] || substituted=1
            current=$new
            ;;
        '^APIVERSION=')
            case "$current" in APIVERSION=*) current=${current#APIVERSION=}; substituted=1 ;; esac
            ;;
        '^AR=\([^|]*\)|.*$')
            case "$current" in AR=*\|*) current=${current#AR=}; current=${current%%|*}; substituted=1 ;; esac
            ;;
        '^['*)
            if [ "$pattern" = '^[^[]*\[[^[]*\[\([^]]*\)\].*$' ] && [ "$replacement" = '\1' ]; then
                tmp=${current#*\[}
                if [ "$tmp" != "$current" ]; then
                    tmp2=${tmp#*\[}
                    if [ "$tmp2" != "$tmp" ]; then current=${tmp2%%]*}; substituted=1; fi
                fi
            else
                fallback_error "$subst"
            fi
            ;;
        '^'*'$')
            literal=${pattern#^}
            literal=${literal%$}
            case "$literal" in *'['*|*']'*|*'('*|*')'*|*'\\'*|*'.'*|*'*'*|*'+'*|*'?'*) fallback_error "$subst" ;; esac
            if [ "$current" = "$literal" ]; then current=$replacement; substituted=1; fi
            ;;
        '^'*)
            literal=${pattern#^}
            case "$literal" in *'['*|*']'*|*'('*|*')'*|*'\\'*|*'.'*|*'*'*|*'+'*|*'?'*) fallback_error "$subst" ;; esac
            case "$current" in "$literal"*) current=$replacement${current#"$literal"}; substituted=1 ;; esac
            ;;
        *'$')
            literal=${pattern%$}
            case "$literal" in *'['*|*']'*|*'('*|*')'*|*'\\'*|*'.'*|*'*'*|*'+'*|*'?'*) fallback_error "$subst" ;; esac
            case "$current" in *"$literal") current=${current%"$literal"}$replacement; substituted=1 ;; esac
            ;;
        *)
            normalized=$(literal_replace_all "$pattern" '[@]' '@')
            pattern=$normalized
            case "$replacement" in *'&'*|*'\\'*) fallback_error "$subst" ;; esac
            case "$pattern" in
                *'['*|*']'*|*'('*|*')'*|*'\\'*|*'.*'*|*'^'*|*'$'*) fallback_error "$subst" ;;
            esac
            case "$current" in
                *"$pattern"*)
                    if [ "$want_global" = 1 ]; then
                        current=$(literal_replace_all "$current" "$pattern" "$replacement")
                    else
                        prefix=${current%%"$pattern"*}
                        suffix=${current#*"$pattern"}
                        current=$prefix$replacement$suffix
                    fi
                    substituted=1
                    ;;
            esac
            ;;
    esac
    if [ "$want_print" = 1 ] && [ "$substituted" = 1 ]; then emit_current; fiB\WÜØÜ\

BÂØÜ\IBØ\ÙHØÜ\[\
HÈ[WÛÈY\HHH	[Z]ØÝ\[ÎÂ
H[Z]ØÝ\[ÎÂ
H[]YLHÎÂÐP×ÒSUÜÊBØ\ÙHÝ\[[
P×ÒSU
H\WÜÝXÝÜØÜ\ËÐP×ÒSUßHÎÈ\ØXÂÎÂÊH\WÜÝXÝØÜ\ÎÂ
H[XÚ×Ù\ÜØÜ\ÎÂ\ØXÂB×Ü[LØÜ\ÏB[\ÏBÚ[HÈÈYÝNÈÂ\ÏINÈÚYØ\ÙH\È[[H×Ü[LHÎÂYJBÈÈYÝH[XÚ×Ù\Ü	ËYHÚ]Ý]ØÜ\	ÂØÜ\INÈÚYØÜ\ÏHÜØÜ\ßIÜØÜ\ÎÂIØÜ\ÎÂ[_Y[B×Ü[LBÈÈYÝH[XÚ×Ù\Ü\ÈÚ]Ý]ØÜ\ØÜ\INÈÚYØÜ\ÏHÜØÜ\ßIÜØÜ\ÎÂIØÜ\ÎÂYJHØÜ\IØ\ÈËY_NÈØÜ\ÏHÜØÜ\ßIÜØÜ\ÎÂIØÜ\ÎÂKJHÚ[HÈÈYÝNÈÈ[OINÈÚYÈ[\ÏHÙ[\ßIÙ[\ÎÂI[HÈÛHÎÂJH[XÚ×Ù\Ü\ÈÎÂ
BYÈ^ØÜ\ÈNÈ[ØÜ\ÏI\ÎÈ[ÙH[\ÏHÙ[\ßIÙ[\ÎÂI\ÈÈBÎÂ\ØXÂÛBÈ[ØÜ\ÈH[XÚ×Ù\Ü	ÏZ\ÜÚ[ÈØÜ\Â[WÛÏLØÙ\Ü×ÜÝX[J
BÂÚ[HÈÂ[OBYQÏHXY\[NÈ[YÛ]Û[OLNÈ[ÙHÏIÎÈYÛ]Û[OLÈÈ[[HHXZÎÈB[WÛÏI

[WÛÈ
ÈJJBÝ\[I[B[]YLÛÚYÏIQÂQÏIÂÂÜØÜ\[	ØÜ\ÎÈÂ\WÜØÜ\ØÜ\È[]YHHXZÂÛBQÏIÛÚYÂYÈ[]YHH	È×Ü[HNÈ[[Z]ØÝ\[ÈBÈYÛ]Û[HHHHXZÂÛBBYÈ^[\ÈNÈ[ØÙ\Ü×ÜÝX[B[ÙBÛÚYÏIQÂQÏIÂÂÜ[H[	[\ÎÈÂÈ\[HHÈ[	Ù\ÜÒÚ[ÙY[XÚÈØ[ÝXY	\×È[HÈ^]ÈBØÙ\Ü×ÜÝX[H[HÛBQÏIÛÚYÂB