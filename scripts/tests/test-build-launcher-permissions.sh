#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Check both committed permissions and the actual checkout.
set -eu

root=$(CDPATH='' cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

entry=$(git ls-tree HEAD -- build.sh)
mode=${entry%% *}
if [ "$mode" != 100755 ]; then
    printf 'error: build.sh Git mode is %s; expected 100755\n' "${mode:-missing}" >&2
    exit 1
fi

if [ ! -f build.sh ] || [ -L build.sh ] || [ ! -x build.sh ]; then
    printf '%s\n' 'error: build.sh must be an executable regular file' >&2
    exit 1
fi

printf '%s\n' 'build.sh: committed and checkout executable permissions verified'
