#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"

# builder.sh is the normalized stage runner, not a second public entry point.
# Redirect accidental direct invocations through build.sh so host policy cannot
# be bypassed.
if [[ "${WHP_BUILD_ENTRY_NORMALIZED:-0}" != 1 ]]; then
    exec "$SOURCE_DIR/build.sh" "$@"
fi

# Exhaustive cross-platform syntax validation belongs in CI. Making every
# runtime build parse every macOS/firmware helper would let an irrelevant
# optional path reject an otherwise viable QEMU host. Keep the old validation
# available as an explicit diagnostic switch.
case "${WHP_RUNTIME_PREFLIGHT:-0}" in
    0) ;;
    1)
        source "$BUILD_SYSTEM_DIR/preflight.bash"
        whp_validate_build_scripts
        ;;
    *)
        printf 'error: WHP_RUNTIME_PREFLIGHT must be 0 or 1\n' >&2
        exit 1
        ;;
esac

source "$BUILD_SYSTEM_DIR/stages.bash"

# Preparation must see the requested build outputs.  A command such as
# `./build.sh qemu-system-ppc` is a run-specific request and must be able to
# expand an existing incremental build even when the saved PPC toggle is off.
whp_prepare_build "$@"
if [[ "$HOST_OS" == Darwin && "$MACOS_ENABLE_GTK" == 1 ]]; then
    source "$SOURCE_DIR/scripts/macos-gtk-environment.bash"
    "$WHP_BUILD_BASH" --noprofile --norc \
        "$SOURCE_DIR/scripts/verify-macos-gtk.sh"
fi
whp_prepare_sources
whp_configure_build
whp_build_targets "$@"

source "$BUILD_SYSTEM_DIR/post-build.bash"
whp_verify_build_outputs "$@"
