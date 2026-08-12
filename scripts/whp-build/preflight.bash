#!/usr/bin/env bash

# Lightweight integrity checks for the WHP build wrapper itself. This file is
# sourced by builder.sh before the larger stage implementation is loaded.

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: scripts/whp-build/preflight.bash requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi
: "${SOURCE_DIR:?builder.sh must define SOURCE_DIR before build preflight}"

source "$SOURCE_DIR/scripts/whp-build/shell-inventory.bash"

whp_validate_build_scripts()
{
    local bash_runner="${WHP_BUILD_BASH:-${BASH:-bash}}"
    local posix_runner
    local script
    local checked=0
    local checked_scripts=()

    posix_runner="$(command -v sh 2>/dev/null || true)"
    if [[ -z "$posix_runner" ]]; then
        printf 'error: sh is required to validate POSIX build entry points\n' >&2
        return 1
    fi
    if [[ ! -x "$bash_runner" ]]; then
        printf 'error: build preflight cannot execute Bash: %s\n' \
            "$bash_runner" >&2
        return 1
    fi

    for script in "${WHP_POSIX_BUILD_SCRIPTS[@]}"; do
        if [[ ! -f "$script" ]]; then
            printf 'error: required build script is missing: %s\n' "$script" >&2
            return 1
        fi
        "$posix_runner" -n "$script"
        checked_scripts+=("$script")
        checked=$((checked + 1))
    done

    for script in "${WHP_BASH_BUILD_SCRIPTS[@]}"; do
        if [[ ! -f "$script" ]]; then
            printf 'error: required build script is missing: %s\n' "$script" >&2
            return 1
        fi
        "$bash_runner" --noprofile --norc -n "$script"
        checked_scripts+=("$script")
        checked=$((checked + 1))
    done

    case "${WHP_RUN_SHELLCHECK:-0}" in
        0) ;;
        1)
            if ! command -v shellcheck >/dev/null 2>&1; then
                printf 'error: WHP_RUN_SHELLCHECK=1 but shellcheck is unavailable\n' >&2
                return 1
            fi
            shellcheck "${checked_scripts[@]}"
            ;;
        *)
            printf 'error: WHP_RUN_SHELLCHECK must be 0 or 1\n' >&2
            return 1
            ;;
    esac

    printf 'WHP build wrapper syntax: verified (%d scripts)\n' "$checked"
}
