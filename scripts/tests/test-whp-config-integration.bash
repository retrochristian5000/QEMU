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
grep -Fq 'Build targets' <<< "$menu_output"
grep -Fq 'Host features' <<< "$menu_output"
grep -Fq 'Firmware' <<< "$menu_output"
grep -Fq 'Build behavior' <<< "$menu_output"
grep -Fq 'QEMU machines' <<< "$menu_output"

cat > "$COPY/.whpconfig" <<'EOF'
WHP_CONFIG_VERSION=1
QEMU_TARGET_LIST=ppc-softmmu
QEMU_HOST_LTO=auto
MACOS_ENABLE_GTK=n
MACOS_ENABLE_PA=n
BUILD_OPENBIOS=y
BOOTSTRAP_POWERPC_TOOLCHAIN=y
WHP_INCREMENTAL_BUILD=y
INSTALL=n
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=n
EOF
WHP_SHELL_PROBE_ONLY=1 /bin/sh "$COPY/build.sh" >/dev/null
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

printf 'WHP portable configuration integration: verified\n'
