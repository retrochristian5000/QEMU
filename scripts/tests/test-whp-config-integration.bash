#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Exercise the public build.sh menu and config-loading path in an isolated copy
# so tests can never overwrite a real user's .whpconfig.
COPY="$TMP/copy"
mkdir -p "$COPY/scripts/whp-config" "$COPY/scripts/whp-build" \
    "$COPY/configs/devices/ppc-softmmu"
cp "$ROOT/build.sh" "$COPY/build.sh"
cp "$ROOT/scripts/whp-config/config.py" "$COPY/scripts/whp-config/config.py"
cp "$ROOT/scripts/whp-config/menuconfig.py" "$COPY/scripts/whp-config/menuconfig.py"
cp "$ROOT/scripts/whp-build/portable-build.py" "$COPY/scripts/whp-build/portable-build.py"
cp "$ROOT/scripts/whp-build/portable-build-entry.py" \
   "$COPY/scripts/whp-build/portable-build-entry.py"
cp "$ROOT/configs/devices/ppc-softmmu/default.mak" \
   "$COPY/configs/devices/ppc-softmmu/default.mak"

menu_output="$(/bin/sh "$COPY/build.sh" menuconfig --dump)"
grep -Fq 'Build outputs' <<< "$menu_output"
grep -Fq 'qemu-img' <<< "$menu_output"
grep -Fq 'qemu-system-i386' <<< "$menu_output"
grep -Fq 'qemu-system-ppc' <<< "$menu_output"
grep -Fq 'Host features' <<< "$menu_output"
grep -Fq 'Cocoa' <<< "$menu_output"
grep -Fq 'CoreAudio' <<< "$menu_output"
grep -Fq 'GTK' <<< "$menu_output"
grep -Fq 'PulseAudio' <<< "$menu_output"
grep -Fq 'Diagnostics' <<< "$menu_output"
grep -Fq 'Treat compiler warnings as errors' <<< "$menu_output"
grep -Fq 'AddressSanitizer' <<< "$menu_output"
grep -Fq 'UndefinedBehaviorSanitizer' <<< "$menu_output"
grep -Fq 'ThreadSanitizer' <<< "$menu_output"
grep -Fq 'Firmware' <<< "$menu_output"
grep -Fq 'Build behavior' <<< "$menu_output"
grep -Fq 'Install prefix' <<< "$menu_output"
grep -Fq 'Run tests after build' <<< "$menu_output"
grep -Fq 'QEMU machines' <<< "$menu_output"
if grep -Fq 'Build targets' <<< "$menu_output" ||
   grep -Fq 'QEMU target list' <<< "$menu_output" ||
   grep -Fq 'on macOS' <<< "$menu_output"; then
    printf 'error: menu exposes a raw target list or platform-specific wording\n' >&2
    exit 1
fi

cat > "$COPY/.whpconfig" <<'EOF'
WHP_CONFIG_VERSION=2
QEMU_HOST_LTO=auto
PREFIX=auto
BUILD_QEMU_IMG=y
BUILD_QEMU_SYSTEM_I386=y
BUILD_QEMU_SYSTEM_PPC=y
MACOS_ENABLE_COCOA=auto
MACOS_ENABLE_COREAUDIO=auto
MACOS_ENABLE_GTK=auto
MACOS_ENABLE_PA=auto
BUILD_OPENBIOS=auto
BOOTSTRAP_POWERPC_TOOLCHAIN=auto
WHP_INCREMENTAL_BUILD=y
RUN_TESTS=y
INSTALL=n
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
EOF
probe_output="$(WHP_SHELL_PROBE_ONLY=1 /bin/sh "$COPY/build.sh")"
grep -Fq 'WHP build shell:' <<< "$probe_output"
test ! -e "$COPY/configs/devices/ppc-softmmu/whp-user.mak"

portable_probe="$(
    WHP_FORCE_PORTABLE_CORE=1 \
    WHP_PORTABLE_PROBE_ONLY=1 \
    BUILD_QEMU_SYSTEM_I386=1 \
    BUILD_QEMU_SYSTEM_PPC=0 \
    /bin/sh "$COPY/build.sh" qemu-system-i386
)"
grep -Fq 'CONFIGURE_ARG=--target-list=i386-softmmu' <<< "$portable_probe"
grep -Fq 'CONFIGURE_ARG=--enable-werror' <<< "$portable_probe"
grep -Fq 'CONFIGURE_ARG=--disable-asan' <<< "$portable_probe"
grep -Fq 'CONFIGURE_ARG=--disable-ubsan' <<< "$portable_probe"
grep -Fq 'CONFIGURE_ARG=--disable-tsan' <<< "$portable_probe"
if grep -Fq -- '--enable-gtk' <<< "$portable_probe" ||
   grep -Fq -- '--enable-pa' <<< "$portable_probe"; then
    printf 'error: portable auto mode must not force GTK or PulseAudio\n' >&2
    exit 1
fi

portable_sanitizer_probe="$(
    WHP_FORCE_PORTABLE_CORE=1 \
    WHP_PORTABLE_PROBE_ONLY=1 \
    BUILD_QEMU_SYSTEM_I386=1 \
    BUILD_QEMU_SYSTEM_PPC=0 \
    QEMU_WERROR=0 \
    QEMU_ASAN=1 \
    QEMU_UBSAN=1 \
    QEMU_TSAN=0 \
    /bin/sh "$COPY/build.sh" qemu-system-i386
)"
grep -Fq 'CONFIGURE_ARG=--disable-werror' <<< "$portable_sanitizer_probe"
grep -Fq 'CONFIGURE_ARG=--enable-asan' <<< "$portable_sanitizer_probe"
grep -Fq 'CONFIGURE_ARG=--enable-ubsan' <<< "$portable_sanitizer_probe"
grep -Fq 'CONFIGURE_ARG=--disable-tsan' <<< "$portable_sanitizer_probe"

portable_tsan_error="$TMP/portable-tsan-error.txt"
if WHP_FORCE_PORTABLE_CORE=1 \
   WHP_PORTABLE_PROBE_ONLY=1 \
   BUILD_QEMU_SYSTEM_I386=1 \
   BUILD_QEMU_SYSTEM_PPC=0 \
   QEMU_ASAN=1 \
   QEMU_TSAN=1 \
   /bin/sh "$COPY/build.sh" qemu-system-i386 \
       >"$portable_tsan_error" 2>&1; then
    printf 'error: portable core accepted incompatible sanitizer settings\n' >&2
    exit 1
fi
grep -Fq 'QEMU_TSAN cannot be combined with QEMU_ASAN or QEMU_UBSAN' \
    "$portable_tsan_error"

# An unusable Bash discovered from PATH is not a reason to reject core QEMU.
# Explicitly naming a bad WHP_BUILD_BASH remains an error, but discovery must
# degrade to the portable Python core.
FAKEBIN="$TMP/fakebin"
mkdir -p "$FAKEBIN"
cat > "$FAKEBIN/bash" <<'EOF'
#!/bin/sh
exit 1
EOF
chmod +x "$FAKEBIN/bash"
old_bash_probe="$(PATH="$FAKEBIN:$PATH" WHP_SHELL_PROBE_ONLY=1 \
    /bin/sh "$COPY/build.sh")"
grep -Fq 'portable Python core' <<< "$old_bash_probe"

# Exercise configure-stage use of QEMU's device preset hook only when the user
# explicitly filters the tracked PPC defaults. The compatibility file must be
# removed immediately after configure.
SOURCE_DIR="$TMP/source"
BUILD_DIR="$TMP/build"
mkdir -p "$SOURCE_DIR/configs/devices/ppc-softmmu" "$BUILD_DIR"
cp "$ROOT/configs/devices/ppc-softmmu/default.mak" \
    "$SOURCE_DIR/configs/devices/ppc-softmmu/default.mak"
cat > "$SOURCE_DIR/configure" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > configure-args.txt
touch build.ninja
EOF
chmod +x "$SOURCE_DIR/configure"

HOST_OS=Linux
PROCESS_ARCH=x86_64
PHYSICAL_ARCH=x86_64
HOST_ARCH=x86_64
ROSETTA_TRANSLATED=0
MACOS_ALLOW_ROSETTA=0
MACOS_VERIFY_TOOLCHAIN=0
MACOS_ALLOW_NONCLANG=0
MACOS_ALLOW_COMPILER_CONFIG=0
MACOS_COMPILER_MANIFEST=disabled
MACOS_COMPILER_MANIFEST_SIGNATURE=disabled
MACOS_LTO_MANIFEST=disabled
MACOS_LTO_MANIFEST_SIGNATURE=disabled
CC_FOR_BUILD=cc
CXX_FOR_BUILD=c++
OBJC_FOR_BUILD=cc
STRIP_FOR_BUILD=strip
PKG_CONFIG_FOR_BUILD=pkg-config
CFLAGS=
MAKE_CMD=make
NINJA_CMD=ninja
QEMU_HOST_LTO=auto
BUILD_OPENBIOS=0
OPENBIOS_CROSS_COMPILE=
BOOTSTRAP_POWERPC_TOOLCHAIN=0
POWERPC_TOOLCHAIN_DIR="$TMP/powerpc"
QEMU_TARGET_LIST=ppc-softmmu
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=n
configure_args=(--target-list=ppc-softmmu)

source "$ROOT/scripts/whp-build/configure.bash"
whp_configure_build
grep -Fxq -- '--with-devices-ppc=whp-user' "$BUILD_DIR/configure-args.txt"
grep -Fq 'WHP_PPC_DEVICE_CONFIG_SIGNATURE=newworld=y;oldworld=n' "$BUILD_DIR/.whp-config"
test ! -e "$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"

# Tracked PPC defaults must not request or generate a custom device preset.
rm -f "$BUILD_DIR/build.ninja" "$BUILD_DIR/.whp-config"
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
configure_args=(--target-list=ppc-softmmu)
whp_configure_build
if grep -Fq -- '--with-devices-ppc=' "$BUILD_DIR/configure-args.txt"; then
    printf 'error: tracked PPC defaults must not use a generated source preset\n' >&2
    exit 1
fi
test ! -e "$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"

# Verify explicit host-feature switches feed configure, while auto does not.
# Earlier configure tests intentionally redirect SOURCE_DIR to a fake tree.
# Restore the real repository before loading the production build helpers.
SOURCE_DIR="$ROOT"
source "$ROOT/scripts/whp-build/common.bash"
source "$ROOT/scripts/whp-build/prepare-build.bash"
source "$ROOT/scripts/whp-build/diagnostics.bash"
HOST_OS=Linux
CC=cc
CXX=c++
CC_FOR_BUILD=cc
PREFIX=/portable-prefix
QEMU_TARGET_LIST=ppc-softmmu
BUILD_QEMU_IMG=1
MACOS_ENABLE_GTK=auto
MACOS_ENABLE_PA=auto
QEMU_HOST_LTO=auto
whp_prepare_configure_args
generic_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--prefix=/portable-prefix' <<< "$generic_args"
if grep -Eq -- '--(enable|disable)-(gtk|pa|lto)' <<< "$generic_args"; then
    printf 'error: auto host features must be left to QEMU/Meson detection\n' >&2
    exit 1
fi

MACOS_ENABLE_GTK=0
MACOS_ENABLE_PA=1
QEMU_HOST_LTO=0
whp_prepare_configure_args
generic_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--disable-gtk' <<< "$generic_args"
grep -Fxq -- '--enable-pa' <<< "$generic_args"
grep -Fxq -- '--disable-lto' <<< "$generic_args"

QEMU_WERROR=1
QEMU_ASAN=1
QEMU_UBSAN=1
QEMU_TSAN=0
whp_apply_qemu_diagnostics
generic_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--enable-werror' <<< "$generic_args"
grep -Fxq -- '--enable-asan' <<< "$generic_args"
grep -Fxq -- '--enable-ubsan' <<< "$generic_args"
grep -Fxq -- '--disable-tsan' <<< "$generic_args"

configure_args=()
QEMU_WERROR=1
QEMU_ASAN=0
QEMU_UBSAN=0
QEMU_TSAN=1
whp_apply_qemu_diagnostics
generic_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--enable-werror' <<< "$generic_args"
grep -Fxq -- '--disable-asan' <<< "$generic_args"
grep -Fxq -- '--disable-ubsan' <<< "$generic_args"
grep -Fxq -- '--enable-tsan' <<< "$generic_args"

configure_args=()
QEMU_WERROR=1
QEMU_ASAN=1
QEMU_UBSAN=0
QEMU_TSAN=1
if whp_apply_qemu_diagnostics 2>/dev/null; then
    printf 'error: Bash builder accepted incompatible sanitizer settings\n' >&2
    exit 1
fi
[[ ${#configure_args[@]} == 0 ]]

# Direct environment overrides accept common boolean spellings instead of
# requiring the config renderer's internal 0/1 representation.
MACOS_ENABLE_GTK=y
MACOS_ENABLE_PA=N
BUILD_OPENBIOS=Yes
BOOTSTRAP_POWERPC_TOOLCHAIN=off
QEMU_HOST_LTO=Auto
whp_require_tristate_values MACOS_ENABLE_GTK MACOS_ENABLE_PA \
    BUILD_OPENBIOS BOOTSTRAP_POWERPC_TOOLCHAIN QEMU_HOST_LTO
[[ "$MACOS_ENABLE_GTK" == 1 ]]
[[ "$MACOS_ENABLE_PA" == 0 ]]
[[ "$BUILD_OPENBIOS" == 1 ]]
[[ "$BOOTSTRAP_POWERPC_TOOLCHAIN" == 0 ]]
[[ "$QEMU_HOST_LTO" == auto ]]

# Default policy is unprivileged: install is off and prefix is user/build local.
unset PREFIX INSTALL
HOST_OS=Linux
HOST_ARCH=x86_64
HOME="$TMP/home"
mkdir -p "$HOME"
whp_prepare_build_defaults
[[ "$RUN_TESTS" == 1 ]]
[[ "$INSTALL" == 0 ]]
[[ "$PREFIX" == "$HOME/.local/whp-qemu" ]]
[[ "$PREFIX" != /emulator ]]

# RUN_TESTS is post-build policy. QEMU builds run make check when enabled,
# skip it when disabled, and firmware-only targets do not trigger the QEMU suite.
TEST_BUILD_DIR="$TMP/test-build"
TEST_NINJA_LOG="$TMP/test-ninja.log"
TEST_MAKE_LOG="$TMP/test-make.log"
FAKE_TEST_NINJA="$TMP/fake-test-ninja"
FAKE_TEST_MAKE="$TMP/fake-test-make"
mkdir -p "$TEST_BUILD_DIR"
cat > "$FAKE_TEST_NINJA" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$WHP_TEST_NINJA_LOG"
EOF
cat > "$FAKE_TEST_MAKE" <<'EOF'
#!/bin/sh
printf '%s\n' "$*" >> "$WHP_TEST_MAKE_LOG"
EOF
chmod +x "$FAKE_TEST_NINJA" "$FAKE_TEST_MAKE"

RUN_TESTS=1 INSTALL=0 JOBS=2 \
BUILD_DIR="$TEST_BUILD_DIR" NINJA_CMD="$FAKE_TEST_NINJA" MAKE_CMD="$FAKE_TEST_MAKE" \
WHP_TEST_NINJA_LOG="$TEST_NINJA_LOG" WHP_TEST_MAKE_LOG="$TEST_MAKE_LOG" \
bash -c 'set -euo pipefail; source "$1"; whp_build_targets qemu-system-i386' \
    _ "$ROOT/scripts/whp-build/build-targets.bash"
grep -Fq 'qemu-system-i386' "$TEST_NINJA_LOG"
grep -Fq ' check' "$TEST_MAKE_LOG"

: > "$TEST_MAKE_LOG"
RUN_TESTS=0 INSTALL=0 JOBS=2 \
BUILD_DIR="$TEST_BUILD_DIR" NINJA_CMD="$FAKE_TEST_NINJA" MAKE_CMD="$FAKE_TEST_MAKE" \
WHP_TEST_NINJA_LOG="$TEST_NINJA_LOG" WHP_TEST_MAKE_LOG="$TEST_MAKE_LOG" \
bash -c 'set -euo pipefail; source "$1"; whp_build_targets qemu-system-i386' \
    _ "$ROOT/scripts/whp-build/build-targets.bash"
test ! -s "$TEST_MAKE_LOG"

: > "$TEST_MAKE_LOG"
RUN_TESTS=1 INSTALL=0 JOBS=2 \
BUILD_DIR="$TEST_BUILD_DIR" NINJA_CMD="$FAKE_TEST_NINJA" MAKE_CMD="$FAKE_TEST_MAKE" \
WHP_TEST_NINJA_LOG="$TEST_NINJA_LOG" WHP_TEST_MAKE_LOG="$TEST_MAKE_LOG" \
bash -c 'set -euo pipefail; source "$1"; whp_build_targets whp-openbios-ppc' \
    _ "$ROOT/scripts/whp-build/build-targets.bash"
test ! -s "$TEST_MAKE_LOG"

python3 -m py_compile "$ROOT/scripts/whp-build/portable-build-entry.py"
bash -n "$ROOT/scripts/whp-build/diagnostics.bash"

printf 'WHP portable configuration integration: verified\n'