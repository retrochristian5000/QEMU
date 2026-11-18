#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Validate a native ln executable for QEMU's symlink and hardlink operations.
# Do not overwrite Autoconf/Libtool LN_S, which may contain a command string.
set -eu

marker=whp-qemu-ln-seed-adapter
if [ "${1:-}" = --whp-ln-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

ln_probe()
(
    candidate=$1
    probe_dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ln-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$probe_dir"' 0
    trap 'exit 1' 1 2 3 15

    printf 'original\n' > "$probe_dir/target file" || exit 1
    "$candidate" -s 'target file' "$probe_dir/symbolic link" || exit 1
    [ -L "$probe_dir/symbolic link" ] || exit 1
    [ "$(readlink "$probe_dir/symbolic link")" = 'target file' ] || exit 1
    [ "$(cat "$probe_dir/symbolic link")" = original ] || exit 1

    # A dangling relative symlink is valid; the target need not yet exist.
    "$candidate" -s missing "$probe_dir/dangling link" || exit 1
    [ -L "$probe_dir/dangling link" ] || exit 1
    [ ! -e "$probe_dir/dangling link" ] || exit 1

    # Ensure -f replaces a regular file rather than nesting another entry.
    printf 'previous\n' > "$probe_dir/replacement" || exit 1
    "$candidate" -sf 'target file' "$probe_dir/replacement" || exit 1
    [ -L "$probe_dir/replacement" ] || exit 1
    [ "$(readlink "$probe_dir/replacement")" = 'target file' ] || exit 1

    # Without -s, the new name must reference the same inode, not a copy.
    "$candidate" "$probe_dir/target file" "$probe_dir/hard link" || exit 1
    [ -f "$probe_dir/hard link" ] && [ ! -L "$probe_dir/hard link" ] || exit 1
    printf 'updated\n' > "$probe_dir/hard link" || exit 1
    [ "$(cat "$probe_dir/target file")" = updated ] || exit 1
    rm "$probe_dir/target file" || exit 1
    [ "$(cat "$probe_dir/hard link")" = updated ] || exit 1
)

ln_resolve()
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
    identity=$("$candidate" --whp-ln-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    ln_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

ln_select()
{
    if [ -n "${WHP_LN_SEED:-}" ]; then
        if selected=$(ln_resolve "$WHP_LN_SEED"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: WHP_LN_SEED is not a usable host ln: %s\n' "$WHP_LN_SEED" >&2
        return 1
    fi
    # macOS/BSD and GNU Coreutils are both acceptable; no GNU-only flags.
    for candidate in /bin/ln /usr/bin/ln ln gln; do
        if selected=$(ln_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no host ln passed the QEMU link seed probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed) ln_select; exit $? ;;
    --check)
        selected=$(ln_select) || exit 1
        printf 'WHP ln seed: %s (symlink, dangling link, -sf, hardlink verified)\n' \
            "$selected"
        exit 0 ;;
esac

# Build.sh validates once and locks the literal-command bridge. Do not rerun
# the filesystem probe on each symlink creation during toolchain bootstrap.
if [ "${WHP_LN_LOCKED:-0}" = 1 ]; then
    [ -n "${WHP_LN_SEED:-}" ] && [ -x "$WHP_LN_SEED" ] || {
        printf '%s\n' 'error: locked ln has no usable seed' >&2
        exit 1
    }
    case "$WHP_LN_SEED" in
        */ln.sh|*/scripts/whp-build/seed-bin/ln)
            printf '%s\n' 'error: locked ln points back to its seed adapter' >&2
            exit 1 ;;
    esac
    exec "$WHP_LN_SEED" "$@"
fi
selected=$(ln_select) || exit 1
exec "$selected" "$@"
