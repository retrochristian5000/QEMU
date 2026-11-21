#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Explicit C cross-compiler adapter. Native host tools must use cc.sh.
# A cross object is compiled but is never linked, run, or mistaken for host CC.
set -eu

marker=whp-qemu-cross-cc-seed-adapter
case "${1:-}" in
    --whp-cross-cc-adapter-probe|--whp-cc-adapter-probe)
        printf '%s\n' "$marker"
        exit 0 ;;
esac

cross_fail()
{
    printf 'error: cross C seed: %s\n' "$1" >&2
    exit 2
}

cross_environment()
{
    # Native bootstrap/SDK variables must not silently change a cross driver.
    unset CCC_OVERRIDE_OPTIONS
    unset CC_FOR_BUILD CXX_FOR_BUILD WHP_CC_SEED WHP_CXX_SEED
    unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH
    unset LIBRARY_PATH LD_LIBRARY_PATH LD_PRELOAD
    unset DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH DYLD_INSERT_LIBRARIES
    unset COMPILER_PATH GCC_EXEC_PREFIX
    unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS OBJCXXFLAGS LIBS
    unset SDKROOT MACOSX_DEPLOYMENT_TARGET IPHONEOS_DEPLOYMENT_TARGET
    unset IPHONESIMULATOR_DEPLOYMENT_TARGET TVOS_DEPLOYMENT_TARGET
    unset WATCHOS_DEPLOYMENT_TARGET XROS_DEPLOYMENT_TARGET
    unset TARGET TARGET_ARCH TARGET_OS TARGET_ABI TARGET_VENDOR TARGET_TRIPLE
    unset TARGET_SYSROOT TARGET_CC TARGET_CXX TARGET_CPP TARGET_LD
    unset CC_FOR_TARGET CXX_FOR_TARGET CMAKE_C_COMPILER_TARGET
    unset CMAKE_CXX_COMPILER_TARGET CMAKE_ASM_COMPILER_TARGET
    unset CARGO_BUILD_TARGET CROSS_COMPILE
}

cross_initialize()
{
    cross_target=${WHP_CROSS_TARGET:-}
    cross_kind=${WHP_CROSS_CC_KIND:-}
    cross_request=${WHP_CROSS_CC_SEED:-}
    cross_sysroot=${WHP_CROSS_SYSROOT:-}

    case "$cross_target" in
        *-*) ;;
        *) cross_fail 'WHP_CROSS_TARGET must name an explicit target triple' ;;
    esac
    case "$cross_target" in
        *[!A-Za-z0-9_.+-]*|""|-*|*-)
            cross_fail 'WHP_CROSS_TARGET contains invalid triple characters' ;;
    esac
    case "$cross_kind" in
        clang|gcc) ;;
        *) cross_fail 'WHP_CROSS_CC_KIND must be clang or gcc' ;;
    esac
    [ -n "$cross_request" ] || cross_fail 'WHP_CROSS_CC_SEED is required; native CC is never a fallback'
    case "$cross_request" in
        */*) cross_driver=$cross_request ;;
        *[[:space:]]*) cross_fail 'WHP_CROSS_CC_SEED must name one executable, not a command line' ;;
        *) cross_driver=$(command -v "$cross_request" 2>/dev/null || true) ;;
    esac
    [ -n "$cross_driver" ] && [ -f "$cross_driver" ] && [ -x "$cross_driver" ] ||
        cross_fail 'WHP_CROSS_CC_SEED is not an executable file'
    case "$cross_driver" in
        */*)
            cross_dir=$(CDPATH= cd -P -- "${cross_driver%/*}" && pwd -P) ||
                cross_fail 'cannot resolve cross compiler directory'
            cross_driver=$cross_dir/${cross_driver##*/}
            ;;
        *) cross_fail 'cross compiler cannot be resolved to a pathname' ;;
    esac

    # Check adapter identity before --version, not just a pathname suffix.
    for probe in --whp-cross-cc-adapter-probe --whp-cc-adapter-probe; do
        identity=$("$cross_driver" "$probe" 2>/dev/null || true)
        case "$identity" in
            whp-qemu-*-seed-adapter)
                cross_fail 'cross compiler resolves to another WHP seed adapter' ;;
        esac
    done

    if [ -n "$cross_sysroot" ]; then
        case "$cross_sysroot" in
            /*) ;;
            *) cross_fail 'WHP_CROSS_SYSROOT must be an absolute target SDK/sysroot directory' ;;
        esac
        [ -d "$cross_sysroot" ] || cross_fail 'WHP_CROSS_SYSROOT does not exist'
        cross_sysroot=$(CDPATH= cd -P -- "$cross_sysroot" && pwd -P) ||
            cross_fail 'cannot resolve target sysroot'
    fi

    cross_environment
    "$cross_driver" --version >/dev/null 2>&1 ||
        cross_fail 'selected cross compiler fails --version'

    if [ "$cross_kind" = clang ]; then
        actual=$("$cross_driver" "--target=$cross_target" -dumpmachine 2>/dev/null) ||
            cross_fail 'selected Clang cannot report the requested cross target'
    else
        actual=$("$cross_driver" -dumpmachine 2>/dev/null) ||
            cross_fail 'selected GCC cross compiler cannot report its target'
    fi
    [ "$actual" = "$cross_target" ] || {
        printf 'error: cross C seed: requested target %s differs from compiler target %s\n' \
            "$cross_target" "$actual" >&2
        exit 2
    }
    case "$actual" in
        *[[:space:]]*) cross_fail 'cross compiler target has invalid whitespace' ;;
    esac
}

cross_validate_args()
{
    # Prevent a later compiler flag from undoing the exact checked triple or
    # sysroot. Architecture-specific -mcpu/-march/-mabi remain caller-owned.
    for argument do
        case "$argument" in
            --target|--target=*|-target|-target=*|-arch|-arch=*|-isysroot|-isysroot*|\
            --sysroot|--sysroot=*|-m32|-m64|-Xclang|-Xarch_*)
                cross_fail 'command-line target, SDK, or arch override is forbidden; use WHP_CROSS_TARGET/WHP_CROSS_SYSROOT' ;;
        esac
    done
}

cross_run()
{
    if [ -n "$cross_sysroot" ]; then
        set -- "--sysroot=$cross_sysroot" "$@"
    fi
    if [ "$cross_kind" = clang ]; then
        set -- "--target=$cross_target" "$@"
    fi
    "$cross_driver" "$@"
}

cross_check()
(
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-cross-cc.XXXXXXXX") ||
        cross_fail 'cannot allocate private cross compiler probe directory'
    trap 'rm -rf -- "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    printf '%s\n' 'int whp_cross_cc_probe(void) { return 71; }' > "$tmp/probe.c"
    if ! cross_run -c "$tmp/probe.c" -o "$tmp/probe.o" >"$tmp/stdout" 2>"$tmp/stderr"; then
        printf 'error: cross C seed: cross compile-only probe failed for %s (%s)\n' \
            "$cross_target" "$cross_driver" >&2
        cat "$tmp/stderr" >&2
        exit 1
    fi
    [ -s "$tmp/probe.o" ] || cross_fail 'compiler produced no cross object'
)

case "${1:-}" in
    --print-cxx|--print-cc)
        cross_fail 'use --print-seed for the target-aware wrapper, never a bare CC path' ;;
esac

cross_initialize
case "${1:-}" in
    --print-target)
        printf '%s\n' "$cross_target" ;;
    --print-driver)
        printf '%s\n' "$cross_driver" ;;
    --print-seed)
        entry=$0
        case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
        count=0
        while [ -L "$entry" ]; do
            count=$((count + 1))
            [ "$count" -le 16 ] || cross_fail 'cross seed symlink loop'
            link=$(readlink "$entry") || exit 1
            case "$link" in
                /*) entry=$link ;;
                *) entry=${entry%/*}/$link ;;
            esac
        done
        directory=$(CDPATH= cd -P -- "${entry%/*}" && pwd -P) || exit 1
        printf '%s/%s\n' "$directory" "${entry##*/}" ;;
    --check)
        cross_check || exit 1
        printf 'WHP C cross seed: %s (%s, target %s; compile-only verified)\n' \
            "$cross_driver" "$cross_kind" "$cross_target" ;;
    *)
        cross_validate_args "$@"
        if [ -n "$cross_sysroot" ]; then
            set -- "--sysroot=$cross_sysroot" "$@"
        fi
        if [ "$cross_kind" = clang ]; then
            set -- "--target=$cross_target" "$@"
        fi
        exec "$cross_driver" "$@" ;;
esac
