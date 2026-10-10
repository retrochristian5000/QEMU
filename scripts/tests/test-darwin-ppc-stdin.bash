#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Standalone Darwin PPC stdin ABI contract; no Darwin runtime is assumed.
set -euo pipefail

root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

cc="${CC:-cc}"
"$cc" -std=c11 -Wall -Wextra -Werror -pedantic \
    -I"$root" \
    "$root/darwin-user/ppc/stdio.c" \
    "$root/tests/unit/test-darwin-ppc-stdin.c" \
    -o "$tmp/test-darwin-ppc-stdin"
"$tmp/test-darwin-ppc-stdin"
echo "Darwin PowerPC stdin ABI boundary: verified"
