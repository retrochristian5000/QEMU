#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"

grep -Fq -- '-DCMAKE_INSTALL_LIBDIR=lib' "$core"

printf 'PowerPC CMake libdir policy: verified\n'
