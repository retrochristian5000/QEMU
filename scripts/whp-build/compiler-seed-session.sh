#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Build-invocation native C admission reuse. No on-disk cache.
# Only build.sh publishes a fresh admission after a successful full probe.

whp_cc_session_context()
(
    # The probe sanitizes target flags; retain the environment which may
    # change the native compiler, SDK, linker or its default configuration.
    printf '%s\n' "${PATH:-}" "${SDKROOT:-}" "${DEVELOPER_DIR:-}" \
        "${WHP_XCRUN_SEED:-}" "${WHP_CLANG_SEED:-}" "${HOME:-}" \
        "${MACOSX_DEPLOYMENT_TARGET:-}" "${WHP_NATIVE_ARCH:-}"
)

whp_cc_session_fingerprint()
(
    candidate=$1
    case "$candidate" in /*) ;; *) exit 1 ;; esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    # Preserve the driver's invocation name but identify its symlink target.
    for tool in /usr/bin/stat /bin/stat; do
        [ -x "$tool" ] || continue
        if identity=$(LC_ALL=C "$tool" -Lc '%d:%i:%s:%y:%z' "$candidate" 2>/dev/null) &&
           [ -n "$identity" ]; then
            printf '%s\n' "$identity"
            exit 0
        fi
        if identity=$(LC_ALL=C "$tool" -Lf '%d:%i:%z:%m:%c' "$candidate" 2>/dev/null) &&
           [ -n "$identity" ]; then
            printf '%s\n' "$identity"
            exit 0
        fi
    done
    exit 1
)

whp_cc_session_clear()
{
    unset WHP_CC_SESSION_PATH WHP_CC_SESSION_REQUEST \
        WHP_CC_SESSION_CONTEXT WHP_CC_SESSION_FINGERPRINT
}

whp_cc_session_begin()
{
    whp_cc_session_clear
    WHP_CC_SESSION_PATH=${CC_FOR_BUILD:-}
    WHP_CC_SESSION_REQUEST=${WHP_CC_SEED:-}
    if WHP_CC_SESSION_FINGERPRINT=$(whp_cc_session_fingerprint "$WHP_CC_SESSION_PATH") &&
       WHP_CC_SESSION_CONTEXT=$(whp_cc_session_context); then
        export WHP_CC_SESSION_PATH WHP_CC_SESSION_REQUEST \
            WHP_CC_SESSION_CONTEXT WHP_CC_SESSION_FINGERPRINT
    else
        # An unavailable stat implementation is not a build failure.
        whp_cc_session_clear
    fi
}

whp_cc_session_lookup()
(
    selected=${WHP_CC_SESSION_PATH:-}
    [ -n "$selected" ] && [ "$selected" = "${CC_FOR_BUILD:-}" ] ||
        exit 1
    # An explicit child override is a different admission request unless
    # it names the already-admitted absolute path.
    requested=${WHP_CC_SEED:-}
    [ "$requested" = "${WHP_CC_SESSION_REQUEST:-}" ] ||
        [ "$requested" = "$selected" ] || exit 1
    # Relative explicit selections may resolve differently after a chdir.
    case "$requested" in /*|'') ;; */*) exit 1 ;; esac
    [ "$(whp_cc_session_context)" = "${WHP_CC_SESSION_CONTEXT:-}" ] ||
        exit 1
    current=$(whp_cc_session_fingerprint "$selected") || exit 1
    [ "$current" = "${WHP_CC_SESSION_FINGERPRINT:-}" ] || exit 1
    printf '%s\n' "$selected"
)
