#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select a coherent installed archive/indexer pair for native LLVM bootstrap.
# Called only after a cached LLVM toolchain misses; never builds LLVM itself.
set -eu

[ "$#" -eq 1 ] && [ -n "$1" ] || {
    printf '%s\n' 'usage: native-archive-pair.sh NATIVE_C_COMPILER' >&2
    exit 2
}
compiler=$1
entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || exit 1
    link=$(readlink "$entry") || exit 1
    case "$link" in /*) entry=$link ;; *) entry=${entry%/*}/$link ;; esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/../.." && pwd -P) || exit 1

selection=${WHP_NATIVE_LLVM_ARCHIVE_PROVIDER:-auto}
case "$selection" in
    auto|native|gnu|llvm) ;;
    *) printf 'error: invalid WHP_NATIVE_LLVM_ARCHIVE_PROVIDER: %s\n' "$selection" >&2
       exit 2 ;;
esac
# Existing explicit build-machine tools have priority over inferred providers.
generic_request=no
[ -z "${WHP_AR_SEED:-}${AR_FOR_BUILD:-}${WHP_RANLIB_SEED:-}${RANLIB_FOR_BUILD:-}" ] ||
    generic_request=yes
gnu_request=no
[ -z "${WHP_GNU_AR_SEED:-}" ] || gnu_request=yes
llvm_request=no
[ -z "${WHP_LLVM_AR_SEED:-}${WHP_LLVM_RANLIB_SEED:-}" ] || llvm_request=yes
if [ "$gnu_request" = yes ] && [ "$llvm_request" = yes ]; then
    printf '%s\n' 'error: GNU and LLVM archive seeds were both explicitly selected' >&2
    exit 1
fi
if [ "$generic_request" = yes ] &&
   { [ "$gnu_request" = yes ] || [ "$llvm_request" = yes ]; }; then
    printf '%s\n' 'error: generic and specialized archive overrides conflict' >&2
    exit 1
fi

case "$selection" in
    auto)
        if [ "$generic_request" = yes ]; then
            selection=native
            mandatory=yes
        elif [ "$gnu_request" = yes ]; then
            selection=gnu
            mandatory=yes
        elif [ "$llvm_request" = yes ]; then
            selection=llvm
            mandatory=yes
        else
            # Compiler identity is only a preference; archive/native index
            # admission still determines whether specialization is usable.
            version=$(LC_ALL=C "$compiler" --version 2>/dev/null || true)
            case "$version" in
                *'clang version '*) selection=llvm ;;
                *'gcc (GCC)'*|*'gcc (Debian '*|*'gcc (Ubuntu '*|*'gcc version '*)
                    selection=gnu ;;
                *) selection=native ;;
            esac
            mandatory=no
        fi
        ;;
    *)
        mandatory=yes
        if [ "$generic_request" = yes ] && [ "$selection" != native ]; then
            printf '%s\n' 'error: explicit generic archive conflicts with requested specialized provider' >&2
            exit 1
        fi
        if [ "$gnu_request" = yes ] && [ "$selection" != gnu ]; then
            printf '%s\n' 'error: GNU archive override conflicts with requested provider' >&2
            exit 1
        fi
        if [ "$llvm_request" = yes ] && [ "$selection" != llvm ]; then
            printf '%s\n' 'error: LLVM archive override conflicts with requested provider' >&2
            exit 1
        fi
        ;;
esac

select_llvm_pair()
{
    ar=$(/bin/sh "$root/seeds/llvm-ar.sh" --print-seed) || return 1
    ranlib=$(WHP_LLVM_AR_SEED="$ar" \
        /bin/sh "$root/seeds/llvm-ranlib.sh" --print-seed) || return 1
    family=llvm
}

select_gnu_pair()
{
    ar=$(/bin/sh "$root/seeds/GNUar.sh" --print-seed) || return 1
    case "${ar##*/}" in
        gar) other=granlib ;;
        ar) other=ranlib ;;
        *) printf 'error: GNU archiver has no recognized ranlib sibling: %s\n' "$ar" >&2
           return 1 ;;
    esac
    candidate="${ar%/*}/$other"
    [ -x "$candidate" ] || {
        printf 'error: GNU ranlib sibling is missing: %s\n' "$candidate" >&2
        return 1
    }
    # GNU LTO still needs a separately checked GCC plugin. Here require
    # coherent Binutils releases and a real unindexed-archive probe.
    ar_version=$(LC_ALL=C "$ar" --version 2>/dev/null) || return 1
    ranlib_version=$(LC_ALL=C "$candidate" --version 2>/dev/null) || return 1
    ar_first=${ar_version%%'
'*}
    ranlib_first=${ranlib_version%%'
'*}
    case "$ranlib_first" in
        'GNU ranlib ('*'GNU Binutils'*') '*) ;;
        *) printf 'error: selected ranlib is not GNU Binutils: %s\n' "$candidate" >&2
           return 1 ;;
    esac
    [ "${ar_first##* }" = "${ranlib_first##* }" ] || {
        printf 'error: GNU ar/ranlib releases disagree: %s vs %s\n' \
            "$ar_first" "$ranlib_first" >&2
        return 1
    }
    ranlib=$(WHP_AR_SEED="$ar" WHP_RANLIB_SEED="$candidate" \
        /bin/sh "$root/seeds/ranlib.sh" --print-seed) || return 1
    family=gnu
}

select_native_pair()
{
    ar=$(/bin/sh "$root/seeds/ar.sh" --print-seed) || return 1
    ranlib=$(WHP_AR_SEED="$ar" \
        /bin/sh "$root/seeds/ranlib.sh" --print-seed) || return 1
    family=native
}

case "$selection" in
    gnu)
        if ! select_gnu_pair; then
            if [ "$mandatory" = yes ]; then
                printf '%s\n' 'error: required GNU archive/indexer pair failed admission' >&2
                exit 1
            fi
            printf '%s\n' 'WHP archive preference: GNU pair unavailable; using native fallback' >&2
            select_native_pair || exit 1
        fi ;;
    llvm)
        if ! select_llvm_pair; then
            if [ "$mandatory" = yes ]; then
                printf '%s\n' 'error: required LLVM archive/indexer pair failed admission' >&2
                exit 1
            fi
            printf '%s\n' 'WHP archive preference: LLVM pair unavailable; using native fallback' >&2
            select_native_pair || exit 1
        fi ;;
    native) select_native_pair || exit 1 ;;
esac

case "$ar:$ranlib" in
    *'
'*) printf '%s\n' 'error: archive tool path contains a newline' >&2; exit 1 ;;
esac
printf 'WHP native archive provider: %s (ar=%s; ranlib=%s)\n' \
    "$family" "$ar" "$ranlib" >&2
printf '%s\n%s\n' "$ar" "$ranlib"
