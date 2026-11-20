#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Resolve the selected Apple developer installation. Full Xcode and standalone
# Command Line Tools (CLT) are separate roots and must not be mixed.

whp_apple_developer_root()
(
    if [ -n "${DEVELOPER_DIR:-}" ]; then
        developer=$DEVELOPER_DIR
        origin=DEVELOPER_DIR
    else
        origin=xcode-select
        command -v xcode-select >/dev/null 2>&1 || {
            printf '%s\n' 'error: xcode-select is unavailable' >&2
            exit 1
        }
        developer=$(xcode-select -p 2>/dev/null) || {
            printf '%s\n' 'error: no active Apple developer directory (xcode-select -p failed)' >&2
            printf '%s\n' '  Select an installed Xcode or Command Line Tools directory before building.' >&2
            exit 1
        }
    fi
    # DEVELOPER_DIR can name the Xcode.app bundle instead of Contents/Developer.
    case "$developer" in *.app) developer=$developer/Contents/Developer ;; esac
    [ -d "$developer" ] || {
        printf 'error: selected Apple developer directory does not exist: %s (source: %s)\n' \
            "$developer" "$origin" >&2
        printf '%s\n' '  The selected Xcode/CLT installation may have been moved or removed.' >&2
        printf '%s\n' '  Select an installed developer root (xcode-select --switch), or set DEVELOPER_DIR for this build.' >&2
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
    # Validate the selected installation before invoking xcrun: an obsolete
    # xcode-select entry must not silently choose a different Xcode/CLT.
    developer=$(whp_apple_developer_root) || exit 1
    sdk=macosx
    if [ -n "${SDKROOT:-}" ]; then
        sdk=$(DEVELOPER_DIR="$developer" whp_apple_select_sdk) || exit 1
    fi
    whp_xcrun_tool=${WHP_XCRUN_SEED:-xcrun}
    command -v "$whp_xcrun_tool" >/dev/null 2>&1 || {
        printf '%s\n' 'error: xcrun is unavailable' >&2
        exit 1
    }
    tool=$(DEVELOPER_DIR="$developer" "$whp_xcrun_tool" --sdk "$sdk" --find "$name" 2>/dev/null) || {
        printf 'error: selected Apple developer directory has no %s tool: %s\n' "$name" "$developer" >&2
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
    # Confirm the selected root before asking xcrun for an SDK. Pin that
    # root only for discovery and verification; do not change global state.
    developer=$(whp_apple_developer_root) || exit 1
    whp_xcrun_tool=${WHP_XCRUN_SEED:-xcrun}
    command -v "$whp_xcrun_tool" >/dev/null 2>&1 || {
        printf '%s\n' 'error: xcrun is unavailable' >&2
        exit 1
    }
    sdk=$(DEVELOPER_DIR="$developer" "$whp_xcrun_tool" --sdk macosx --show-sdk-path 2>/dev/null) || {
        printf 'error: selected Apple developer directory has no macOS SDK: %s\n' "$developer" >&2
        exit 1
    }
    DEVELOPER_DIR="$developer" whp_apple_check_sdkroot "$sdk" || exit 1
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

# Enforce active SDK precedence at build entry points, not on every
# compiler-seed lookup. Deliberately older SDKs require an explicit opt-in.
whp_apple_sdk_version_is_older()
{
    awk -v selected="$1" -v active="$2" '
        BEGIN {
            n = split(selected, s, /[.]/)
            m = split(active, a, /[.]/)
            if (n < 1 || n > 3 || m < 1 || m > 3) exit 2
            for (i = 1; i <= n; i++) if (s[i] !~ /^[0-9]+$/) exit 2
            for (i = 1; i <= m; i++) if (a[i] !~ /^[0-9]+$/) exit 2
            for (i = 1; i <= 3; i++) {
                left = i <= n ? s[i] + 0 : 0
                right = i <= m ? a[i] + 0 : 0
                if (left < right) exit 0
                if (left > right) exit 1
            }
            exit 1
        }
    '
}

whp_apple_require_current_sdk()
(
    selected_sdk=$1
    case "${WHP_MACOS_ALLOW_OLDER_SDK:-0}" in
        0) ;;
        1) exit 0 ;;
        *)
            printf 'error: WHP_MACOS_ALLOW_OLDER_SDK must be 0 or 1\n' >&2
            exit 1
            ;;
    esac

    # Compare only against the active SDK in the selected Xcode/CLT root.
    # Never select a different developer installation implicitly.
    active_sdk=$(SDKROOT= whp_apple_find_sdk 2>/dev/null || true)
    [ -n "$active_sdk" ] || exit 0
    [ "$selected_sdk" = "$active_sdk" ] && exit 0

    developer=$(whp_apple_developer_root) || exit 1
    whp_xcrun_tool=${WHP_XCRUN_SEED:-xcrun}
    selected_version=$(DEVELOPER_DIR="$developer" "$whp_xcrun_tool" \
        --sdk "$selected_sdk" --show-sdk-version 2>/dev/null) || {
        printf 'error: cannot read the selected macOS SDK version: %s\n' \
            "$selected_sdk" >&2
        exit 1
    }
    active_version=$(DEVELOPER_DIR="$developer" "$whp_xcrun_tool" \
        --sdk "$active_sdk" --show-sdk-version 2>/dev/null) || {
        printf 'error: cannot read the active macOS SDK version: %s\n' \
            "$active_sdk" >&2
        exit 1
    }

    if whp_apple_sdk_version_is_older "$selected_version" "$active_version"; then
        printf '%s\n' \
            "error: selected macOS SDK $selected_version is older than active SDK $active_version." \
            "  selected: $selected_sdk" \
            "  active:   $active_sdk" \
            'Unset stale SDKROOT to use the active SDK, or set' \
            'WHP_MACOS_ALLOW_OLDER_SDK=1 for an intentional compatibility build.' >&2
        exit 1
    else
        status=$?
        if [ "$status" -ne 1 ]; then
            printf 'error: invalid macOS SDK version comparison: %s versus %s\n' \
                "$selected_version" "$active_version" >&2
            exit 1
        fi
    fi
)
