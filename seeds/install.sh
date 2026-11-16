#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Root host install seed: validate the native tool without building coreutils.
# Do not confuse this executable with Automake's INSTALL_* make variables.
set -eu

marker=whp-qemu-install-seed-adapter
if [ "${1:-}" = --whp-install-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

# Compare actual POSIX file modes, not just existence or -x/-r.
# GNU and macOS/BSD ls may append ACL or extended-attribute markers.
install_mode()
(
    file=$1
    expected=$2
    listing=$(LC_ALL=C ls -ld "$file") || return 1
    permissions=${listing%% *}
    case "$permissions" in
        "$expected"|"$expected"+|"$expected"@|"$expected".) return 0 ;;
    esac
    printf 'error: install seed mode mismatch: %s (expected %s; observed %s)\n' \
        "$file" "$expected" "$permissions" >&2
    return 1
)

install_probe()
(
    candidate=$1
    probe_dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-install-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$probe_dir"' 0
    trap 'exit 1' 1 2 3 15
    printf 'whp-install-probe\n' > "$probe_dir/source" || exit 1

    # GNU and BSD/macOS install share these operations. Probe semantics rather
    # than --version banners; a command that merely exits zero is not usable.
    if ! "$candidate" -d -m 0755 "$probe_dir/prefix/bin" 2>"$probe_dir/stderr" ||
       [ ! -d "$probe_dir/prefix/bin" ] ||
       ! install_mode "$probe_dir/prefix/bin" 'drwxr-xr-x'; then
        printf 'error: install seed failed directory creation: %s\n' "$candidate" >&2
        cat "$probe_dir/stderr" >&2
        exit 1
    fi
    if ! "$candidate" -c -m 0644 "$probe_dir/source" \
        "$probe_dir/prefix/bin/data" 2>"$probe_dir/stderr" ||
       [ "$(cat "$probe_dir/prefix/bin/data" 2>/dev/null || true)" != whp-install-probe ] ||
       ! install_mode "$probe_dir/prefix/bin/data" '-rw-r--r--'; then
        printf 'error: install seed failed data copy or mode: %s\n' "$candidate" >&2
        cat "$probe_dir/stderr" >&2
        exit 1
    fi
    if ! "$candidate" -m 0755 "$probe_dir/source" \
        "$probe_dir/prefix/bin/tool" 2>"$probe_dir/stderr" ||
       [ "$(cat "$probe_dir/prefix/bin/tool" 2>/dev/null || true)" != whp-install-probe ] ||
       ! install_mode "$probe_dir/prefix/bin/tool" '-rwxr-xr-x'; then
        printf 'error: install seed failed executable copy or mode: %s\n' "$candidate" >&2
        cat "$probe_dir/stderr" >&2
        exit 1
    fi
    printf 'updated-install-probe\n' > "$probe_dir/source" || exit 1
    if ! "$candidate" -m 0644 "$probe_dir/source" \
        "$probe_dir/prefix/bin/data" 2>"$probe_dir/stderr" ||
       [ "$(cat "$probe_dir/prefix/bin/data" 2>/dev/null || true)" != updated-install-probe ] ||
       ! install_mode "$probe_dir/prefix/bin/data" '-rw-r--r--'; then
        printf 'error: install seed failed replacement: %s\n' "$candidate" >&2
        cat "$probe_dir/stderr" >&2
        exit 1
    fi
)

install_resolve()
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
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/} ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-install-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    install_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

install_select()
{
    if [ -n "${WHP_INSTALL_SEED:-}" ]; then
        if seed=$(install_resolve "$WHP_INSTALL_SEED"); then
            printf '%s\n' "$seed"
            return 0
        fi
        printf 'error: WHP_INSTALL_SEED is not a usable host install: %s\n' \
            "$WHP_INSTALL_SEED" >&2
        return 1
    fi
    # Prefer working native install; GNU Coreutils may expose ginstall.
    for candidate in /usr/bin/install /bin/install install ginstall; do
        if seed=$(install_resolve "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' 'error: no host install passed the QEMU install seed probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed) install_select; exit $? ;;
    --check)
        seed=$(install_select) || exit 1
        printf 'WHP native install seed: %s (directory, data, executable, replacement verified)\n' \
            "$seed"
        exit 0 ;;
esac

if [ "${WHP_INSTALL_LOCKED:-0}" = 1 ]; then
    [ -n "${WHP_INSTALL_SEED:-}" ] && [ -x "$WHP_INSTALL_SEED" ] || {
        printf '%s\n' 'error: locked install has no usable seed' >&2
        exit 1
    }
    case "$WHP_INSTALL_SEED" in
        */install.sh|*/scripts/whp-build/seed-bin/install)
            printf '%s\n' 'error: locked install points back to its adapter' >&2
            exit 1 ;;
    esac
    selected=$WHP_INSTALL_SEED
else
    selected=$(install_select) || exit 1
fi
case "${WHP_INSTALL_VERBOSE:-0}" in
    0) ;;
    1) printf 'WHP install invocation: executable=%s; option=%s; argument-count=%s\n' \
           "$selected" "${1:-<none>}" "$#" >&2 ;;
    *) printf 'error: WHP_INSTALL_VERBOSE must be 0 or 1\n' >&2; exit 2 ;;
esac
exec "$selected" "$@"
