#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"

# builder.sh is the normalized stage runner, not a second public entry point.
# Redirect accidental direct invocations through build.sh so macOS SDK,
# Homebrew, shell, and architecture policy cannot be bypassed.
if [[ "${WHP_BUILD_ENTRY_NORMALIZED:-0}" != 1 ]]; then
    exec "$SOURCE_DIR/build.sh" "$@"
fi

# Keep this file as one readable run of the build system.  Policy, validation,
# configuration, and execution live behind the stage interface below.
source "$BUILD_SYSTEM_DIR/stages.bash"

whp_prepare_build
source "$SOURCE_DIR/scripts/macos-gtk-environment.bash"
bash "$SOURCE_DIR/scripts/verify-macos-gtk.sh"
whp_prepare_sources
whp_configure_build
whp_build_targets "$@"
BUILD_DIR="$BUILD_DIR" \
QEMU_TARGET_LIST="$QEMU_TARGET_LIST" \
BUILD_TARGETS="$BUILD_TARGETS" \
    bash "$SOURCE_DIR/scripts/verify-qemu-machine-profiles.sh" "$@"
