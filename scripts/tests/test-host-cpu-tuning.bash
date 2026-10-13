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
probe=0
native=0
if [ -n "${WHP_FAKE_COMPILER_LOG:-}" ]; then
    printf '%s\n' "$*" >> "$WHP_FAKE_COMPILER_LOG"
fi
for arg in "$@"; do
    case "$arg" in
        -###) probe=1 ;;
        -mcpu=native) native=1 ;;
    esac
done
if [ "$probe" = 1 ] && [ "$native" = 1 ]; then
    printf '"-cc1" "-target-cpu" "apple-m4"\n' >&2
fi
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
[[ "$QEMU_HOST_CPU_FLAGS_RESOLVED" == '-mtune=apple-m4' ]]
[[ "$QEMU_HOST_NATIVE_CPU" == 'apple-m4' ]]
LDFLAGS='-Wl,test'
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-g -DKEEP=1 -mtune=apple-m4' ]]
[[ "$CXXFLAGS" == '-Wall -mtune=apple-m4' ]]
[[ "$OBJCFLAGS" == '-Wextra -mtune=apple-m4' ]]
[[ "$LDFLAGS" == '-Wl,test' ]]

# Applying the QEMU-only tuning twice must not duplicate it.
whp_apply_host_cpu_tuning
[[ "$CFLAGS" == '-g -DKEEP=1 -mtune=apple-m4' ]]

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
[[ -z "$QEMU_HOST_NATIVE_CPU" ]]

# Darwin must forward its ABI, SDK and deployment flags into the Python
# C, C++ and Objective-C tuning probes (not just the eventual CXXFLAGS).
HOST_OS=Darwin
WHP_MACOS_ARCH=arm64e
SDKROOT=/fake/MacOSX.sdk
MACOSX_DEPLOYMENT_TARGET=15.0
WHP_FAKE_COMPILER_LOG="$tmpdir/darwin-probes.log"
QEMU_HOST_CPU_TUNING=native
export HOST_OS WHP_MACOS_ARCH SDKROOT MACOSX_DEPLOYMENT_TARGET \
       WHP_FAKE_COMPILER_LOG QEMU_HOST_CPU_TUNING
whp_prepare_host_cpu_tuning >/dev/null
[[ "$QEMU_HOST_CPU_FLAGS_RESOLVED" == '-mtune=apple-m4' ]]
grep -Fq -- '-arch arm64e -isysroot /fake/MacOSX.sdk -mmacosx-version-min=15.0' \
    "$WHP_FAKE_COMPILER_LOG"

printf 'host CPU tuning wrapper tests: passed\n'
