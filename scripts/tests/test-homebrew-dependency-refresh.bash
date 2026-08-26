#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/whp-homebrew-refresh.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT

formulae="$TMP_ROOT/formulae.txt"
fake_brew="$TMP_ROOT/brew"
cat > "$fake_brew" <<'EOF'
#!/bin/sh
set -eu
if [ "$#" -eq 3 ] && [ "$1" = list ] && [ "$2" = --formula ] && [ "$3" = --versions ]; then
    cat "$WHP_TEST_BREW_FORMULAE"
    exit 0
fi
printf 'unsupported fake brew invocation:' >&2
printf ' %s' "$@" >&2
printf '\n' >&2
exit 2
EOF
chmod +x "$fake_brew"
export WHP_TEST_BREW_FORMULAE="$formulae"

source "$SOURCE_DIR/scripts/macos-build-hygiene.bash"

printf '%s\n' \
    'glib 2.86.0' \
    'libslirp 4.9.3' \
    'pixman 0.46.4' > "$formulae"
old_signature="$(whp_homebrew_dependency_signature "$fake_brew")"

printf '%s\n' \
    'glib 2.86.0' \
    'libslirp 4.10.0' \
    'pixman 0.46.4' > "$formulae"
new_signature="$(whp_homebrew_dependency_signature "$fake_brew")"

if [[ -z "$old_signature" || -z "$new_signature" ||
      "$old_signature" == "$new_signature" ]]; then
    printf '%s\n' \
        'error: Homebrew dependency signature did not change after libslirp upgrade.' \
        "old=$old_signature" \
        "new=$new_signature" >&2
    exit 1
fi

fake_source="$TMP_ROOT/source"
fake_build="$TMP_ROOT/build"
mkdir -p "$fake_source" "$fake_build"
cat > "$fake_source/configure" <<'EOF'
#!/bin/sh
set -eu
count_file="$PWD/configure-count"
count=0
if [ -f "$count_file" ]; then
    count="$(cat "$count_file")"
fi
count=$((count + 1))
printf '%s\n' "$count" > "$count_file"
touch build.ninja
EOF
chmod +x "$fake_source/configure"

SOURCE_DIR="$fake_source"
BUILD_DIR="$fake_build"
HOST_OS=Darwin
PROCESS_ARCH=arm64
PHYSICAL_ARCH=arm64
HOST_ARCH=arm64
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
CC=cc
CXX=c++
OBJC=cc
CFLAGS=
CXXFLAGS=
OBJCFLAGS=
CPPFLAGS=
LDFLAGS=
DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
SDKROOT=/tmp/MacOSX.sdk
MACOS_SDK_VERSION=15.0
MACOSX_DEPLOYMENT_TARGET=14.0
PKG_CONFIG=pkg-config
PKG_CONFIG_PATH=/opt/homebrew/lib/pkgconfig
PKG_CONFIG_PATH_FOR_BUILD="$PKG_CONFIG_PATH"
HOMEBREW_PREFIX=/opt/homebrew
MAKE_CMD=make
NINJA_CMD=ninja
PYTHON=python3
QEMU_TARGET_LIST=
QEMU_HOST_LTO=auto
BUILD_OPENBIOS=0
OPENBIOS_CROSS_COMPILE=
BOOTSTRAP_POWERPC_TOOLCHAIN=0
POWERPC_TOOLCHAIN_COMPILER=clang
POWERPC_TOOLCHAIN_SOURCE_MODE=release
POWERPC_TOOLCHAIN_DIR="$TMP_ROOT/powerpc-elf"
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
WHP_INCREMENTAL_BUILD=1
configure_args=(--disable-system --disable-tools)

source "$WHP_ORIGINAL_SOURCE_DIR/scripts/whp-build/configure.bash"

HOMEBREW_DEPENDENCY_SIGNATURE="$old_signature"
whp_configure_build
first_count="$(cat "$BUILD_DIR/configure-count")"

HOMEBREW_DEPENDENCY_SIGNATURE="$new_signature"
whp_configure_build
second_count="$(cat "$BUILD_DIR/configure-count")"

if [[ "$first_count" != 1 || "$second_count" != 2 ]]; then
    printf '%s\n' \
        'error: a Homebrew dependency upgrade did not force in-place QEMU reconfiguration.' \
        "first configure count=$first_count" \
        "second configure count=$second_count" >&2
    exit 1
fi

printf 'Homebrew dependency refresh: PASS (%s -> %s)\n' \
    "$old_signature" "$new_signature"
