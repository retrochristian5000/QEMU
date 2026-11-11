#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

for patch_file in "$ROOT"/subprojects/packagefiles/slirp/*.patch; do
    if ! git apply --numstat -- "$patch_file" >/dev/null; then
        printf 'error: malformed unified diff: %s\n' "$patch_file" >&2
        exit 1
    fi
done

printf 'Slirp patch syntax: verified\n'
