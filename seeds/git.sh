#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Seed Git adapter for the WHP QEMU bootstrap graph.
#
# Git cannot bootstrap the checkout that contains its own pinned source.
# An already usable host Git is therefore an explicit root capability.

set -eu

WHP_GIT_ADAPTER_MARKER=whp-qemu-git-seed-adapter

if [ "${1:-}" = --whp-git-adapter-probe ]; then
    printf '%s\n' "$WHP_GIT_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-git-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_GIT_ADAPTER_MARKER" ]
}

resolve_candidate()
{
    value=$1
    [ -n "$value" ] || return 1
    case "$value" in
        *[[:space:]]*) return 1 ;;
    esac
    if [ -x "$value" ]; then
        candidate=$value
    else
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    is_self "$candidate" && return 1
    # The early parent updater runs before the grep seed is selected. Parse
    # the Git banner with the POSIX shell, without rediscovering host grep.
    git_version=$("$candidate" --version 2>/dev/null) || return 1
    case "$git_version" in
        'git version '*) ;;
        *) return 1 ;;
    esac
    printf '%s\n' "$candidate"
}

select_seed()
{
    if [ -n "${WHP_GIT_SEED:-}" ]; then
        resolve_candidate "$WHP_GIT_SEED" ||
            {
                printf 'error: WHP_GIT_SEED is not a usable Git: %s\n' \
                    "$WHP_GIT_SEED" >&2
                return 1
            }
        return 0
    fi

    # Honor a non-Apple Git explicitly selected through PATH. A default
    # /usr/bin/git at the front of macOS PATH must not hide Homebrew Git.
    host_kernel=${WHP_HOST_KERNEL:-}
    if [ -z "$host_kernel" ]; then
        host_kernel=$(uname -s 2>/dev/null || printf unknown)
    fi
    if [ "$host_kernel" = Darwin ]; then
        path_git=$(command -v git 2>/dev/null || true)
        case "$path_git" in
            /usr/bin/git|/bin/git|'') ;;
            *)
                if seed=$(resolve_candidate "$path_git"); then
                    printf '%s\n' "$seed"
                    return 0
                fi
                ;;
        esac

        # No dependency on the brew command: linked and keg-only Git
        # installations work in the standard Apple Silicon/Intel prefixes.
        # A custom prefix can be supplied by Homebrew's shell environment.
        if [ -n "${HOMEBREW_PREFIX:-}" ]; then
            for candidate in "$HOMEBREW_PREFIX/bin/git" "$HOMEBREW_PREFIX/opt/git/bin/git"; do
                if seed=$(resolve_candidate "$candidate"); then
                    printf '%s\n' "$seed"
                    return 0
                fi
            done
        fi
        for candidate in /opt/homebrew/bin/git /usr/local/bin/git \
                         /opt/homebrew/opt/git/bin/git /usr/local/opt/git/bin/git; do
            if seed=$(resolve_candidate "$candidate"); then
                printf '%s\n' "$seed"
                return 0
            fi
        done
    fi

    # On non-Darwin hosts, follow PATH first. Apple's Git remains the final
    # Darwin fallback, after any available Homebrew installation.
    for candidate in git /usr/bin/git; do
        if seed=$(resolve_candidate "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' \
        'error: no usable host Git is available for the QEMU bootstrap seed' >&2
    return 1
}

seed=$(select_seed)

case "${1:-}" in
    --print-seed)
        printf '%s\n' "$seed"
        exit 0
        ;;
    --check)
        printf 'WHP Git seed: %s\n' "$seed"
        exit 0
        ;;
esac

exec "$seed" "$@"
