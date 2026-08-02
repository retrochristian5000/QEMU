#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET}"
TOOLCHAIN_DOWNLOAD_DIR="${POWERPC_TOOLCHAIN_DOWNLOAD_DIR:-$SOURCE_DIR/build/toolchain-downloads}"
TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
TOOLCHAIN_HOST_CC="${TOOLCHAIN_HOST_CC:-${CC_FOR_BUILD:-${CC:-cc}}}"
TOOLCHAIN_HOST_CXX="${TOOLCHAIN_HOST_CXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
MAKE_CMD="${MAKE_CMD:-${MAKE:-make}}"
JOBS="${JOBS:-1}"
stage_root=""
temporary_download=""

BINUTILS_VERSION="${POWERPC_BINUTILS_VERSION:-2.44}"
GCC_VERSION="${POWERPC_GCC_VERSION:-14.2.0}"
BINUTILS_ARCHIVE="binutils-${BINUTILS_VERSION}.tar.xz"
GCC_ARCHIVE="gcc-${GCC_VERSION}.tar.xz"
BINUTILS_URL="${POWERPC_BINUTILS_URL:-https://sourceware.org/pub/binutils/releases/$BINUTILS_ARCHIVE}"
GCC_URL="${POWERPC_GCC_URL:-https://gcc.gnu.org/pub/gcc/releases/gcc-$GCC_VERSION/$GCC_ARCHIVE}"
BINUTILS_SHA256="${POWERPC_BINUTILS_SHA256:-ce2017e059d63e67ddb9240e9d4ec49c2893605035cd60e92ad53177f4377237}"
GCC_SHA256="${POWERPC_GCC_SHA256:-a7b39bc69cbf9e25826c5a60ab26477001f7c08d85cec04bc0e29cabed6f3cc9}"

case "$TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac

if ! "$MAKE_CMD" --version 2>/dev/null | head -n 1 | grep -q 'GNU Make'; then
    printf 'error: PowerPC toolchain bootstrap requires GNU Make\n' >&2
    printf 'set MAKE_CMD to gmake or another GNU Make executable\n' >&2
    exit 1
fi

for required in tar sed grep awk bzip2 gzip perl; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: PowerPC toolchain bootstrap dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done

if command -v curl >/dev/null 2>&1; then
    download_cmd=curl
elif command -v wget >/dev/null 2>&1; then
    download_cmd=wget
else
    printf 'error: curl or wget is required to download the toolchain sources\n' >&2
    exit 1
fi

if command -v shasum >/dev/null 2>&1; then
    hash_cmd=(shasum -a 256)
elif command -v sha256sum >/dev/null 2>&1; then
    hash_cmd=(sha256sum)
else
    printf 'error: shasum or sha256sum is required to verify downloads\n' >&2
    exit 1
fi

powerpc_tools=(gcc as ar ld nm objcopy objdump readelf strip ranlib)
toolchain_is_usable()
{
    local prefix_dir="$1"
    local tool

    for tool in "${powerpc_tools[@]}"; do
        [[ -x "$prefix_dir/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
    done

    case "$("$prefix_dir/bin/${TOOLCHAIN_TARGET}-gcc" -dumpmachine)" in
        "$TOOLCHAIN_TARGET"|powerpc-*-elf) return 0 ;;
        *) return 1 ;;
    esac
}

marker="$TOOLCHAIN_DIR/.whp-powerpc-toolchain"
expected_marker="$(cat <<MARKER
BOOTSTRAP_SCHEMA=2
BUILD_SYSTEM=$(uname -srm)
BUILD_PROCESS_ARCH=$(uname -m)
ROSETTA_TRANSLATED=$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')
TARGET=$TOOLCHAIN_TARGET
BINUTILS_VERSION=$BINUTILS_VERSION
BINUTILS_SHA256=$BINUTILS_SHA256
GCC_VERSION=$GCC_VERSION
GCC_SHA256=$GCC_SHA256
HOST_CC=$TOOLCHAIN_HOST_CC
HOST_CXX=$TOOLCHAIN_HOST_CXX
MARKER
)"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == "0" ]] &&
   [[ -f "$marker" ]] &&
   [[ "$(cat "$marker")" == "$expected_marker" ]] &&
   toolchain_is_usable "$TOOLCHAIN_DIR"; then
    printf 'PowerPC bootstrap toolchain is current: %s/bin/%s-\n' \
        "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
    exit 0
fi

mkdir -p "$TOOLCHAIN_DOWNLOAD_DIR" "$TOOLCHAIN_WORK_DIR"
lock_dir="$TOOLCHAIN_WORK_DIR/.bootstrap-lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
    printf 'error: another PowerPC toolchain bootstrap is using %s\n' \
        "$TOOLCHAIN_WORK_DIR" >&2
    exit 1
fi
cleanup()
{
    [[ -z "$temporary_download" ]] || rm -f "$temporary_download"
    [[ -z "$stage_root" ]] || rm -rf "$stage_root"
    rmdir "$lock_dir" 2>/dev/null || true
}
trap cleanup EXIT

download_and_verify()
{
    local url="$1"
    local output="$2"
    local expected="$3"
    local actual

    if [[ ! -f "$output" ]]; then
        temporary_download="${output}.tmp.$$"
        rm -f "$temporary_download"
        if [[ "$download_cmd" == curl ]]; then
            curl --fail --location --retry 3 --output "$temporary_download" "$url"
        else
            wget --tries=3 --output-document="$temporary_download" "$url"
        fi
        mv -f "$temporary_download" "$output"
        temporary_download=""
    fi

    actual="$("${hash_cmd[@]}" "$output" | awk '{print $1}')"
    if [[ "$actual" != "$expected" ]]; then
        rm -f "$output"
        printf 'error: checksum mismatch for %s\n' "$output" >&2
        printf 'expected: %s\nactual:   %s\n' "$expected" "$actual" >&2
        exit 1
    fi
}

extract_archive()
{
    local archive="$1"
    local source_dir="$2"

    if [[ ! -f "$source_dir/.whp-extracted" ]]; then
        rm -rf "$source_dir"
        tar -xf "$archive" -C "$TOOLCHAIN_WORK_DIR"
        touch "$source_dir/.whp-extracted"
    fi
}

binutils_tar="$TOOLCHAIN_DOWNLOAD_DIR/$BINUTILS_ARCHIVE"
gcc_tar="$TOOLCHAIN_DOWNLOAD_DIR/$GCC_ARCHIVE"
binutils_src="$TOOLCHAIN_WORK_DIR/binutils-$BINUTILS_VERSION"
gcc_src="$TOOLCHAIN_WORK_DIR/gcc-$GCC_VERSION"
binutils_build="$TOOLCHAIN_WORK_DIR/build-binutils-$BINUTILS_VERSION"
gcc_build="$TOOLCHAIN_WORK_DIR/build-gcc-$GCC_VERSION"

download_and_verify "$BINUTILS_URL" "$binutils_tar" "$BINUTILS_SHA256"
download_and_verify "$GCC_URL" "$gcc_tar" "$GCC_SHA256"
extract_archive "$binutils_tar" "$binutils_src"
extract_archive "$gcc_tar" "$gcc_src"

# GCC 14's helper still names an HTTP endpoint. Use HTTPS while retaining
# the release-provided prerequisite checksums and pinned dependency versions.
sed -i.bak \
    "s|base_url='http://gcc.gnu.org/pub/gcc/infrastructure/'|base_url='https://gcc.gnu.org/pub/gcc/infrastructure/'|" \
    "$gcc_src/contrib/download_prerequisites"
rm -f "$gcc_src/contrib/download_prerequisites.bak"
sed -i.bak '/^[[:space:]]*echo "${gettext}"[[:space:]]*$/d' \
    "$gcc_src/contrib/download_prerequisites"
rm -f "$gcc_src/contrib/download_prerequisites.bak"
(
    cd "$gcc_src"
    ./contrib/download_prerequisites --no-isl
)

stage_root="$TOOLCHAIN_WORK_DIR/install-root.$$"
staged_toolchain="$stage_root$TOOLCHAIN_DIR"
rm -rf "$stage_root"
mkdir -p "$stage_root" "$(dirname "$TOOLCHAIN_DIR")"

rm -rf "$binutils_build"
mkdir -p "$binutils_build"
(
    cd "$binutils_build"
    env -u CFLAGS -u CXXFLAGS -u CPPFLAGS -u LDFLAGS \
        CC="$TOOLCHAIN_HOST_CC" CXX="$TOOLCHAIN_HOST_CXX" \
        "$binutils_src/configure" \
        --target="$TOOLCHAIN_TARGET" \
        --prefix="$TOOLCHAIN_DIR" \
        --disable-gdb \
        --disable-gdbserver \
        --disable-gprofng \
        --disable-gold \
        --disable-nls \
        --disable-shared \
        --disable-sim \
        --disable-werror \
        --enable-static
    "$MAKE_CMD" -j"$JOBS" MAKEINFO=true
    "$MAKE_CMD" MAKEINFO=true DESTDIR="$stage_root" install
)

rm -rf "$gcc_build"
mkdir -p "$gcc_build"
(
    cd "$gcc_build"
    export PATH="$staged_toolchain/bin:$PATH"
    env -u CFLAGS -u CXXFLAGS -u CPPFLAGS -u LDFLAGS \
        CC="$TOOLCHAIN_HOST_CC" CXX="$TOOLCHAIN_HOST_CXX" \
        "$gcc_src/configure" \
        --target="$TOOLCHAIN_TARGET" \
        --prefix="$TOOLCHAIN_DIR" \
        --with-cpu=604 \
        --with-endian=big \
        --with-newlib \
        --without-headers \
        --without-isl \
        --without-zstd \
        --disable-bootstrap \
        --disable-decimal-float \
        --disable-libatomic \
        --disable-libgomp \
        --disable-libquadmath \
        --disable-libsanitizer \
        --disable-libssp \
        --disable-multilib \
        --disable-nls \
        --disable-shared \
        --disable-threads \
        --disable-werror \
        --enable-languages=c
    "$MAKE_CMD" -j"$JOBS" MAKEINFO=true all-gcc
    "$MAKE_CMD" MAKEINFO=true DESTDIR="$stage_root" install-gcc
)

if ! toolchain_is_usable "$staged_toolchain"; then
    printf 'error: bootstrapped PowerPC toolchain is incomplete\n' >&2
    exit 1
fi

test_source="$TOOLCHAIN_WORK_DIR/toolchain-smoke.c"
test_object="$TOOLCHAIN_WORK_DIR/toolchain-smoke.o"
printf 'int whp_powerpc_toolchain_smoke(void) { return 0; }\n' > "$test_source"
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-gcc" \
    -m32 -mcpu=604 -msoft-float -ffreestanding \
    -c "$test_source" -o "$test_object"
if ! "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" -h "$test_object" |
     grep -q 'Machine:.*PowerPC'; then
    printf 'error: PowerPC toolchain smoke test produced the wrong architecture\n' >&2
    exit 1
fi
rm -f "$test_source" "$test_object"

printf '%s\n' "$expected_marker" > "$staged_toolchain/.whp-powerpc-toolchain"
old_toolchain="${TOOLCHAIN_DIR}.old.$$"
rm -rf "$old_toolchain"
if [[ -e "$TOOLCHAIN_DIR" ]]; then
    mv "$TOOLCHAIN_DIR" "$old_toolchain"
fi
if ! mv "$staged_toolchain" "$TOOLCHAIN_DIR"; then
    [[ ! -e "$old_toolchain" ]] || mv "$old_toolchain" "$TOOLCHAIN_DIR"
    exit 1
fi
rm -rf "$old_toolchain" "$stage_root"

printf 'Bootstrapped PowerPC toolchain: %s/bin/%s-\n' \
    "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
