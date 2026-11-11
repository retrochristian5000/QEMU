#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST="$ROOT/roms/openbios/tests/test-host-warning-options.bash"

if [[ ! -f "$TEST" ]]; then
    echo 'error: initialize roms/openbios before running this test' >&2
    exit 1
fi

bash "$TEST"
