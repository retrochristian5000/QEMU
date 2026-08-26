#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
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
exit 2
EOF
chmod +x "$fake_brew"
export WHP_TEST_BREW_FORMULAE="$formulae"
export WHP_HOMEBREW_BREW="$fake_brew"

source "$ROOT/scripts/whp-build/homebrew-deps.bash"

# pkg-config metadata often embeds the versioned Cellar keg. QEMU must see the
# stable opt symlink instead so a formula upgrade cannot strand build.ninja.
fake_pkg_config="$TMP_ROOT/pkg-config"
cat > "$fake_pkg_config" <<'EOF'
#!/bin/sh
printf '%s\n' \
  '-I/opt/homebrew/Cellar/libslirp/4.9.3/include -L/opt/homebrew/Cellar/libslirp/4.9.3/lib -lslirp' \
  '/opt/homebrew/Cellar/openssl@3/3.6.0/lib/pkgconfig'
EOF
chmod +x "$fake_pkg_config"
normalized="$(
    HOMEBREW_PREFIX=/opt/homebrew \
    WHP_REAL_PKG_CONFIG="$fake_pkg_config" \
    "$ROOT/scripts/whp-build/pkg-config-homebrew.bash" --cflags --libs libslirp
)"
case "$normalized" in
    *'/opt/homebrew/Cellar/'*)
        printf 'error: pkg-config output still contains a versioned Homebrew Cellar path\n' >&2
        exit 1
        ;;
esac
grep -Fq '/opt/homebrew/opt/libslirp/include' <<< "$normalized"
grep -Fq '/opt/homebrew/opt/libslirp/lib' <<< "$normalized"
grep -Fq '/opt/homebrew/opt/openssl@3/lib/pkgconfig' <<< "$normalized"

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

source "$ROOT/scripts/whp-build/configure.bash"

printf '%s\n' \
    'glib 2.86.0' \
    'libslirp 4.9.3' \
    'pixman 0.46.4' > "$formulae"
old_signature="$(whp_homebrew_dependency_signature "$fake_brew")"
whp_refresh_homebrew_dependency_identity
whp_configure_build
first_count="$(cat "$BUILD_DIR/configure-count")"

# An unchanged Homebrew inventory must not churn configure.
whp_refresh_homebrew_dependency_identity
whp_configure_build
stable_count="$(cat "$BUILD_DIR/configure-count")"

printf '%s\n' \
    'glib 2.86.0' \
    'libslirp 4.10.0' \
    'pixman 0.46.4' > "$formulae"
new_signature="$(whp_homebrew_dependency_signature "$fake_brew")"
whp_refresh_homebrew_dependency_identity

if ! grep -Fq 'WHP_HOMEBREW_DEPENDENCIES_STALE=' "$BUILD_DIR/.whp-config"; then
    printf 'error: Homebrew upgrade did not mark the QEMU config stale\n' >&2
    exit 1
fi

whp_configure_build
second_count="$(cat "$BUILD_DIR/configure-count")"

if grep -Fq 'WHP_HOMEBREW_DEPENDENCIES_STALE=' "$BUILD_DIR/.whp-config"; then
    printf 'error: one-shot Homebrew stale marker survived successful configure\n' >&2
    exit 1
fi

if [[ -z "$old_signature" || -z "$new_signature" ||
      "$old_signature" == "$new_signature" ]]; then
    printf 'error: libslirp upgrade did not change the Homebrew signature\n' >&2
    exit 1
fi
if [[ "$first_count" != 1 || "$stable_count" != 1 || "$second_count" != 2 ]]; then
    printf '%s\n' \
        'error: Homebrew dependency refresh did not reconfigure exactly once.' \
        "first=$first_count stable=$stable_count upgraded=$second_count" >&2
    exit 1
fi

if ! grep -Fq 'FORMULA=libslirp 4.10.0' "$BUILD_DIR/.whp-homebrew-deps"; then
    printf 'error: Homebrew dependency manifest did not record upgraded libslirp\n' >&2
    exit 1
fi

# Existing trees created before the Homebrew manifest must also reconfigure
# once; otherwise the user's current stale Cellar path survives this upgrade.
legacy_build="$TMP_ROOT/legacy-build"
mkdir -p "$legacy_build"
printf 'SOURCE_DIR=%s\nQEMU_TARGET_LIST=ppc-softmmu\n' "$fake_source" > "$legacy_build/.whp-config"
touch "$legacy_build/build.ninja"
BUILD_DIR="$legacy_build"
whp_refresh_homebrew_dependency_identity
if ! grep -Fq 'WHP_HOMEBREW_DEPENDENCIES_STALE=' "$BUILD_DIR/.whp-config"; then
    printf 'error: pre-manifest build tree was not marked stale on first refresh\n' >&2
    exit 1
fi

printf 'Homebrew dependency refresh: PASS (%s -> %s)\n' \
    "$old_signature" "$new_signature"
