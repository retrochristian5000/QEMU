#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
. "$SOURCE_DIR/scripts/whp-build/shell-functions.sh"

check_switch()
{
    expected=$1
    value=$2
    actual=$(whp_normalize_auto_switch TEST_SWITCH "$value")
    if [ "$actual" != "$expected" ]; then
        printf 'error: switch %s normalized to %s, expected %s\n' \
            "$value" "$actual" "$expected" >&2
        exit 1
    fi
}

check_switch auto auto
check_switch 0 0
check_switch 1 1
check_switch 1 y
check_switch 0 n

if whp_normalize_auto_switch TEST_SWITCH invalid >/dev/null 2>&1; then
    printf '%s\n' 'error: invalid auto switch was accepted' >&2
    exit 1
fi


check_strict()
{
    function_name=$1
    expected=$2
    value=$3
    actual=$("$function_name" TEST_SWITCH "$value")
    if [ "$actual" != "$expected" ]; then
        printf 'error: %s %s returned %s, expected %s\n' \
            "$function_name" "$value" "$actual" "$expected" >&2
        exit 1
    fi
}

check_strict whp_require_auto_switch auto auto
check_strict whp_require_auto_switch 0 0
check_strict whp_require_auto_switch 1 1
if whp_require_auto_switch TEST_SWITCH y >/dev/null 2>&1; then
    printf '%s\n' 'error: strict auto switch accepted y alias' >&2
    exit 1
fi

check_strict whp_require_binary_switch 0 0
check_strict whp_require_binary_switch 1 1
if whp_require_binary_switch TEST_SWITCH auto >/dev/null 2>&1; then
    printf '%s\n' 'error: binary switch accepted auto' >&2
    exit 1
fi

# Identity checks must accept the same path even on older shells, and
# accept genuine aliases only when -ef or a native identity shim proves equality.
if ! whp_same_directory "$SOURCE_DIR" "$SOURCE_DIR"; then
    printf '%s\n' 'error: identical directories were rejected' >&2
    exit 1
fi
whp_parent_dir=${SOURCE_DIR%/*}
if whp_same_directory "$SOURCE_DIR" "$whp_parent_dir"; then
    printf '%s\n' 'error: distinct directories were accepted' >&2
    exit 1
else
    whp_status=$?
    case "$whp_status" in
        1|2) ;;
        *) printf 'error: unexpected directory identity status %s\n' "$whp_status" >&2; exit 1 ;;
    esac
fi
if [ "$whp_status" -eq 1 ]; then
    # A symlinked spelling should resolve to the same underlying inode.
    whp_probe_dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-ef-probe.XXXXXX") || exit 1
    trap 'rm -rf "$whp_probe_dir"' 0
    mkdir "$whp_probe_dir/original"
    ln -s original "$whp_probe_dir/alias"
    if ! whp_same_directory "$whp_probe_dir/original" "$whp_probe_dir/alias"; then
        printf '%s\n' 'error: shell -ef rejected a directory symlink alias' >&2
        exit 1
    fi
fi

# macOS native BSD stat is independently tested even when the running
# /bin/sh implements -ef; BSD stat needs -L to follow directory symlinks.
if [ "$(uname -s 2>/dev/null || :)" = Darwin ]; then
    whp_stat_probe=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-darwin-stat.XXXXXX") || exit 1
    trap 'rm -rf "${whp_probe_dir:-}" "$whp_stat_probe"' 0
    mkdir "$whp_stat_probe/original" "$whp_stat_probe/other"
    ln -s original "$whp_stat_probe/alias path"
    whp_id_original=$(whp_darwin_directory_identity "$whp_stat_probe/original") || exit 1
    whp_id_alias=$(whp_darwin_directory_identity "$whp_stat_probe/alias path") || exit 1
    whp_id_other=$(whp_darwin_directory_identity "$whp_stat_probe/other") || exit 1
    if [ "$whp_id_original" != "$whp_id_alias" ] ||
       [ "$whp_id_original" = "$whp_id_other" ]; then
        printf '%s\n' 'error: Darwin stat failed directory identity or symlink following' >&2
        exit 1
    fi
    if whp_darwin_directory_identity "$whp_stat_probe/missing" >/dev/null 2>&1; then
        printf '%s\n' 'error: missing directory acquired a stat identity' >&2
        exit 1
    fi
fi

printf '%s\n' 'WHP shared shell functions: verified'
