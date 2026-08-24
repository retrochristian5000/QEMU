#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$SOURCE_DIR/scripts/whp-build/common.bash"
source "$SOURCE_DIR/scripts/whp-build/prepare-mold.bash"

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/whp-mold-test.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

BUILD_DIR="$tmpdir/build"
HOST_ARCH=arm64
HOST_OS=Darwin
BOOTSTRAP_MOLD=1
MOLD_TOOLS_DIR="$tmpdir/mold-tools"
LDFLAGS=
mkdir -p "$BUILD_DIR"

stderr="$tmpdir/darwin.stderr"
whp_prepare_mold 2> "$stderr"
[[ "$BOOTSTRAP_MOLD" == 0 ]]
[[ -z "${MOLD_LINKER:-}" ]]
[[ -z "$LDFLAGS" ]]
grep -Fq 'cannot link macOS Mach-O binaries' "$stderr"

HOST_ARCH=x86_64
HOST_OS=Linux
BOOTSTRAP_MOLD=0
MOLD_LINKER=stale
LDFLAGS=
whp_prepare_mold
[[ "$BOOTSTRAP_MOLD" == 0 ]]
[[ -z "$MOLD_LINKER" ]]
[[ -z "$LDFLAGS" ]]

grep -Fq '[submodule "toolchains/fast-linker"]' "$SOURCE_DIR/.gitmodules"
grep -Fq 'url = https://github.com/retrochristian5000/fast-linker.git' \
    "$SOURCE_DIR/.gitmodules"

printf 'mold bootstrap policy tests: passed\n'
