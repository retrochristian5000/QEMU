#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"
BUILDER="$SOURCE_DIR/builder.sh"

for module in \
    common.bash \
    prepare-build.bash \
    prepare-sources.bash \
    prepare-seabios-grub.bash \
    prepare-mold.bash \
    host-cpu-tuning.bash \
    configure.bash \
    build-targets.bash; do
    source_line="source \"\$BUILD_SYSTEM_DIR/$module\""
    if ! grep -Fqx "$source_line" "$BUILDER"; then
        printf 'error: builder.sh does not directly load build module: %s\n' \
            "$module" >&2
        exit 1
    fi

done

for module in \
    "$BUILD_SYSTEM_DIR/common.bash" \
    "$BUILD_SYSTEM_DIR/prepare-build.bash" \
    "$BUILD_SYSTEM_DIR/prepare-sources.bash" \
    "$BUILD_SYSTEM_DIR/prepare-seabios-grub.bash" \
    "$BUILD_SYSTEM_DIR/prepare-mold.bash" \
    "$BUILD_SYSTEM_DIR/host-cpu-tuning.bash" \
    "$BUILD_SYSTEM_DIR/configure.bash" \
    "$BUILD_SYSTEM_DIR/build-targets.bash"; do
    if [[ -e "$module" && -x "$module" ]]; then
        printf 'error: sourced build module must not be executable: %s\n' \
            "$module" >&2
        exit 1
    fi
done

printf 'WHP single build orchestration: verified\n'
