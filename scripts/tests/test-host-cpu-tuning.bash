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

# CPU-specific flags must be removed before firmware/tool preparation. Host
# optimization and instrumentation overrides are stripped later so firmware can
# retain its own policy while QEMU leaves optimization ownership to Meson.
CFLAGS='-O0 -march=old -g -DKEEP=1 -fsanitize=address'
CXXFLAGS='-mcpu old -Og -Wall -fno-inline'
OBJCFLAGS='-Oz -mtune=old -Wextra --coverage'
whp_strip_inherited_host_cpu_tuning
[[ "$CFLAGS" == '-O0 -g -DKEEP=1 -fsanitize=address' ]]
[[ "$CXXFLAGS" == '-Og -Wall -fno-inline' ]]
[[ "$OBJCFLAGS" == '-Oz -Wextra --coverage' ]]

whp_strip_inherited_host_performance_overrides
[[ "$CFLAGS" == '-g -DKEEP=1' ]]
[[ "$CXXFLAGS" == '-Wall' ]]
[[ "$OBJCFLAGS" == '-Wextra' ]]

whp_prepare_host_cpu_tuning >/dev/null
[[ "$QEMU_HOST_CPU_FLAGS_RESOLVED" == '-mcpu=native' ]]
LDFLAGS='-Wl,test'
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-g -DKEEP=1 -mcpu=native' ]]
[[ "$CXXFLAGS" == '-Wall -mcpu=native' ]]
[[ "$OBJCFLAGS" == '-Wextra -mcpu=native' ]]
[[ "$LDFLAGS" == '-Wl,test' ]]

# Applying the QEMU-only tuning twice must not duplicate it.
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-g -DKEEP=1 -mcpu=native' ]]

# Portable mode must remove inherited performance/CPU overrides and add no
# host-specific replacement.
CFLAGS='-O3 -march=native -g'
CXXFLAGS='-Os -mcpu=native -Wall'
OBJCFLAGS='-O0 -mtune=native -Wextra'
QEMU_HOST_CPU_TUNING=portable
export QEMU_HOST_CPU_TUNING
whp_strip_inherited_host_cpu_tuning
whp_strip_inherited_host_performance_overrides
whp_prepare_host_cpu_tuning >/dev/null
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-g' ]]
[[ "$CXXFLAGS" == '-Wall' ]]
[[ "$OBJCFLAGS" == '-Wextra' ]]

printf 'host CPU tuning wrapper tests: passed\n'
