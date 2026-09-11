#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/whp-build/openbios-build-cache.bash"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/openbios"
mkdir -p "$repo"
git -C "$repo" init -q
git -C "$repo" config user.email test@example.invalid
git -C "$repo" config user.name test
printf 'one\n' > "$repo/tracked.txt"
git -C "$repo" add tracked.txt
git -C "$repo" commit -qm initial

sig1="$(whp_openbios_source_signature "$repo")"
printf 'two\n' > "$repo/tracked.txt"
sig2="$(whp_openbios_source_signature "$repo")"
[[ "$sig1" != "$sig2" ]] || {
    printf 'error: tracked OpenBIOS edit did not invalidate signature\n' >&2
    exit 1
}
git -C "$repo" checkout -q -- tracked.txt
printf 'extra\n' > "$repo/untracked.txt"
sig3="$(whp_openbios_source_signature "$repo")"
[[ "$sig1" != "$sig3" ]] || {
    printf 'error: untracked OpenBIOS edit did not invalidate signature\n' >&2
    exit 1
}

output="$tmp/openbios-ppc"
state="$tmp/state"
printf 'rom\n' > "$output"
whp_openbios_cache_write "$state" "$output" "$sig1"
whp_openbios_cache_is_fresh "$state" "$output" "$sig1" 0

printf 'corrupt\n' > "$output"
if whp_openbios_cache_is_fresh "$state" "$output" "$sig1" 0; then
    printf 'error: modified OpenBIOS output incorrectly reported a cache hit\n' >&2
    exit 1
fi
printf 'rom\n' > "$output"
whp_openbios_cache_write "$state" "$output" "$sig1"

if whp_openbios_cache_is_fresh "$state" "$output" "$sig1" 1; then
    printf 'error: forced OpenBIOS rebuild incorrectly reported a cache hit\n' >&2
    exit 1
fi
if whp_openbios_cache_is_fresh "$state" "$output" "$sig2" 0; then
    printf 'error: changed OpenBIOS signature incorrectly reported a cache hit\n' >&2
    exit 1
fi
rm -f "$output"
if whp_openbios_cache_is_fresh "$state" "$output" "$sig1" 0; then
    printf 'error: missing OpenBIOS output incorrectly reported a cache hit\n' >&2
    exit 1
fi

printf 'OpenBIOS incremental cache guards: verified\n'
