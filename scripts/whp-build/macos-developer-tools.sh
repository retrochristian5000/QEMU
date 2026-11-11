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

# Reject non-macOS platform subtrees even if a misplaced SDK is named
# MacOSX.sdk or a compiler executable has the expected name.
whp_apple_require_macos_platform()
(
    whp_apple_path=$1
    case "$whp_apple_path" in
        */Platforms/MacOSX.platform/Developer/*) ;;
        */Platforms/*)
            printf 'error: non-macOS Apple platform in native bootstrap: %s\n' \
                "$whp_apple_path" >&2
            exit 1
            ;;
    esac
)

whp_apple_find_tool()
(
    name=$1
    tool_class=${2:-developer}
    # /usr/bin carries legitimate Apple shims for native system utilities.
    # Accept those only for a narrow allowlist, never for compiler drivers.
    case "$tool_class" in
        developer) ;;
        system)
            case "$name" in ar|ranlib|nm|strip|lipo|ld) ;;
                *) printf 'error: unsupported Apple system tool: %s\n' "$name" >&2; exit 1 ;;
            esac
            ;;
        *) printf 'error: invalid Apple tool class: %s\n' "$tool_class" >&2; exit 1 ;;
    esac
    sdk=macosx
    if [ -n "${SDKROOT:-}" ]; then
        sdk=$(whp_apple_select_sdk) || exit 1
    else
        whp_apple_developer_root >/dev/null || exit 1
    fi
    whp_xcrun_tool=${WHP_XCRUN_SEED:-xcrun}
    command -v "$whp_xcrun_tool" >/dev/null 2>&1 || {
        printf '%s\n' 'error: xcrun is unavailable' >&2
        exit 1
    }
    tool=$("$whp_xcrun_tool" --sdk "$sdk" --find "$name" 2>/dev/null) || {
        printf 'error: selected Apple developer directory has no %s tool\n' "$name" >&2
        exit 1
    }
    [ -x "$tool" ] || {
        printf 'error: selected Apple tool is not executable: %s\n' "$tool" >&2
        exit 1
    }
    # xcrun --find may resolve an Apple system shim outside the selected
    # developer root. An exact /usr/bin/name is valid only for system tools.
    if [ "$tool_class" = system ] && [ "$tool" = "/usr/bin/$name" ]; then
        printf '%s\n' "$tool"
        exit 0
    fi
    whp_apple_require_under_root "${tool%/*}" "$name tool" || exit 1
    whp_apple_require_macos_platform "$tool" || exit 1
    printf '%s\n' "$tool"
)

whp_apple_check_sdkroot()
(
    sdk=$1
    [ -d "$sdk" ] || {
        printf 'error: selected macOS SDK does not exist: %s\n' "$sdk" >&2
        exit 1
    }
    # Check the requested path as well as the resolved one: an alias inside
    # iPhoneOS.platform must not launder an otherwise valid MacOSX.sdk.
    whp_apple_require_macos_platform "$sdk" || exit 1
    canonical=$(CDPATH= cd -P -- "$sdk" && pwd -P) || exit 1
    case "${canonical##*/}" in
        MacOSX*.sdk) ;;
        *)
            printf 'error: not a native macOS SDK: %s\n' "$canonical" >&2
            exit 1
            ;;
    esac
    whp_apple_require_under_root "$canonical" "macOS SDK" || exit 1
    whp_apple_require_macos_platform "$canonical" || exit 1
    # A directory named MacOSX.sdk is not sufficient: bootstrap components
    # consume POSIX, C library, and Apple platform headers before QEMU builds.
    # Validate their source in the selected SDK rather than searching /usr/include
    # (which is intentionally absent on current macOS installations).
    for header in stdio.h stdlib.h unistd.h sys/types.h TargetConditionals.h; do
        if [ ! -f "$canonical/usr/include/$header" ]; then
            printf 'error: selected macOS SDK is missing system header %s: %s\n' \
                "$header" "$canonical/usr/include/$header" >&2
            exit 1
        fi
    done
)

whp_apple_find_sdk()
(
    # whp_apple_check_sdkroot below verifies the selected developer root and
    # SDK containment. Avoid resolving that same root twice for one lookup.
    whp_xcrun_tool=${WHP_XCRUN_SEED:-xcrun}
    command -v "$whp_xcrun_tool" >/dev/null 2>&1 || {
        printf '%s\n' 'error: xcrun is unavailable' >&2
        exit 1
    }
    sdk=$("$whp_xcrun_tool" --sdk macosx --show-sdk-path 2>/dev/null) || {
        printf '%s\n' 'error: selected Apple developer directory has no macOS SDK' >&2
        exit 1
    }
    whp_apple_check_sdkroot "$sdk" || exit 1
    # Return the same physical SDK path that was actually validated.
    CDPATH= cd -P -- "$sdk" && pwd -P
)

# Resolve the SDK once for consumers that build from another directory.
# No caller should have to interpret a relative SDKROOT or re-resolve a
# symlink after the developer-root and header checks have completed.
whp_apple_select_sdk()
(
    sdk=${SDKROOT:-}
    if [ -n "$sdk" ]; then
        whp_apple_check_sdkroot "$sdk" || exit 1
        CDPATH= cd -P -- "$sdk" && pwd -P
    else
        whp_apple_find_sdk
    fi
)
