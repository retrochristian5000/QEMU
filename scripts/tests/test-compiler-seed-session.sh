#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Validate the native C admission session without a full QEMU build.
set -eu
root=$(CDPATH= cd -P -- "$(dirname -- "$0")/../.." && pwd -P)
. "$root/scripts/whp-build/compiler-seed-session.sh"

scratch=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-cc-session.XXXXXX")
trap 'rm -rf -- "$scratch"' 0
trap 'exit 1' HUP INT TERM
scratch=$(CDPATH= cd -P -- "$scratch" && pwd -P)

# Use a deterministic executable fixture to exercise the identity guard.
printf '#!/bin/sh\nexit 0\n' > "$scratch/cc"
chmod 700 "$scratch/cc"
CC_FOR_BUILD="$scratch/cc"
WHP_CC_SEED=$CC_FOR_BUILD
PATH=/usr/bin:/bin
export CC_FOR_BUILD WHP_CC_SEED PATH
whp_cc_session_begin

if [ -z "${WHP_CC_SESSION_PATH:-}" ]; then
    printf '%s\n' 'SKIP: no supported stat for compiler session'
    exit 77
fi

[ "$(whp_cc_session_lookup)" = "$CC_FOR_BUILD" ]
# A child shell must receive exactly the same admission.
[ "$(/bin/sh -c '. "$1"; whp_cc_session_lookup' sh \
    "$root/scripts/whp-build/compiler-seed-session.sh")" = "$CC_FOR_BUILD" ]

reject()
{
    if whp_cc_session_lookup >/dev/null 2>&1; then
        printf 'error: reused native compiler after %s changed\n' "$1" >&2
        exit 1
    fi
}

(WHP_CC_SEED="$scratch/other"; reject 'explicit seed')
(CC_FOR_BUILD="$scratch/other"; reject 'native C compiler')
(SDKROOT="$scratch/other-sdk"; reject 'SDK')
(DEVELOPER_DIR="$scratch/other-developer"; reject 'developer root')
(PATH=/bin:/usr/bin; reject 'PATH order')
(PATH=.:/usr/bin:/bin; reject 'relative PATH')
(PATH=:/usr/bin:/bin; reject 'empty PATH element')
(PATH=/usr/bin:/bin:; reject 'trailing empty PATH element')
(HOME="$scratch/other-home"; reject 'HOME')
(WHP_CLANG_SEED="$scratch/other-clang"; reject 'Clang selection')
(whp_cc_session_clear; reject 'cleared session')

# Replacing the executable in place invalidates the admission even if its
# pathname stays unchanged. Use an atomic replacement with a new inode.
printf '#!/bin/sh\nexit 1\n' > "$scratch/replacement"
chmod 700 "$scratch/replacement"
mv "$scratch/replacement" "$CC_FOR_BUILD"
reject 'compiler identity'
whp_cc_session_begin
[ "$(whp_cc_session_lookup)" = "$CC_FOR_BUILD" ]
chmod 600 "$CC_FOR_BUILD"
reject 'compiler executability'
printf '%s\n' 'Native C session identity and environment checks passed'
