#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Exercise the public build.sh menu and config-loading path in an isolated copy
# so tests can never overwrite a real user's .whpconfig.
COPY="$TMP/copy"
mkdir -p "$COPY/scripts/whp-config" "$COPY/configs/devices/ppc-softmmu"
cp "$ROOT/build.sh" "$COPY/build.sh"
cp "$ROOT/scripts/whp-config/config.py" "$COPY/scripts/whp-config/config.py"
cp "$ROOT/scripts/whp-config/menuconfig.py" "$COPY/scripts/whp-config/menuconfig.py"
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
grep -Fq 'Firmware' <<< "$menu_output"
grep -Fq 'Build behavior' <<< "$menu_output"
grep -Fq 'Install prefix' <<< "$menu_output"
grep -Fq 'QEMU machines' <<< "$menu_output"
if grep -Fq 'Build targets' <<< "$menu_output" ||
   grep -Fq 'QEMU target list' <<< "$menu_output" ||
   grep -Fq 'on macOS' <<< "$menu_output"; then
    printf 'error: menu exposes a raw target list or platform-specific wording\n' >&2
    exit 1
fi

cat > "$COPY/.whpconfig" <<'EOF'
WHP_CONFIG_VERSION=1
QEMU_HOST_LTO=auto
PREFIX=/opt/whp-qemu
BUILD_QEMU_IMG=y
BUILD_QEMU_SYSTEM_I386=y
BUILD_QEMU_SYSTEM_PPC=y
MACOS_ENABLE_COCOA=y
MACOS_ENABLE_COREAUDIO=y
MACOS_ENABLE_GTK=n
MACOS_ENABLE_PA=n
BUILD_OPENBIOS=y
BOOTSTRAP_POWERPC_TOOLCHAIN=y
WHP_INCREMENTAL_BUILD=y
INSTALL=n
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=n
EOF
probe_output="$(WHP_SHELL_PROBE_ONLY=1 /bin/sh "$COPY/build.sh")"
grep -Fq 'WHP build shell:' <<< "$probe_output"
grep -Fq 'CONFIG_MAC_NEWWORLD=y' \
    "$COPY/configs/devices/ppc-softmmu/whp-user.mak"
grep -Fq 'CONFIG_MAC_OLDWORLD=n' \
    "$COPY/configs/devices/ppc-softmmu/whp-user.mak"

# Exercise the configure-stage bridge to QEMU's supported device preset hook.
SOURCE_DIR="$TMP/source"
BUILD_DIR="$TMP/build"
mkdir -p "$SOURCE_DIR/configs/devices/ppc-softmmu" "$BUILD_DIR"
printf 'CONFIG_MAC_NEWWORLD=y\nCONFIG_MAC_OLDWORLD=n\n' > \
    "$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"
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
QEMU_HOST_LTO=0
BUILD_OPENBIOS=0
OPENBIOS_CROSS_COMPILE=
BOOTSTRAP_POWERPC_TOOLCHAIN=0
POWERPC_TOOLCHAIN_DIR="$TMP/powerpc"
QEMU_TARGET_LIST=ppc-softmmu
configure_args=(--target-list=ppc-softmmu)

source "$ROOT/scripts/whp-build/configure.bash"
whp_configure_build
grep -Fxq -- '--with-devices-ppc=whp-user' "$BUILD_DIR/configure-args.txt"
grep -Fq 'WHP_PPC_DEVICE_CONFIG_SIGNATURE=' "$BUILD_DIR/.whp-config"

# Verify macOS host feature switches and prefix feed configure explicitly.
source "$ROOT/scripts/whp-build/common.bash"
source "$ROOT/scripts/whp-build/prepare-build.bash"
HOST_OS=Darwin
CC=clang
CXX=clang++
CC_FOR_BUILD=clang
OBJC=clang
PREFIX=/portable-prefix
QEMU_HOST_LTO=0
BUILD_QEMU_IMG=1
BUILD_QEMU_SYSTEM_I386=1
BUILD_QEMU_SYSTEM_PPC=1
MACOS_ENABLE_COCOA=0
MACOS_ENABLE_COREAUDIO=0
MACOS_ENABLE_GTK=0
MACOS_ENABLE_PA=0
whp_prepare_configure_args
macos_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--prefix=/portable-prefix' <<< "$macos_args"
grep -Fxq -- '--disable-cocoa' <<< "$macos_args"
grep -Fxq -- '--disable-coreaudio' <<< "$macos_args"
grep -Fxq -- '--disable-gtk' <<< "$macos_args"
grep -Fxq -- '--disable-pa' <<< "$macos_args"
if grep -Fq -- '--audio-drv-list=' <<< "$macos_args"; then
    printf 'error: disabled macOS audio backends must not emit an audio driver list\n' >&2
    exit 1
fi

MACOS_ENABLE_COCOA=1
MACOS_ENABLE_COREAUDIO=1
MACOS_ENABLE_GTK=1
MACOS_ENABLE_PA=1
whp_prepare_configure_args
macos_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--enable-cocoa' <<< "$macos_args"
grep -Fxq -- '--enable-coreaudio' <<< "$macos_args"
grep -Fxq -- '--enable-gtk' <<< "$macos_args"
grep -Fxq -- '--enable-pa' <<< "$macos_args"
grep -Fxq -- '--audio-drv-list=coreaudio,pa' <<< "$macos_args"

# Output selections feed QEMU's tools switch and derived system target list.
HOST_OS=Linux
QEMU_TARGET_LIST=x86_64-softmmu
BUILD_QEMU_IMG=1
BUILD_QEMU_SYSTEM_I386=1
BUILD_QEMU_SYSTEM_PPC=1
whp_prepare_build_defaults
whp_prepare_configure_args
output_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--target-list=ppc-softmmu,i386-softmmu' <<< "$output_args"
grep -Fxq -- '--enable-tools' <<< "$output_args"

BUILD_QEMU_IMG=0
BUILD_QEMU_SYSTEM_I386=0
BUILD_QEMU_SYSTEM_PPC=1
whp_prepare_build_defaults
whp_prepare_configure_args
output_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--target-list=ppc-softmmu' <<< "$output_args"
grep -Fxq -- '--disable-tools' <<< "$output_args"

BUILD_QEMU_IMG=1
BUILD_QEMU_SYSTEM_I386=1
BUILD_QEMU_SYSTEM_PPC=0
whp_prepare_build_defaults
whp_prepare_configure_args
output_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--target-list=i386-softmmu' <<< "$output_args"

BUILD_QEMU_IMG=1
BUILD_QEMU_SYSTEM_I386=0
BUILD_QEMU_SYSTEM_PPC=0
whp_prepare_build_defaults
whp_prepare_configure_args
output_args="$(printf '%s\n' "${configure_args[@]}")"
grep -Fxq -- '--disable-system' <<< "$output_args"
if grep -Fq -- '--target-list=' <<< "$output_args"; then
    printf 'error: tools-only configuration must not emit a target list\n' >&2
    exit 1
fi

# A tools-only build carries an empty internal target list into artifact checks.
source "$ROOT/scripts/whp-build/post-build.bash"
if whp_target_list_contains ppc-softmmu; then
    printf 'error: an empty target list must not request the PPC emulator\n' >&2
    exit 1
fi

printf 'WHP portable configuration integration: verified\n'
