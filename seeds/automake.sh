#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an existing GNU Automake/aclocal pair for native source generation.
# This seed does not bootstrap Automake or change the Autoconf cycle boundary.
set -eu

marker=whp-qemu-automake-seed-adapter
if [ "${1:-}" = --whp-automake-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

seed_resolve()
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
    probe=$("$candidate" --whp-automake-adapter-probe 2>/dev/null || true)
    [ "$probe" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

seed_version()
(
    candidate=$1
    banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        *'(GNU automake)'*) ;;
        *) exit 1 ;;
    esac
    version=${first##* }
    case "$version" in
        [0-9]*.[0-9]*) ;;
        *) exit 1 ;;
    esac
    case "$version" in
        *[!0-9.]*|*..*|*.) exit 1 ;;
    esac
    printf '%s\n' "$version"
)

seed_pair()
(
    explicit_automake=${WHP_AUTOMAKE_SEED:-${AUTOMAKE:-}}
    explicit_aclocal=${WHP_ACLOCAL_SEED:-${ACLOCAL:-}}
    if [ -n "$explicit_automake" ]; then
        automake=$(seed_resolve "$explicit_automake") || {
            printf 'error: invalid explicit GNU Automake seed: %s\n' "$explicit_automake" >&2
            exit 1
        }
    elif [ -n "$explicit_aclocal" ]; then
        # A pinned aclocal also identifies its Automake installation. The
        # inverse of the normal sibling lookup prevents PATH from mixing
        # GNU Automake releases when aclocal alone is selected.
        aclocal=$(seed_resolve "$explicit_aclocal") || {
            printf 'error: invalid explicit aclocal seed: %s\n' "$explicit_aclocal" >&2
            exit 1
        }
        automake=$(seed_resolve "${aclocal%/*}/automake") || {
            printf 'error: selected aclocal has no adjacent Automake: %s\n' "$aclocal" >&2
            exit 1
        }
    else
        automake=$(seed_resolve automake) || {
            printf '%s\n' 'error: no usable GNU Automake seed on PATH' >&2
            exit 1
        }
    fi

    # Prefer the executable installed alongside the selected Automake. This
    # avoids pairing a Homebrew/managed Automake with a different PATH aclocal.
    if [ -n "$explicit_aclocal" ]; then
        aclocal=$(seed_resolve "$explicit_aclocal") || {
            printf 'error: invalid explicit aclocal seed: %s\n' "$explicit_aclocal" >&2
            exit 1
        }
    elif [ -x "${automake%/*}/aclocal" ]; then
        aclocal=$(seed_resolve "${automake%/*}/aclocal") || exit 1
    else
        # A split installation is allowed only with an explicit partner.
        printf '%s\n' 'error: selected Automake has no adjacent aclocal; specify WHP_ACLOCAL_SEED for a split installation' >&2
        exit 1
    fi

    av=$(seed_version "$automake") || {
        printf 'error: GNU Automake version is not usable: %s\n' "$automake" >&2
        exit 1
    }
    lv=$(seed_version "$aclocal") || {
        printf 'error: GNU aclocal version is not usable: %s\n' "$aclocal" >&2
        exit 1
    }
    [ "$av" = "$lv" ] || {
        printf 'error: Automake/aclocal version mismatch: %s != %s\n' "$av" "$lv" >&2
        exit 1
    }
    printf '%s\n%s\n' "$automake" "$aclocal"
)

# A matching GNU version banner does not prove that aclocal can find the
# installed Automake macros. This particularly matters when macOS/Homebrew
# has relocated one tool or its shared data directory.
# Validate the *two distinct* Automake data roots. aclocal --print-ac-dir
# reports the optional unversioned system-wide directory, not the required
# aclocal-$APIVERSION macros. Derive the latter from automake --print-libdir.
seed_check_macros()
(
    selected_automake=$1
    selected_aclocal=$2
    unset PERL5LIB PERLLIB PERL5OPT PERL5DB PERL_LOCAL_LIB_ROOT
    unset PERL_MM_OPT PERL_MB_OPT ACLOCAL_PATH AUTOMAKE_LIBDIR
    LC_ALL=C
    export LC_ALL
    system_dir=$("$selected_aclocal" --print-ac-dir) || {
        printf 'error: selected aclocal cannot report its system macro directory: %s\n' \
            "$selected_aclocal" >&2
        exit 1
    }
    library_dir=$("$selected_automake" --print-libdir) || {
        printf 'error: selected Automake cannot report its library directory: %s\n' \
            "$selected_automake" >&2
        exit 1
    }
    case "$system_dir" in
        /*) ;;
        *) printf 'error: aclocal system macro directory is not absolute: %s\n' \
               "$system_dir" >&2; exit 1 ;;
    esac
    case "$library_dir" in
        */automake-[0-9]*)
            api_version=${library_dir##*/automake-}
            case "$api_version" in
                *[!0-9.]*|*..*|*.)
                    printf 'error: Automake library version is malformed: %s\n' \
                        "$library_dir" >&2
                    exit 1 ;;
            esac ;;
        *)
            printf 'error: Automake library directory is unexpected: %s\n' \
                "$library_dir" >&2
            exit 1 ;;
    esac
    case "$system_dir$library_dir" in
        *'
'*)
            printf '%s\n' 'error: Automake reported multiple macro directories' >&2
            exit 1 ;;
    esac
    versioned_dir=${library_dir%/*}/aclocal-$api_version
    for file in "$library_dir/Automake/Config.pm" \
                "$library_dir/am/header-vars.am" \
                "$versioned_dir/init.m4" \
                "$versioned_dir/amversion.m4"; do
        if [ ! -r "$file" ]; then
            printf 'error: Automake installation lacks required source-generation data: %s (automake %s, aclocal %s)\n' \
                "$file" "$selected_automake" "$selected_aclocal" >&2
            exit 1
        fi
    done
    printf 'WHP Automake libraries: %s; aclocal macros: %s\n' \
        "$library_dir" "$versioned_dir"
)

pair=$(seed_pair) || exit 1
automake=${pair%%'
'*}
aclocal=${pair#*'
'}
case "${1:-}" in
    --print-seed|--print-automake) printf '%s\n' "$automake" ;;
    --print-aclocal) printf '%s\n' "$aclocal" ;;
    --check-macros) seed_check_macros "$automake" "$aclocal" ;;
    --check)
        printf 'WHP GNU Automake seed: %s\nWHP GNU aclocal seed: %s\n' "$automake" "$aclocal" ;;
    --aclocal)
        shift
        exec "$aclocal" "$@" ;;
    *)
        exec "$automake" "$@" ;;
esac
