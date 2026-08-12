#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

# build.sh owns shell selection, validation, incremental defaults, and startup
# environment normalization.  Keep this compatibility entry point thin so the
# same policy cannot drift into a second implementation.
if [ "${WHP_BUILD_ENTRY_NORMALIZED:-0}" != 1 ]; then
    exec "$SOURCE_DIR/build.sh" "$@"
fi

: "${WHP_BUILD_BASH:?WHP_BUILD_BASH is required}"
: "${CONFIG_SHELL:?CONFIG_SHELL is required}"

CLEAN_ENV=$(command -v env 2>/dev/null || true)
if [ -z "$CLEAN_ENV" ]; then
    printf 'error: env is required to normalize the macOS build environment\n' >&2
    exit 1
fi

exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
    -u SHELLOPTS -u BASHOPTS \
    WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
    WHP_BUILD_ENTRY_NORMALIZED=1 \
    "$WHP_BUILD_BASH" --noprofile --norc \
    "$SCRIPT_DIR/macos-builder.bash" "$@"
