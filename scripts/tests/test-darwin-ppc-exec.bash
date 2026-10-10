#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
cc="${CC:-cc}"
"$cc" -std=c11 -Wall -Wextra -Werror -pedantic -I"$root" \
  "$root/tests/unit/test-darwin-ppc-exec.c" \
  "$root/darwin-user/macho_probe.c" \
  "$root/darwin-user/macho_exec.c" \
  -o "$tmp/test-darwin-ppc-exec"
"$tmp/test-darwin-ppc-exec"
printf 'Darwin PPC32/PPC64 Mach-O executable image plan: verified\n'
