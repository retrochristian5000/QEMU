#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Independent host Bash seed; never build Bash using the Bash fork itself.
set -eu
marker=whp-qemu-bash-seed-adapter
if [ "${1:-}" = --whp-bash-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

# --noprofile and --norc alone do not suppress noninteractive BASH_ENV.
bash_clean()
{
    env -u BASH_ENV -u ENV -u POSIXLY_CORRECT -u SHELLOPTS -u BASHOPTS "$@"
}
bash_probe()
(
    candidate=$1
    output=$(bash_clean "$candidate" --noprofile --norc -c '
        test -n "${BASH_VERSION:-}" || exit 1
        (( BASH_VERSINFO[0] > 3 ||
           (BASH_VERSINFO[0] == 3 && BASH_VERSINFO[1] >= 2) )) || exit 1
        whp_array=(one two)
        [[ "${#whp_array[@]}" -eq 2 ]] || exit 1
        (( whp_count = 1 + 1 ))
        [[ "$whp_count" -eq 2 ]] || exit 1
        IFS= read -r whp_line < <(printf "%s\n" process-substitution)
        [[ "$whp_line" == process-substitution ]] || exit 1
        printf "%s\n" whp-bash-seed-ok
    ' 2>/dev/null) || exit 1
    [ "$output" = whp-bash-seed-ok ]
)
bash_resolve()
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
    identity=$(bash_clean "$candidate" --whp-bash-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    bash_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)
bash_select()
{
    if [ -n "${WHP_BASH_SEED:-}" ]; then
        if selected=$(bash_resolve "$WHP_BASH_SEED"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: WHP_BASH_SEED is not a usable GNU Bash: %s\n' "$WHP_BASH_SEED" >&2
        return 1
    fi
    # Retain the historical macOS independent /bin/bash root. A managed
    # Bash is promoted separately by BOOTSTRAP_BASH.
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        if selected=$(bash_resolve /bin/bash); then
            printf '%s\n' "$selected"
            return 0
        fi
    fi
    for candidate in bash /usr/bin/bash /bin/bash; do
        if selected=$(bash_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable host GNU Bash >= 3.2 for WHP bootstrap' >&2
    return 1
}
case "${1:-}" in
    --print-seed|--print-bash) bash_select ;;
    --check)
        selected=$(bash_select) || exit 1
        printf 'WHP Bash seed: %s\n' "$selected" ;;
    *)
        selected=$(bash_select) || exit 1
        exec env -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
            -u SHELLOPTS -u BASHOPTS "$selected" "$@" ;;
esac
