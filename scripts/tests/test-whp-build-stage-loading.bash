#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"

source "$BUILD_SYSTEM_DIR/stages.bash"

for stage_function in \
    whp_prepare_build \
    whp_prepare_sources \
    whp_configure_build \
    whp_build_targets; do
    if ! declare -F "$stage_function" >/dev/null; then
        printf 'error: build stage function was not loaded: %s\n' \
            "$stage_function" >&2
        exit 1
    fi
done

for module in \
    "$BUILD_SYSTEM_DIR/stages.bash" \
    "$BUILD_SYSTEM_DIR/prepare-build.bash" \
    "$BUILD_SYSTEM_DIR/prepare-sources.bash" \
    "$BUILD_SYSTEM_DIR/configure.bash" \
    "$BUILD_SYSTEM_DIR/build-targets.bash"; do
    if [[ -e "$module" && -x "$module" ]]; then
        printf 'error: sourced build module must not be executable: %s\n' \
            "$module" >&2
        exit 1
    fi
done

printf 'WHP build stage loading: verified\n'
