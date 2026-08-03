#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"

# Keep this file as one readable run of the build system.  Policy, validation,
# configuration, and execution live behind the stage interface below.
source "$BUILD_SYSTEM_DIR/stages.bash"

whp_prepare_build
bash "$SOURCE_DIR/scripts/verify-macos-gtk.sh"
whp_prepare_sources
whp_configure_build
whp_build_targets "$@"
