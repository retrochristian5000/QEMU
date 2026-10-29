#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Resolve the selected Apple developer installation. Full Xcode and standalone
# Command Line Tools (CLT) are separate roots and must not be mixed.

whp_apple_developer_root()
(
    if [ -n "${DEVELOPER_DIR:-}" ]; then
        developer=$DEVELOPER_DIR
    else
        command -v xcode-select >/dev/null 2>&1 || {
            printf '%s\n' 'error: xcode-select is unavailable' >&2
            exit 1
        }
        developer=$(xcode-select -p 2>/dev/null) || {
            printf '%s\n' 'error: no active Apple developer directory' >&2
            exit 1
        }
    fi
    # DEVELOPER_DIR can name the Xcode.app bundle instead of Contents/Developer.
    case "$developer" in *.app) developer=$developer/Contents/Developer ;; esac
    [ -d "$developer" ] || {
        printf 'error: selected Apple developer directory does not exist: %s\n' "$developer" >&2
        exit 1
    }
    CDPATH= cd -P -- "$developer" && pwd -P
)

whp_apple_developer_kind()
{
    case "$1" in
        /Library/Developer/CommandLineTools) printf '%s\n' clt ;;
        */Contents/Developer) printf '%s\n' xcode ;;
        *) printf '%s\n' other ;;
    esac
}

whp_apple_require_under_root()
(
    candidate=$1
    label=$2
    developer=$(whp_apple_developer_root) || exit 1
    [ -d "$candidate" ] || {
        printf 'error: %s directory does not exist: %s\n' "$label" "$candidate" >&2
        exit 1
    }
    actual=$(CDPATH= cd -P -- "$candidate" && pwd -P) || exit 1
    case "$actual" in
        "$developer"|"$developer"/*) ;;
        *)
            printf 'error: %s is outside the selected Apple developer directory\n' "$label" >&2
            printf '  selected: %s\n  supplied: %s\n' "$developer" "$actual" >&2
            exit 1
            ;;
    esac
)

whp_apple_find_tool()
(
    name=$1
    whp_apple_developer_root >/dev/null || exit 1
    command -v xcrun >/dev/null 2>&1 || {
        printf '%s\n' 'error: xcrun is unavailable' >&2
        exit 1
    }
    tool=$(xcrun --sdk macosx --find "$name" 2>/dev/null) || {
        printf 'error: selected Apple developer directory has no %s tool\n' "$name" >&2
        exit 1
    }
    [ -x "$tool" ] || {
        printf 'error: selected Apple tool is not executable: %s\n' "$tool" >&2
        exit 1
    }
    whp_apple_require_under_root "${tool%/*}" "$name tool" || exit 1
    printf '%s\n' "$tool"
)

whp_apple_check_sdkroot()
(
    sdk=$1
    [ -d "$sdk" ] || {
        printf 'error: selected macOS SDK does not exist: %s\n' "$sdk" >&2
        exit 1
    }
    canonical=$(CDPATH= cd -P -- "$sdk" && pwd -P) || exit 1
    case "${canonical##*/}" in
        MacOSX*.sdk) ;;
        *)
            printf 'error: not a native macOS SDK: %s\n' "$canonical" >&2
            exit 1
            ;;
    esac
    whp_apple_require_under_root "$canonical" "macOS SDK"
)

whp_apple_find_sdk()
(
    whp_apple_developer_root >/dev/null || exit 1
    command -v xcrun >/dev/null 2>&1 || exit 1
    sdk=$(xcrun --sdk macosx --show-sdk-path 2>/dev/null) || {
        printf '%s\n' 'error: selected Apple developer directory has no macOS SDK' >&2
        exit 1
    }
    whp_apple_check_sdkroot "$sdk" || exit 1
    printf '%s\n' "$sdk"
)
