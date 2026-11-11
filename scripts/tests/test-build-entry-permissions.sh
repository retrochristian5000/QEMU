#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# build.sh is the protected public Unix build entry point. Its executable bit
# is part of the interface: ./build.sh must remain directly runnable.

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)

set -- $(git -C "$SOURCE_DIR" ls-files --stage -- build.sh)
mode=${1:-}

if [ "$mode" != 100755 ]; then
    printf 'error: build.sh must remain executable in Git (mode 100755); found %s\n' \
        "${mode:-<untracked>}" >&2
    exit 1
fi

if [ ! -x "$SOURCE_DIR/build.sh" ]; then
    printf '%s\n' \
        'error: build.sh is tracked executable but is not executable in this checkout' >&2
    exit 1
fi

printf '%s\n' 'WHP build entry permissions: verified'
