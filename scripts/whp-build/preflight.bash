#!/usr/bin/env bash

# Lightweight integrity checks for the WHP build wrapper itself. This file is
# sourced by builder.sh before the larger stage implementation is loaded.

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: scripts/whp-build/preflight.bash requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi
: "${SOURCE_DIR:?builder.sh must define SOURCE_DIR before build preflight}"

whp_validate_build_scripts()
{
    local bash_runner="${WHP_BUILD_BASH:-${BASH:-bash}}"
    local posix_runner
    local script
    local checked=0
    local checked_scripts=()
    local posix_scripts=(
        "$SOURCE_DIR/build.sh"
        "$SOURCE_DIR/scripts/macos-builder.sh"
    )
    local bash_scripts=(
        "$SOURCE_DIR/builder.sh"
        "$SOURCE_DIR/scripts/macos-builder.bash"
        "$SOURCE_DIR/scripts/macos-build-hygiene.bash"
        "$SOURCE_DIR/scripts/macos-compiler-policy.bash"
        "$SOURCE_DIR/scripts/macos-gtk-environment.bash"
        "$SOURCE_DIR/scripts/verify-macos-gtk.sh"
        "$SOURCE_DIR/scripts/verify-macos-toolchain.sh"
        "$SOURCE_DIR/scripts/verify-macos-lto.sh"
        "$SOURCE_DIR/scripts/whp-build/stages.bash"
        "$SOURCE_DIR/scripts/whp-build/prepare-build.bash"
        "$SOURCE_DIR/scripts/whp-build/prepare-sources.bash"
        "$SOURCE_DIR/scripts/whp-build/configure.bash"
        "$SOURCE_DIR/scripts/whp-build/build-targets.bash"
        "$SOURCE_DIR/scripts/whp-build/configure-openbios.bash"
        "$SOURCE_DIR/scripts/whp-build/preflight.bash"
        "$SOURCE_DIR/scripts/whp-build/post-build.bash"
        "$SOURCE_DIR/scripts/meson-build-openbios.sh"
        "$SOURCE_DIR/scripts/build-openbios.sh"
    )

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

    for script in "${posix_scripts[@]}"; do
        if [[ ! -f "$script" ]]; then
            printf 'error: required build script is missing: %s\n' "$script" >&2
            return 1
        fi
        "$posix_runner" -n "$script"
        checked_scripts+=("$script")
        checked=$((checked + 1))
    done
    for script in "${bash_scripts[@]}"; do
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
