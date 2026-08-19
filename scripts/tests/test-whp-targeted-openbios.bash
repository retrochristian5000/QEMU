#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BUILD_SYSTEM_DIR="$SOURCE_DIR/scripts/whp-build"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

cat > "$work_dir/fake-ninja" <<'RUNNER'
#!/bin/sh
printf '%s\n' "$@" > "$WHP_TEST_RUNNER_ARGS"
RUNNER
chmod +x "$work_dir/fake-ninja"

source "$BUILD_SYSTEM_DIR/build-targets.bash"

export WHP_TEST_RUNNER_ARGS="$work_dir/runner-args"
BUILD_DIR="$work_dir/build"
mkdir -p "$BUILD_DIR"
JOBS=1
NINJA_CMD="$work_dir/fake-ninja"
MAKE_CMD=
INSTALL=0
BUILD_TARGETS=all
BUILD_OPENBIOS=1

whp_build_targets qemu-system-ppc

grep -Fxq qemu-system-ppc "$WHP_TEST_RUNNER_ARGS"
grep -Fxq whp-openbios-ppc "$WHP_TEST_RUNNER_ARGS"

printf 'WHP targeted PowerPC firmware companion: verified\n'
