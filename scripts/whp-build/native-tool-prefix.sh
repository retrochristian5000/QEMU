#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Read-only discovery of tools installed for the build machine.
# This is not QEMU's runtime INSTALL_PREFIX, a target sysroot, or a PATH shim.

whp_native_tool_prefix_init()
{
    : "${BUILD_DIR:?BUILD_DIR must be selected before native-prefix discovery}"
    if [ -n "${WHP_NATIVE_TOOL_PREFIX:-}" ]; then
        WHP_NATIVE_TOOL_PREFIX_EXPLICIT=1
    else
        WHP_NATIVE_TOOL_PREFIX_EXPLICIT=0
        WHP_NATIVE_TOOL_PREFIX=$BUILD_DIR/deps
    fi
    case "$WHP_NATIVE_TOOL_PREFIX" in
        /*) ;;
        *)
            printf 'error: WHP_NATIVE_TOOL_PREFIX must be absolute: %s\n' \
                "$WHP_NATIVE_TOOL_PREFIX" >&2
            return 2 ;;
    esac
    if [ ! -d "$WHP_NATIVE_TOOL_PREFIX" ] &&
       { [ -f "$WHP_NATIVE_TOOL_PREFIX" ] ||
         [ -L "$WHP_NATIVE_TOOL_PREFIX" ] ||
         [ -p "$WHP_NATIVE_TOOL_PREFIX" ]; }; then
        printf 'error: native tool prefix is not a directory: %s\n' \
            "$WHP_NATIVE_TOOL_PREFIX" >&2
        return 2
    fi
    export WHP_NATIVE_TOOL_PREFIX WHP_NATIVE_TOOL_PREFIX_EXPLICIT
}

# Only named host executables are eligible. Each consumer must still run its
# own version, feature, and ABI checks before invoking the returned candidate.
whp_native_tool_prefix_find()
{
    case "${1:-}" in
        bash|ninja|which|cmake|pkg-config) ;;
        *) return 2 ;;
    esac
    for whp_native_candidate in \
        "$WHP_NATIVE_TOOL_PREFIX/bin/$1" \
        "$WHP_NATIVE_TOOL_PREFIX/$1/bin/$1"; do
        if [ -f "$whp_native_candidate" ] &&
           [ -x "$whp_native_candidate" ]; then
            printf '%s\n' "$whp_native_candidate"
            return 0
        fi
    done
    return 1
}

# Standalone non-mutating inspection: BUILD_DIR=/absolute/path /bin/sh ... --audit
if [ "${0##*/}" = native-tool-prefix.sh ]; then
    case "${1:-}" in
        --audit)
            whp_native_tool_prefix_init || exit $?
            printf 'WHP native tool prefix: %s\n' "$WHP_NATIVE_TOOL_PREFIX"
            for whp_native_name in bash ninja which cmake pkg-config; do
                if whp_native_found=$(whp_native_tool_prefix_find "$whp_native_name"); then
                    printf '%s: candidate (unverified): %s\n' \
                        "$whp_native_name" "$whp_native_found"
                else
                    printf '%s: absent\n' "$whp_native_name"
                fi
            done
            ;;
        *)
            printf '%s\n' 'usage: BUILD_DIR=/absolute/path sh native-tool-prefix.sh --audit' >&2
            exit 2 ;;
    esac
fi
