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

printf '%s\n' 'WHP shared shell functions: verified'
