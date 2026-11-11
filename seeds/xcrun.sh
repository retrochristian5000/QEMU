#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# macOS-only root xcrun seed. Never require Apple tools on other platforms.
# Must NOT source macos-developer-tools.sh: its tool selection uses this seed.
set -eu

marker=whp-qemu-xcrun-seed-adapter
if [ "${1:-}" = --whp-xcrun-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

if [ "$(uname -s 2>/dev/null || true)" != Darwin ]; then
    case "${1:-}" in
        --check) printf '%s\n' 'WHP xcrun seed: not applicable (non-macOS)'; exit 0 ;;
    esac
    printf '%s\n' 'error: xcrun is a macOS-only root tool' >&2
    exit 1
fi

resolve()
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
    identity=$("$candidate" --whp-xcrun-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

probe()
(
    candidate=$1
    # Use the currently selected Apple developer directory and macOS SDK.
    # Do not rely on --version: an invalid Xcode/CLT selection can still
    # provide a working xcrun stub.
    sdk=$("$candidate" --sdk macosx --show-sdk-path 2>/dev/null) || exit 1
    [ -d "$sdk" ] || exit 1
    clang=$("$candidate" --sdk macosx --find clang 2>/dev/null) || exit 1
    [ -f "$clang" ] && [ -x "$clang" ] || exit 1
)

select_seed()
{
    if [ -n "${WHP_XCRUN_SEED:-}" ]; then
        candidate=$(resolve "$WHP_XCRUN_SEED") || {
            printf 'error: invalid WHP_XCRUN_SEED: %s\n' "$WHP_XCRUN_SEED" >&2
            return 1
        }
        if [ "${probe:-yes}" = yes ]; then
            probe "$candidate" || {
                printf 'error: WHP_XCRUN_SEED cannot resolve macOS SDK and clang: %s\n' "$candidate" >&2
                return 1
            }
        fi
        printf '%s\n' "$candidate"
        return 0
    fi
    # macOS provides the native developer-tool dispatcher at /usr/bin.
    # PATH alternatives are fallback candidates, not assumed equivalent.
    for value in /usr/bin/xcrun xcrun; do
        candidate=$(resolve "$value") || continue
        if [ "${probe:-yes}" = yes ]; then probe "$candidate" || continue; fi
        printf '%s\n' "$candidate"
        return 0
    done
    printf '%s\n' 'error: no xcrun resolved the selected macOS SDK and clang' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-xcrun) probe=yes; select_seed ;;
    --check)
        probe=yes
        selected=$(select_seed) || exit 1
        printf 'WHP macOS xcrun seed: %s\n' "$selected"
        ;;
    *)
        # Discovery validates once; individual xcrun calls do not repeat probes.
        probe=no
        selected=$(select_seed) || exit 1
        exec "$selected" "$@"
        ;;
esac
