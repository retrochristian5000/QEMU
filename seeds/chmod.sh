#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select and validate a host chmod without modifying the checkout.
set -eu

marker=whp-qemu-chmod-seed-adapter
if [ "${1:-}" = --whp-chmod-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

chmod_mode()
(
    listing=$(LC_ALL=C ls -ld "$1") || exit 1
    permissions=${listing%% *}
    case "$permissions" in
        "$2"|"$2"+|"$2"@|"$2".) exit 0 ;;
    esac
    printf 'error: chmod seed mode mismatch: %s (expected %s; observed %s)\n' \
        "$1" "$2" "$permissions" >&2
    exit 1
)

chmod_probe()
(
    candidate=$1
    umask 077
    probe_dir=$(mktemp -d "${TMPDIR:-/tmp}/whp-chmod-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$probe_dir"' 0
    trap 'exit 1' 1 2 3 15
    file="$probe_dir/file with spaces"
    printf '%s\n' whp-chmod-probe > "$file" || exit 1
    "$candidate" 0640 "$file" || exit 1
    chmod_mode "$file" '-rw-r-----' || exit 1
    "$candidate" u+x "$file" || exit 1
    chmod_mode "$file" '-rwxr-----' || exit 1
    "$candidate" go-rwx "$file" || exit 1
    chmod_mode "$file" '-rwx------' || exit 1

    mkdir "$probe_dir/tree" || exit 1
    printf '%s\n' child > "$probe_dir/tree/child" || exit 1
    "$candidate" -R u=rwX,go= "$probe_dir/tree" || exit 1
    chmod_mode "$probe_dir/tree" 'drwx------' || exit 1
    chmod_mode "$probe_dir/tree/child" '-rw-------' || exit 1

    # Recursive changes must not follow a symlink outside the selected tree.
    printf '%s\n' outside > "$probe_dir/outside" || exit 1
    "$candidate" 0600 "$probe_dir/outside" || exit 1
    ln -s ../outside "$probe_dir/tree/link" || exit 1
    "$candidate" -R g+r "$probe_dir/tree" || exit 1
    chmod_mode "$probe_dir/tree/child" '-rw-r-----' || exit 1
    chmod_mode "$probe_dir/outside" '-rw-------' || exit 1

    # Do not admit a provider that reports success for missing operands.
    if "$candidate" 0600 "$probe_dir/missing" >/dev/null 2>&1; then
        exit 1
    fi
    [ "$(cat "$file")" = whp-chmod-probe ]
)

chmod_resolve()
(
    requested=$1
    [ -n "$requested" ] || exit 1
    case "$requested" in
        */*) candidate=$requested ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$requested" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/} ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-chmod-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    chmod_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

chmod_select()
{
    if [ -n "${WHP_CHMOD_SEED:-}" ]; then
        if selected=$(chmod_resolve "$WHP_CHMOD_SEED"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: WHP_CHMOD_SEED is not a usable host chmod: %s\n' \
            "$WHP_CHMOD_SEED" >&2
        return 1
    fi
    for candidate in /bin/chmod /usr/bin/chmod chmod gchmod; do
        if selected=$(chmod_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no host chmod passed the QEMU permission seed probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed) chmod_select; exit $? ;;
    --check)
        selected=$(chmod_select) || exit 1
        printf 'WHP chmod seed: %s (numeric, symbolic, recursive, symlink isolation verified)\n' \
            "$selected"
        exit 0 ;;
esac

if [ "${WHP_CHMOD_LOCKED:-0}" = 1 ]; then
    case "${WHP_CHMOD_SEED:-}" in
        ""|*/chmod.sh|*/scripts/whp-build/seed-bin/chmod)
            printf '%s\n' 'error: locked chmod has no independent seed' >&2
            exit 1 ;;
        /*) ;;
        *) printf '%s\n' 'error: locked chmod seed must be an absolute path' >&2
           exit 1 ;;
    esac
    if [ ! -f "$WHP_CHMOD_SEED" ] || [ ! -x "$WHP_CHMOD_SEED" ] ||
       [ "$WHP_CHMOD_SEED" -ef "$0" ] ||
       [ "$WHP_CHMOD_SEED" -ef "${0%/*}/../scripts/whp-build/seed-bin/chmod" ]; then
        printf '%s\n' 'error: locked chmod seed is not an independent executable' >&2
        exit 1
    fi
    selected=$WHP_CHMOD_SEED
else
    selected=$(chmod_select) || exit 1
fi
exec "$selected" "$@"
