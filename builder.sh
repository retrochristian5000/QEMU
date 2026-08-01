#!/usr/bin/env bash

set -e


# This variable controls the file loaded for each emulator profile. The filename is the same for all profiles, but the directories are profile-specific.
export ARCH_DEVICE_FILE="whp-profile"

# This variable controls the C compiler flags.
export CFLAGS="-g0 -march=native -mtune=native -pipe -w"

# This variable controls the C++ compiler flags.
export CXXFLAGS="-g0 -P -pipe -w"

# This variable controls the installation prefix.
export PREFIX="/emulator"

# This variable controls the target list.
export QEMU_TARGET_LIST="i386-softmmu,ppc-softmmu"

# Configure QEMU based on this script's settings.
./configure --enable-gtk --enable-pixman --enable-pa --enable-rng-none --enable-slirp --enable-tools --prefix="$PREFIX" --target-list="$QEMU_TARGET_LIST" --without-default-devices --without-default-features --with-devices-ppc="$ARCH_DEVICE_FILE"
make all install
