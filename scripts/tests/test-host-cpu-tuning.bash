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

whp_prepare_host_cpu_tuning >/dev/null
[[ "$QEMU_HOST_CPU_FLAGS_RESOLVED" == '-mcpu=native' ]]
CFLAGS='-O2'
CXXFLAGS='-O2'
OBJCFLAGS='-O2'
LDFLAGS='-Wl,test'
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-O2 -mcpu=native' ]]
[[ "$CXXFLAGS" == '-O2 -mcpu=native' ]]
[[ "$OBJCFLAGS" == '-O2 -mcpu=native' ]]
[[ "$LDFLAGS" == '-Wl,test' ]]
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-O2 -mcpu=native' ]]
printf 'host CPU tuning wrapper tests: passed\n'
