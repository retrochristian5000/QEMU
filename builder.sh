#!/usr/bin/env bash

set -e

# This variable controls the installation prefix.
export PREFIX="/emulator"

# This variable controls the target list.
export QEMU_TARGET_LIST="ppc-softmmu"

# This variable controls the file loaded for each emulator profile. The filename is the same for all profiles, but the directories are profile-specific.
export ARCH_DEVICE_FILE="whp-profile"

# Configure QEMU based on this script's settings.
./configure --enable-gtk --enable-pixman --enable-pulseaudio --enable-rng-none --enable-slirp --prefix="$PREFIX" --target-list="$QEMU_TARGET_LIST" --without-default-devices --without-default-features --with-devices-ppc="$ARCH_DEVICE_FILE"
make all install
