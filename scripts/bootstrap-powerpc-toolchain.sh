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
TOOLCHAIN_PKG_CONFIG="${TOOLCHAIN_PKG_CONFIG:-false}"
TOOLCHAIN_CONFIG_SHELL="${TOOLCHAIN_CONFIG_SHELL:-${CONFIG_SHELL:-/bin/bash}}"
TOOLCHAIN_BUILD_TRIPLET="${POWERPC_TOOLCHAIN_BUILD:-}"
TOOLCHAIN_HOST_TRIPLET="${POWERPC_TOOLCHAIN_HOST:-}"
TOOLCHAIN_HOST_CFLAGS="${TOOLCHAIN_HOST_CFLAGS:-}"
TOOLCHAIN_HOST_CXXFLAGS="${TOOLCHAIN_HOST_CXXFLAGS:-}"
TOOLCHAIN_HOST_CPPFLAGS="${TOOLCHAIN_HOST_CPPFLAGS:-}"
TOOLCHAIN_HOST_LDFLAGS="${TOOLCHAIN_HOST_LDFLAGS:-}"
MAKE_CMD="${MAKE_CMD:-${MAKE:-make}}"
JOBS="${JOBS:-1}"
stage_root=""
temporary_download=""
bootstrap_stage="initialization"

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

for build_path in "$SOURCE_DIR" "$TOOLCHAIN_DIR" "$TOOLCHAIN_WORK_DIR"; do
    case "$build_path" in
        *[' ':]*)
            printf 'error: toolchain source and build paths cannot contain spaces or colons\n' >&2
            exit 1
            ;;
    esac
done

if [[ ! -x "$TOOLCHAIN_CONFIG_SHELL" ]]; then
    printf 'error: toolchain CONFIG_SHELL is not executable: %s\n' \
        "$TOOLCHAIN_CONFIG_SHELL" >&2
    exit 1
fi

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

set_command()
{
    local command_string="$1"

    case "$command_string" in
        *';'*|*'|'*|*'&'*|*'<'*|*'>'*)
            printf 'error: compiler commands may not contain shell operators: %s\n' \
                "$command_string" >&2
            exit 1
            ;;
    esac

    COMMAND_ARRAY=()
    read -r -a COMMAND_ARRAY <<< "$command_string"
    if [[ "${#COMMAND_ARRAY[@]}" -eq 0 ]] ||
       ! command -v "${COMMAND_ARRAY[0]}" >/dev/null 2>&1; then
        printf 'error: compiler command is not executable: %s\n' \
            "$command_string" >&2
        exit 1
    fi
}

compiler_dumpmachine()
{
    local command_string="$1"
    local result

    set_command "$command_string"
    result="$("${COMMAND_ARRAY[@]}" -dumpmachine 2>/dev/null || true)"
    printf '%s\n' "$result" | sed -n '1p'
}

normalize_apple_silicon_triplet()
{
    case "$1" in
        arm64-apple-darwin*) printf 'aarch64-apple-darwin%s\n' "${1#arm64-apple-darwin}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

if [[ -z "$TOOLCHAIN_BUILD_TRIPLET" ]]; then
    TOOLCHAIN_BUILD_TRIPLET="$(compiler_dumpmachine "$TOOLCHAIN_HOST_CC")"
fi
if [[ -z "$TOOLCHAIN_BUILD_TRIPLET" ]]; then
    printf 'error: could not determine the build-machine triplet\n' >&2
    exit 1
fi
TOOLCHAIN_BUILD_TRIPLET="$(normalize_apple_silicon_triplet "$TOOLCHAIN_BUILD_TRIPLET")"
TOOLCHAIN_HOST_TRIPLET="${TOOLCHAIN_HOST_TRIPLET:-$TOOLCHAIN_BUILD_TRIPLET}"
TOOLCHAIN_HOST_TRIPLET="$(normalize_apple_silicon_triplet "$TOOLCHAIN_HOST_TRIPLET")"

if [[ "$(uname -s)" == "Darwin" ]]; then
    case "$(uname -m):$TOOLCHAIN_BUILD_TRIPLET:$TOOLCHAIN_HOST_TRIPLET" in
        arm64:aarch64-apple-darwin*:aarch64-apple-darwin*|\
        aarch64:aarch64-apple-darwin*:aarch64-apple-darwin*|\
        x86_64:x86_64-apple-darwin*:x86_64-apple-darwin*) ;;
        *)
            printf '%s\n' \
                'error: Darwin toolchain triplets do not match the running process.' \
                "process: $(uname -m)" \
                "build:   $TOOLCHAIN_BUILD_TRIPLET" \
                "host:    $TOOLCHAIN_HOST_TRIPLET" >&2
            exit 1
            ;;
    esac

    for required in xcrun sw_vers; do
        if ! command -v "$required" >/dev/null 2>&1; then
            printf 'error: required Apple tool is missing: %s\n' "$required" >&2
            exit 1
        fi
    done

    SDKROOT="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
    if [[ ! -d "$SDKROOT" ]]; then
        printf 'error: macOS SDK does not exist: %s\n' "$SDKROOT" >&2
        exit 1
    fi
    case "$SDKROOT" in
        *' '*)
            printf 'error: macOS SDK path contains spaces: %s\n' "$SDKROOT" >&2
            exit 1
            ;;
    esac

    MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion | awk -F. '{print $1 "." $2}')}"
    case "$(uname -m)" in
        arm64|aarch64) toolchain_darwin_arch=arm64 ;;
        x86_64) toolchain_darwin_arch=x86_64 ;;
    esac
    toolchain_darwin_flags="-arch $toolchain_darwin_arch -isysroot $SDKROOT -mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
    TOOLCHAIN_HOST_CFLAGS="${TOOLCHAIN_HOST_CFLAGS:-$toolchain_darwin_flags}"
    TOOLCHAIN_HOST_CXXFLAGS="${TOOLCHAIN_HOST_CXXFLAGS:-$toolchain_darwin_flags}"
    TOOLCHAIN_HOST_LDFLAGS="${TOOLCHAIN_HOST_LDFLAGS:-$toolchain_darwin_flags}"
fi

binutils_tools=(as ar ld nm objcopy objdump readelf strip ranlib)
powerpc_tools=(gcc "${binutils_tools[@]}")

binutils_is_usable()
{
    local prefix_dir="$1"
    local tool

    for tool in "${binutils_tools[@]}"; do
        [[ -x "$prefix_dir/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
    done
}

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
BOOTSTRAP_SCHEMA=4
BUILD_SYSTEM=$(uname -srm)
BUILD_PROCESS_ARCH=$(uname -m)
ROSETTA_TRANSLATED=$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')
BUILD_TRIPLET=$TOOLCHAIN_BUILD_TRIPLET
HOST_TRIPLET=$TOOLCHAIN_HOST_TRIPLET
TARGET=$TOOLCHAIN_TARGET
BINUTILS_VERSION=$BINUTILS_VERSION
BINUTILS_SHA256=$BINUTILS_SHA256
GCC_VERSION=$GCC_VERSION
GCC_SHA256=$GCC_SHA256
HOST_CC=$TOOLCHAIN_HOST_CC
HOST_CXX=$TOOLCHAIN_HOST_CXX
HOST_CFLAGS=$TOOLCHAIN_HOST_CFLAGS
HOST_CXXFLAGS=$TOOLCHAIN_HOST_CXXFLAGS
HOST_CPPFLAGS=$TOOLCHAIN_HOST_CPPFLAGS
HOST_LDFLAGS=$TOOLCHAIN_HOST_LDFLAGS
CONFIG_SHELL=$TOOLCHAIN_CONFIG_SHELL
PKG_CONFIG=$TOOLCHAIN_PKG_CONFIG
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
report_failure()
{
    local status=$?

    printf 'error: PowerPC toolchain bootstrap failed during %s (status %s)\n' \
        "$bootstrap_stage" "$status" >&2
    case "$bootstrap_stage" in
        *host*|*Darwin*)
            printf '%s\n' \
                "build triplet: $TOOLCHAIN_BUILD_TRIPLET" \
                "host triplet:  $TOOLCHAIN_HOST_TRIPLET" \
                "host CC:       $TOOLCHAIN_HOST_CC" \
                "host CXX:      $TOOLCHAIN_HOST_CXX" >&2
            ;;
        *binutils*)
            printf 'inspect binutils logs under: %s\n' \
                "$TOOLCHAIN_WORK_DIR/build-binutils-$BINUTILS_VERSION" >&2
            ;;
        *GCC*|*gcc*)
            printf 'inspect GCC logs under: %s\n' \
                "$TOOLCHAIN_WORK_DIR/build-gcc-$GCC_VERSION" >&2
            ;;
    esac
    return "$status"
}
trap report_failure ERR
trap cleanup EXIT

split_flags()
{
    FLAG_ARRAY=()
    if [[ -n "$1" ]]; then
        read -r -a FLAG_ARRAY <<< "$1"
    fi
}

validate_host_compilers()
{
    local probe_dir="$TOOLCHAIN_WORK_DIR/host-probe"
    local expected_arch=""
    local arches

    rm -rf "$probe_dir"
    mkdir -p "$probe_dir"
    cat > "$probe_dir/host.c" <<'SOURCE'
int main(void) { return 0; }
SOURCE
    cat > "$probe_dir/host.cc" <<'SOURCE'
static_assert(__cplusplus >= 201103L, "GCC 14 requires a C++11 host compiler");
int main() { return 0; }
SOURCE

    split_flags "$TOOLCHAIN_HOST_CPPFLAGS"
    local cpp_flags=("${FLAG_ARRAY[@]}")
    split_flags "$TOOLCHAIN_HOST_CFLAGS"
    local c_flags=("${FLAG_ARRAY[@]}")
    split_flags "$TOOLCHAIN_HOST_CXXFLAGS"
    local cxx_flags=("${FLAG_ARRAY[@]}")
    split_flags "$TOOLCHAIN_HOST_LDFLAGS"
    local ld_flags=("${FLAG_ARRAY[@]}")

    set_command "$TOOLCHAIN_HOST_CC"
    local cc_command=("${COMMAND_ARRAY[@]}")
    "${cc_command[@]}" "${cpp_flags[@]}" "${c_flags[@]}" \
        "$probe_dir/host.c" -o "$probe_dir/host-c" "${ld_flags[@]}"

    set_command "$TOOLCHAIN_HOST_CXX"
    local cxx_command=("${COMMAND_ARRAY[@]}")
    "${cxx_command[@]}" "${cpp_flags[@]}" "${cxx_flags[@]}" \
        "$probe_dir/host.cc" -o "$probe_dir/host-cxx" "${ld_flags[@]}"

    if [[ "$(uname -s)" == "Darwin" ]]; then
        case "$TOOLCHAIN_HOST_TRIPLET" in
            aarch64-apple-darwin*) expected_arch=arm64 ;;
            x86_64-apple-darwin*) expected_arch=x86_64 ;;
        esac
        for output in "$probe_dir/host-c" "$probe_dir/host-cxx"; do
            arches="$(xcrun lipo -archs "$output" 2>/dev/null || true)"
            case " $arches " in
                *" $expected_arch "*) ;;
                *)
                    printf 'error: host compiler produced %s, expected %s: %s\n' \
                        "${arches:-unknown architecture}" "$expected_arch" "$output" >&2
                    return 1
                    ;;
            esac
        done
    fi
}

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

validate_source_triplets()
{
    local source_dir="$1"
    local project="$2"
    local build_canonical
    local host_canonical

    build_canonical="$("$source_dir/config.sub" "$TOOLCHAIN_BUILD_TRIPLET")"
    host_canonical="$("$source_dir/config.sub" "$TOOLCHAIN_HOST_TRIPLET")"
    if [[ "$build_canonical" != "$TOOLCHAIN_BUILD_TRIPLET" ||
          "$host_canonical" != "$TOOLCHAIN_HOST_TRIPLET" ]]; then
        printf '%s\n' \
            "error: $project canonicalized the requested machine identities differently." \
            "requested build: $TOOLCHAIN_BUILD_TRIPLET" \
            "canonical build: $build_canonical" \
            "requested host:  $TOOLCHAIN_HOST_TRIPLET" \
            "canonical host:  $host_canonical" >&2
        return 1
    fi
}

common_host_env=(
    -u CFLAGS_FOR_TARGET
    -u CXXFLAGS_FOR_TARGET
    -u CPPFLAGS_FOR_TARGET
    -u LDFLAGS_FOR_TARGET
    -u PKG_CONFIG_PATH
    -u PKG_CONFIG_LIBDIR
    -u PKG_CONFIG_SYSROOT_DIR
    "CONFIG_SHELL=$TOOLCHAIN_CONFIG_SHELL"
    "SHELL=$TOOLCHAIN_CONFIG_SHELL"
    "PKG_CONFIG=$TOOLCHAIN_PKG_CONFIG"
    "CC=$TOOLCHAIN_HOST_CC"
    "CXX=$TOOLCHAIN_HOST_CXX"
    "CFLAGS=$TOOLCHAIN_HOST_CFLAGS"
    "CXXFLAGS=$TOOLCHAIN_HOST_CXXFLAGS"
    "CPPFLAGS=$TOOLCHAIN_HOST_CPPFLAGS"
    "LDFLAGS=$TOOLCHAIN_HOST_LDFLAGS"
)

bootstrap_stage="validating host compiler and SDK"
validate_host_compilers

binutils_tar="$TOOLCHAIN_DOWNLOAD_DIR/$BINUTILS_ARCHIVE"
gcc_tar="$TOOLCHAIN_DOWNLOAD_DIR/$GCC_ARCHIVE"
binutils_src="$TOOLCHAIN_WORK_DIR/binutils-$BINUTILS_VERSION"
gcc_src="$TOOLCHAIN_WORK_DIR/gcc-$GCC_VERSION"
binutils_build="$TOOLCHAIN_WORK_DIR/build-binutils-$BINUTILS_VERSION"
gcc_build="$TOOLCHAIN_WORK_DIR/build-gcc-$GCC_VERSION"

bootstrap_stage="downloading and verifying binutils"
download_and_verify "$BINUTILS_URL" "$binutils_tar" "$BINUTILS_SHA256"
bootstrap_stage="extracting binutils"
extract_archive "$binutils_tar" "$binutils_src"
validate_source_triplets "$binutils_src" binutils

stage_root="$TOOLCHAIN_WORK_DIR/install-root.$$"
staged_toolchain="$stage_root$TOOLCHAIN_DIR"
rm -rf "$stage_root"
mkdir -p "$stage_root" "$(dirname "$TOOLCHAIN_DIR")"

bootstrap_stage="configuring and building binutils"
rm -rf "$binutils_build"
mkdir -p "$binutils_build"
(
    cd "$binutils_build"
    env "${common_host_env[@]}" \
        "$binutils_src/configure" \
        --build="$TOOLCHAIN_BUILD_TRIPLET" \
        --host="$TOOLCHAIN_HOST_TRIPLET" \
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
        --enable-static \
        --without-zstd
    env "${common_host_env[@]}" \
        "$MAKE_CMD" -j"$JOBS" MAKEINFO=true
    env "${common_host_env[@]}" \
        "$MAKE_CMD" MAKEINFO=true DESTDIR="$stage_root" install
)

bootstrap_stage="validating staged binutils"
if ! binutils_is_usable "$staged_toolchain"; then
    printf 'error: staged PowerPC binutils installation is incomplete\n' >&2
    exit 1
fi
binutils_smoke_source="$TOOLCHAIN_WORK_DIR/binutils-smoke.s"
binutils_smoke_object="$TOOLCHAIN_WORK_DIR/binutils-smoke.o"
binutils_smoke_linked="$TOOLCHAIN_WORK_DIR/binutils-smoke-linked.o"
cat > "$binutils_smoke_source" <<'ASSEMBLY'
.text
.globl whp_binutils_smoke
whp_binutils_smoke:
    nop
ASSEMBLY
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-as" \
    -o "$binutils_smoke_object" "$binutils_smoke_source"
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-ld" \
    -r -o "$binutils_smoke_linked" "$binutils_smoke_object"
if ! "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" \
     -h "$binutils_smoke_linked" | grep -q 'Machine:.*PowerPC'; then
    printf 'error: staged binutils produced the wrong object architecture\n' >&2
    exit 1
fi
rm -f "$binutils_smoke_source" "$binutils_smoke_object" \
    "$binutils_smoke_linked"

bootstrap_stage="downloading and verifying GCC"
download_and_verify "$GCC_URL" "$gcc_tar" "$GCC_SHA256"
bootstrap_stage="extracting GCC"
extract_archive "$gcc_tar" "$gcc_src"
validate_source_triplets "$gcc_src" GCC

if [[ "$TOOLCHAIN_HOST_TRIPLET" == aarch64-apple-darwin* ]] &&
   ! grep -Eq 'aarch64[^|]*-\*-darwin|aarch64\*-\*-darwin' \
       "$gcc_src/gcc/config.host"; then
    printf 'error: GCC %s lacks aarch64-Darwin cross-compiler host support\n' \
        "$GCC_VERSION" >&2
    exit 1
fi

# GCC 14's helper still names an HTTP endpoint. Use HTTPS while retaining
# the release-provided prerequisite checksums and pinned dependency versions.
bootstrap_stage="preparing GCC prerequisites"
sed -i.bak \
    "s|base_url='http://gcc.gnu.org/pub/gcc/infrastructure/'|base_url='https://gcc.gnu.org/pub/gcc/infrastructure/'|" \
    "$gcc_src/contrib/download_prerequisites"
rm -f "$gcc_src/contrib/download_prerequisites.bak"
sed -i.bak '/^[[:space:]]*echo "${gettext}"[[:space:]]*$/d' \
    "$gcc_src/contrib/download_prerequisites"
rm -f "$gcc_src/contrib/download_prerequisites.bak"
(
    cd "$gcc_src"
    CONFIG_SHELL="$TOOLCHAIN_CONFIG_SHELL" SHELL="$TOOLCHAIN_CONFIG_SHELL" \
        ./contrib/download_prerequisites --no-isl
)

target_tool_env=(
    "AR_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-ar"
    "AS_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-as"
    "LD_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-ld"
    "NM_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-nm"
    "OBJCOPY_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-objcopy"
    "OBJDUMP_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-objdump"
    "RANLIB_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-ranlib"
    "READELF_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf"
    "STRIP_FOR_TARGET=$staged_toolchain/bin/${TOOLCHAIN_TARGET}-strip"
)

bootstrap_stage="configuring and building GCC"
rm -rf "$gcc_build"
mkdir -p "$gcc_build"
(
    cd "$gcc_build"
    export PATH="$staged_toolchain/bin:$PATH"
    env "${common_host_env[@]}" "${target_tool_env[@]}" \
        "$gcc_src/configure" \
        --build="$TOOLCHAIN_BUILD_TRIPLET" \
        --host="$TOOLCHAIN_HOST_TRIPLET" \
        --target="$TOOLCHAIN_TARGET" \
        --prefix="$TOOLCHAIN_DIR" \
        --with-cpu=604 \
        --with-endian=big \
        --with-gnu-as \
        --with-gnu-ld \
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
        --disable-lto \
        --disable-multilib \
        --disable-nls \
        --disable-shared \
        --disable-threads \
        --disable-werror \
        --enable-languages=c
    env "${common_host_env[@]}" "${target_tool_env[@]}" \
        STAGE1_CFLAGS="$TOOLCHAIN_HOST_CFLAGS" \
        "$MAKE_CMD" -j"$JOBS" MAKEINFO=true all-gcc
    env "${common_host_env[@]}" "${target_tool_env[@]}" \
        "$MAKE_CMD" MAKEINFO=true DESTDIR="$stage_root" install-gcc
)

bootstrap_stage="validating complete PowerPC toolchain"
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

bootstrap_stage="completed"
printf 'Bootstrapped PowerPC toolchain: %s/bin/%s-\n' \
    "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
