#!/usr/bin/env bash
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="${PYTHON:-python3}"
source "$SOURCE_DIR/scripts/whp-build/common.bash"
source "$SOURCE_DIR/scripts/whp-build/host-cpu-tuning.bash"

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/whp-cpu-wrapper.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT
fake="$tmpdir/fake-cc"
cat > "$fake" <<'COMPILER'
#!/bin/sh
exit 0
COMPILER
chmod +x "$fake"
CC="$fake"
CXX="$fake"
OBJC="$fake"
HOST_ARCH=arm64
QEMU_HOST_CPU_TUNING=native
export PYTHON CC CXX OBJC HOST_ARCH QEMU_HOST_CPU_TUNING

# Inherited CPU tuning must be removed before firmware/tool preparation. Keep
# unrelated optimization, warning, and preprocessor flags intact.
CFLAGS='-O2 -march=old -DKEEP=1'
CXXFLAGS='-mcpu old -O2 -Wall'
OBJCFLAGS='-O2 -mtune=old -Wextra'
whp_strip_inherited_host_cpu_tuning
[[ "$CFLAGS" == '-O2 -DKEEP=1' ]]
[[ "$CXXFLAGS" == '-O2 -Wall' ]]
[[ "$OBJCFLAGS" == '-O2 -Wextra' ]]

whp_prepare_host_cpu_tuning >/dev/null
[[ "$QEMU_HOST_CPU_FLAGS_RESOLVED" == '-mcpu=native' ]]
LDFLAGS='-Wl,test'
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-O2 -DKEEP=1 -mcpu=native' ]]
[[ "$CXXFLAGS" == '-O2 -Wall -mcpu=native' ]]
[[ "$OBJCFLAGS" == '-O2 -Wextra -mcpu=native' ]]
[[ "$LDFLAGS" == '-Wl,test' ]]

# Applying the QEMU-only tuning twice must not duplicate it.
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-O2 -DKEEP=1 -mcpu=native' ]]

# Portable mode must leave inherited CPU tuning removed and add no replacement.
CFLAGS='-O2 -march=native'
CXXFLAGS='-O2 -mcpu=native'
OBJCFLAGS='-O2 -mtune=native'
QEMU_HOST_CPU_TUNING=portable
export QEMU_HOST_CPU_TUNING
whp_strip_inherited_host_cpu_tuning
whp_prepare_host_cpu_tuning >/dev/null
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-O2' ]]
[[ "$CXXFLAGS" == '-O2' ]]
[[ "$OBJCFLAGS" == '-O2' ]]

printf 'host CPU tuning wrapper tests: passed\n'
