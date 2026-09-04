#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="${1:-.}"
cd "$ROOT"

status=0

if hits="$(git grep -n -E 'g_memdup[[:space:]]*\(' -- hw include/hw 2>/dev/null)"; then
    printf '%s\n' \
        'error: emulated hardware still uses deprecated g_memdup(); use g_memdup2().' >&2
    printf '%s\n' "$hits" >&2
    status=1
fi

# Darwin SDKs deprecate sprintf(); keep USB device formatting bounded so -Werror
# cannot turn a host SDK policy update into an emulated-hardware build failure.
if hits="$(git grep -n -E '(^|[^[:alnum:]_])sprintf[[:space:]]*\(' -- hw/usb 2>/dev/null)"; then
    printf '%s\n' \
        'error: emulated USB hardware may not use unbounded sprintf(); use snprintf().' >&2
    printf '%s\n' "$hits" >&2
    status=1
fi

suppression_pattern='diagnostic[[:space:]]+ignored[[:space:]]+"-Wdeprecated-declarations"|G_GNUC_BEGIN_IGNORE_DEPRECATIONS|-Wno-error=deprecated-declarations|-Wno-deprecated-declarations'
if hits="$(git grep -n -E "$suppression_pattern" -- hw include/hw 2>/dev/null | \
    grep -v '^hw/hyperv/hv-balloon-page_range_tree.c:')"; then
    printf '%s\n' \
        'error: emulated hardware may not hide deprecated-declaration diagnostics.' \
        'Use a replacement API or a compatibility wrapper instead.' >&2
    printf '%s\n' "$hits" >&2
    status=1
fi

exit "$status"
