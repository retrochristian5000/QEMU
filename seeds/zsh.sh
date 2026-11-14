#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native Zsh seed for explicit Zsh build scripts and portability tests.
# Do not promote Zsh to CONFIG_SHELL or reinterpret POSIX .sh / Bash .bash files.
set -eu

marker=whp-qemu-zsh-seed-adapter
if [ "${1:-}" = --whp-zsh-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

# -f skips user startup files; /etc/zshenv may still be executed by Zsh.
# Avoid caller-supplied startup directories and sh ENV hooks in either phase.
zsh_clean()
{
    env -u ZDOTDIR -u ENV "$@"
}

zsh_probe()
(
    candidate=$1
    output=$(zsh_clean "$candidate" -f -c '
        [[ -n "${ZSH_VERSION:-}" ]] || exit 1
        emulate -R zsh || exit 1
        whp_array=(one two)
        [[ "${whp_array[1]}" == one && "${whp_array[2]}" == two ]] || exit 1
        print -r -- whp-zsh-seed-ok
    ' 2>/dev/null) || exit 1
    [ "$output" = whp-zsh-seed-ok ]
)

zsh_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
             candidate=$directory/${candidate##*/} ;;
        *) exit 1 ;;
    esac
    identity=$(zsh_clean "$candidate" --whp-zsh-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    zsh_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

zsh_select()
{
    if [ -n "${WHP_ZSH_SEED:-}" ]; then
        if selected=$(zsh_resolve "$WHP_ZSH_SEED"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: WHP_ZSH_SEED is not a usable native Zsh: %s\n' \
            "$WHP_ZSH_SEED" >&2
        return 1
    fi
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        if selected=$(zsh_resolve /bin/zsh); then
            printf '%s\n' "$selected"
            return 0
        fi
    fi
    for candidate in zsh /usr/bin/zsh /bin/zsh; do
        if selected=$(zsh_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable native Zsh is available for the optional WHP seed' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-zsh) zsh_select ;;
    --check)
        selected=$(zsh_select) || exit 1
        printf 'WHP Zsh seed: %s\n' "$selected" ;;
    *)
        selected=$(zsh_select) || exit 1
        exec env -u ZDOTDIR -u ENV "$selected" -f "$@" ;;
esac
