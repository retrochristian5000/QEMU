# Shared helpers for WHP Bash build modules.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_canonical_macos_arch()
{
    case "$1" in
        arm64|aarch64) printf 'arm64\n' ;;
        x86_64|amd64) printf 'x86_64\n' ;;
        *) return 1 ;;
    esac
}

whp_append_flag()
{
    local variable="$1"
    local value="$2"
    local current="${!variable:-}"

    if [[ -n "$current" ]]; then
        printf -v "$variable" '%s %s' "$current" "$value"
    else
        printf -v "$variable" '%s' "$value"
    fi
    export "$variable"
}

whp_require_boolean_values()
{
    local variable

    for variable in "$@"; do
        case "${!variable}" in
            0|1) ;;
            *)
                printf 'error: %s must be 0 or 1\n' "$variable" >&2
                return 1
                ;;
        esac
    done
}

whp_require_tristate_values()
{
    local variable

    for variable in "$@"; do
        case "${!variable}" in
            auto|0|1) ;;
            *)
                printf 'error: %s must be auto, 0, or 1\n' "$variable" >&2
                return 1
                ;;
        esac
    done
}
