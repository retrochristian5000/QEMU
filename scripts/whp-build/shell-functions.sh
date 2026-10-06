# Shared POSIX-shell policy helpers for the WHP build bootstrap.
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Keep this module dependency-free: build.sh and host-tools.sh may source it
# before GNU Bash or other managed host tools are available.

whp_normalize_auto_switch()
(
    whp_switch_name=${1:-}
    whp_switch_value=${2:-}

    case "$whp_switch_value" in
        y) whp_switch_value=1 ;;
        n) whp_switch_value=0 ;;
        auto|0|1) ;;
        *)
            printf 'error: %s must be auto, 0, or 1\n' "$whp_switch_name" >&2
            return 1
            ;;
    esac

    printf '%s\n' "$whp_switch_value"
)
