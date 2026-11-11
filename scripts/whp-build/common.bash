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

whp_compiler_sibling_tool()
{
    local compiler="$1"
    local tool="$2"
    local compiler_path
    local compiler_dir
    local candidate

    [[ -n "$compiler" && -n "$tool" ]] || return 1
    case "$compiler" in
        *[[:space:]]*) return 1 ;;
    esac

    compiler_path="$(command -v "$compiler" 2>/dev/null || true)"
    [[ -n "$compiler_path" ]] || return 1
    compiler_dir="$(cd -- "$(dirname -- "$compiler_path")" && pwd -P)" || return 1
    candidate="$compiler_dir/$tool"
    [[ -x "$candidate" ]] || return 1
    printf '%s\n' "$candidate"
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

whp_normalize_boolean_variable()
{
    local variable="$1"
    local value="${!variable}"

    case "$value" in
        1|y|Y|yes|YES|Yes|true|TRUE|True|on|ON|On)
            printf -v "$variable" '%s' 1
            ;;
        0|n|N|no|NO|No|false|FALSE|False|off|OFF|Off)
            printf -v "$variable" '%s' 0
            ;;
        *)
            printf 'error: %s must be a boolean value\n' "$variable" >&2
            return 1
            ;;
    esac
}

whp_normalize_tristate_variable()
{
    local variable="$1"
    local value="${!variable}"

    case "$value" in
        auto|AUTO|Auto)
            printf -v "$variable" '%s' auto
            ;;
        1|y|Y|yes|YES|Yes|true|TRUE|True|on|ON|On)
            printf -v "$variable" '%s' 1
            ;;
        0|n|N|no|NO|No|false|FALSE|False|off|OFF|Off)
            printf -v "$variable" '%s' 0
            ;;
        *)
            printf 'error: %s must be auto or a boolean value\n' "$variable" >&2
            return 1
            ;;
    esac
}

whp_require_boolean_values()
{
    local variable

    for variable in "$@"; do
        whp_normalize_boolean_variable "$variable" || return 1
    done
}

whp_require_tristate_values()
{
    local variable

    for variable in "$@"; do
        whp_normalize_tristate_variable "$variable" || return 1
    done
}
