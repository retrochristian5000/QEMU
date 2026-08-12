#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
toolchain_root="$(dirname "$TOOLCHAIN_DIR")"
TOOLCHAIN_WORK_DIR="$toolchain_root/toolchain-work/$TOOLCHAIN_TARGET"
TOOLCHAIN_DOWNLOAD_DIR="$toolchain_root/toolchain-downloads"
TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
TOOLCHAIN_HOST_CC="${CC_FOR_BUILD:-${CC:-cc}}"
TOOLCHAIN_HOST_CXX="${CXX_FOR_BUILD:-${CXX:-c++}}"
TOOLCHAIN_HOST_AR="${TOOLCHAIN_HOST_AR:-}"
TOOLCHAIN_HOST_NM="${TOOLCHAIN_HOST_NM:-}"
TOOLCHAIN_HOST_RANLIB="${TOOLCHAIN_HOST_RANLIB:-}"
TOOLCHAIN_HOST_STRIP="${TOOLCHAIN_HOST_STRIP:-}"
TOOLCHAIN_PKG_CONFIG="${TOOLCHAIN_PKG_CONFIG:-false}"
config_shell="${CONFIG_SHELL:-/bin/bash}"
TOOLCHAIN_BUILD_TRIPLET="${POWERPC_TOOLCHAIN_BUILD:-}"
TOOLCHAIN_HOST_TRIPLET="${POWERPC_TOOLCHAIN_HOST:-}"
TOOLCHAIN_HOST_CFLAGS="${TOOLCHAIN_HOST_CFLAGS:-}"
TOOLCHAIN_HOST_CXXFLAGS="${TOOLCHAIN_HOST_CXXFLAGS:-}"
TOOLCHAIN_HOST_CPPFLAGS="${TOOLCHAIN_HOST_CPPFLAGS:-}"
TOOLCHAIN_HOST_LDFLAGS="${TOOLCHAIN_HOST_LDFLAGS:-}"
toolchain_cc_for_build="$TOOLCHAIN_HOST_CC"
toolchain_cxx_for_build="$TOOLCHAIN_HOST_CXX"
MAKE_CMD="${MAKE_CMD:-${MAKE:-make}}"
JOBS="${JOBS:-1}"
stage_root=""
temporary_download=""
bootstrap_stage="initialization"
host_configure_args=()
host_zlib=bundled

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

if [[ ! -x "$config_shell" ]]; then
    printf 'error: toolchain CONFIG_SHELL is not executable: %s\n' \
        "$config_shell" >&2
    exit 1
fi

if ! "$MAKE_CMD" --version 2>/dev/null | head -n 1 | grep -q 'GNU Make'; then
    printf 'error: PowerPC toolchain bootstrap requires GNU Make\n' >&2
    printf 'set MAKE_CMD to gmake or another GNU Make executable\n' >&2
    exit 1
fi

for required in tar sed grep awk bzip2 gzip perl ln mkdir mv rm; do
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
        ''|*';'*|*'|'*|*'&'*|*'<'*|*'>')
            printf 'error: command may not contain shell operators: %s\n' \
                "$command_string" >&2
            return 1
            ;;
    esac

    COMMAND_ARRAY=()
    read -r -a COMMAND_ARRAY <<< "$command_string"
    if [[ "${#COMMAND_ARRAY[@]}" -eq 0 ]] ||
       ! command -v "${COMMAND_ARRAY[0]}" >/dev/null 2>&1; then
        printf 'error: command is not executable: %s\n' "$command_string" >&2
        return 1
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

compiler_family()
{
    local command_string="$1"
    local macros

    set_command "$command_string"
    macros="$("${COMMAND_ARRAY[@]}" -dM -E -x c /dev/null 2>/dev/null || true)"
    if grep -q '^#define __clang__ ' <<< "$macros"; then
        printf 'clang\n'
    elif grep -q '^#define __GNUC__ ' <<< "$macros"; then
        printf 'gcc\n'
    else
        printf 'unknown\n'
    fi
}

normalize_apple_silicon_triplet()
{
    case "$1" in
        arm64-apple-darwin*) printf 'aarch64-apple-darwin%s\n' "${1#arm64-apple-darwin}" ;;
        *) printf '%s\n' "$1" ;;
    esac
}

resolve_host_tool()
{
    local variable="$1"
    local program="$2"
    local value="${!variable:-}"

    if [[ -z "$value" ]]; then
        if [[ "$(uname -s)" == Darwin ]]; then
            value="$(xcrun --sdk macosx --find "$program" 2>/dev/null || true)"
        else
            value="$(command -v "$program" 2>/dev/null || true)"
        fi
    fi
    if [[ -z "$value" ]]; then
        printf 'error: host %s tool could not be found\n' "$program" >&2
        return 1
    fi
    set_command "$value"
    printf -v "$variable" '%s' "$value"
    export "$variable"
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

# This bootstrap builds tools that run on the current machine.  A build/host
# mismatch is a Canadian cross and needs a separate compiler and executable
# validation path; silently treating it as an ordinary cross compiler is unsafe.
if [[ "$TOOLCHAIN_BUILD_TRIPLET" != "$TOOLCHAIN_HOST_TRIPLET" ]]; then
    printf '%s\n' \
        'error: Canadian-cross build/host combinations are not supported here.' \
        "build: $TOOLCHAIN_BUILD_TRIPLET" \
        "host:  $TOOLCHAIN_HOST_TRIPLET" \
        'Build the host compiler separately, then add an explicit Canadian-cross stage.' >&2
    exit 1
fi

if [[ "$(uname -s)" == Darwin ]]; then
    for required in xcrun sw_vers; do
        if ! command -v "$required" >/dev/null 2>&1; then
            printf 'error: required Apple tool is missing: %s\n' "$required" >&2
            exit 1
        fi
    done

    case "$(uname -m):$TOOLCHAIN_BUILD_TRIPLET" in
        arm64:aarch64-apple-darwin*|aarch64:aarch64-apple-darwin*|\
        x86_64:x86_64-apple-darwin*) ;;
        *)
            printf '%s\n' \
                'error: Darwin build triplet does not match the running process.' \
                "process: $(uname -m)" \
                "build:   $TOOLCHAIN_BUILD_TRIPLET" >&2
            exit 1
            ;;
    esac

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
    toolchain_host_cc_family="$(compiler_family "$TOOLCHAIN_HOST_CC")"
    toolchain_host_cxx_family="$(compiler_family "$TOOLCHAIN_HOST_CXX")"
    if [[ "$toolchain_host_cc_family" == unknown ||
          "$toolchain_host_cxx_family" == unknown ||
          "$toolchain_host_cc_family" != "$toolchain_host_cxx_family" ]]; then
        printf '%s\n' \
            'error: Darwin host C and C++ compilers must be a matching GCC or Clang pair.' \
            "CC:  $TOOLCHAIN_HOST_CC ($toolchain_host_cc_family)" \
            "CXX: $TOOLCHAIN_HOST_CXX ($toolchain_host_cxx_family)" >&2
        exit 1
    fi
    case "$(uname -m)" in
        arm64|aarch64) toolchain_darwin_arch=arm64 ;;
        x86_64) toolchain_darwin_arch=x86_64 ;;
    esac
    toolchain_darwin_flags="-isysroot $SDKROOT -mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
    if [[ "$toolchain_host_cc_family" == clang ]]; then
        toolchain_darwin_flags="-arch $toolchain_darwin_arch $toolchain_darwin_flags"
    fi
    TOOLCHAIN_HOST_CFLAGS="${TOOLCHAIN_HOST_CFLAGS:-$toolchain_darwin_flags}"
    TOOLCHAIN_HOST_CXXFLAGS="${TOOLCHAIN_HOST_CXXFLAGS:-$toolchain_darwin_flags}"
    TOOLCHAIN_HOST_CPPFLAGS="${TOOLCHAIN_HOST_CPPFLAGS:-$toolchain_darwin_flags}"
    TOOLCHAIN_HOST_LDFLAGS="${TOOLCHAIN_HOST_LDFLAGS:-$toolchain_darwin_flags}"
    # GCC prerequisites such as GMP probe CC_FOR_BUILD without adding CFLAGS
    # or LDFLAGS.  Keep the SDK policy on the command for those nested probes.
    toolchain_cc_for_build="$TOOLCHAIN_HOST_CC $toolchain_darwin_flags"
    toolchain_cxx_for_build="$TOOLCHAIN_HOST_CXX $toolchain_darwin_flags"

    # Binutils 2.44 and GCC 14.2 bundle zlib 1.1.4, whose legacy TARGET_OS_MAC
    # handling defines fdopen before current Apple SDK headers declare it.  Link
    # the host tools to the SDK's libz instead of patching release source code.
    host_configure_args+=(--with-system-zlib)
    host_zlib=system
fi

resolve_host_tool TOOLCHAIN_HOST_AR ar
resolve_host_tool TOOLCHAIN_HOST_NM nm
resolve_host_tool TOOLCHAIN_HOST_RANLIB ranlib
resolve_host_tool TOOLCHAIN_HOST_STRIP strip

binutils_tools=(as ar ld nm objcopy objdump readelf strip ranlib)
powerpc_tools=(gcc "${binutils_tools[@]}")

binutils_is_usable()
{
    local prefix_dir="$1"
    local tool

    for tool in "${binutils_tools[@]}"; do
        [[ -x "$prefix_dir/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
        [[ -e "$prefix_dir/$TOOLCHAIN_TARGET/bin/$tool" ]] || return 1
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
BOOTSTRAP_SCHEMA=7
BUILD_SYSTEM=$(uname -srm)
BUILD_PROCESS_ARCH=$(uname -m)
ROSETTA_TRANSLATED=$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')
BUILD_TRIPLET=$TOOLCHAIN_BUILD_TRIPLET
HOST_TRIPLET=$TOOLCHAIN_HOST_TRIPLET
TARGET=$TOOLCHAIN_TARGET
BINUTILS_VERSION=$BINUTILS_VERSION
BINUTILS_SHA256=$BINUTILS_SHA256
HOST_ZLIB=$host_zlib
GCC_VERSION=$GCC_VERSION
GCC_SHA256=$GCC_SHA256
HOST_CC=$TOOLCHAIN_HOST_CC
HOST_CXX=$TOOLCHAIN_HOST_CXX
HOST_AR=$TOOLCHAIN_HOST_AR
HOST_NM=$TOOLCHAIN_HOST_NM
HOST_RANLIB=$TOOLCHAIN_HOST_RANLIB
HOST_STRIP=$TOOLCHAIN_HOST_STRIP
HOST_CFLAGS=$TOOLCHAIN_HOST_CFLAGS
HOST_CXXFLAGS=$TOOLCHAIN_HOST_CXXFLAGS
HOST_CPPFLAGS=$TOOLCHAIN_HOST_CPPFLAGS
HOST_LDFLAGS=$TOOLCHAIN_HOST_LDFLAGS
CONFIG_SHELL=$config_shell
PKG_CONFIG=$TOOLCHAIN_PKG_CONFIG
TARGET_TOOL_LAYOUT=$TOOLCHAIN_TARGET/bin
TARGET_SYSROOT=$TOOLCHAIN_TARGET/sys-root
MARKER
)"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 ]] &&
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

# Bash 3.2 treats an empty array as unset when nounset is active.  Keep every
# optional flag-array copy and expansion guarded with the parameter + form.

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
    local cpp_flags=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "$TOOLCHAIN_HOST_CFLAGS"
    local c_flags=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "$TOOLCHAIN_HOST_CXXFLAGS"
    local cxx_flags=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})
    split_flags "$TOOLCHAIN_HOST_LDFLAGS"
    local ld_flags=(${FLAG_ARRAY[@]+"${FLAG_ARRAY[@]}"})

    set_command "$TOOLCHAIN_HOST_CC"
    local cc_command=("${COMMAND_ARRAY[@]}")
    "${cc_command[@]}" \
        ${cpp_flags[@]+"${cpp_flags[@]}"} \
        ${c_flags[@]+"${c_flags[@]}"} \
        "$probe_dir/host.c" -o "$probe_dir/host-c" \
        ${ld_flags[@]+"${ld_flags[@]}"}

    set_command "$TOOLCHAIN_HOST_CXX"
    local cxx_command=("${COMMAND_ARRAY[@]}")
    "${cxx_command[@]}" \
        ${cpp_flags[@]+"${cpp_flags[@]}"} \
        ${cxx_flags[@]+"${cxx_flags[@]}"} \
        "$probe_dir/host.cc" -o "$probe_dir/host-cxx" \
        ${ld_flags[@]+"${ld_flags[@]}"}

    if [[ "$(uname -s)" == Darwin ]]; then
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
    local target_canonical

    build_canonical="$("$source_dir/config.sub" "$TOOLCHAIN_BUILD_TRIPLET")"
    host_canonical="$("$source_dir/config.sub" "$TOOLCHAIN_HOST_TRIPLET")"
    target_canonical="$("$source_dir/config.sub" "$TOOLCHAIN_TARGET")"
    if [[ "$build_canonical" != "$TOOLCHAIN_BUILD_TRIPLET" ||
          "$host_canonical" != "$TOOLCHAIN_HOST_TRIPLET" ]]; then
        printf '%s\n' \
            "error: $project canonicalized the requested machine identities differently." \
            "requested build:  $TOOLCHAIN_BUILD_TRIPLET" \
            "canonical build:  $build_canonical" \
            "requested host:   $TOOLCHAIN_HOST_TRIPLET" \
            "canonical host:   $host_canonical" \
            "requested target: $TOOLCHAIN_TARGET" \
            "canonical target: $target_canonical" >&2
        return 1
    fi

    # GNU config.sub inserts an omitted vendor into short target aliases; for
    # example, powerpc-elf becomes powerpc-unknown-elf.  Configure deliberately
    # retains the original target alias for the installed powerpc-elf-* program
    # prefix, so successful target canonicalization is the validation here.
    printf '%s target: %s (canonical %s)\n' \
        "$project" "$TOOLCHAIN_TARGET" "$target_canonical"
}

common_host_env=(
    -u CC_FOR_TARGET -u CXX_FOR_TARGET -u GCC_FOR_TARGET -u GXX_FOR_TARGET
    -u AR_FOR_TARGET -u AS_FOR_TARGET -u LD_FOR_TARGET -u NM_FOR_TARGET
    -u OBJCOPY_FOR_TARGET -u OBJDUMP_FOR_TARGET -u RANLIB_FOR_TARGET
    -u READELF_FOR_TARGET -u STRIP_FOR_TARGET
    -u CFLAGS_FOR_TARGET -u CXXFLAGS_FOR_TARGET
    -u CPPFLAGS_FOR_TARGET -u LDFLAGS_FOR_TARGET
    -u CPATH -u C_INCLUDE_PATH -u CPLUS_INCLUDE_PATH -u OBJC_INCLUDE_PATH
    -u COMPILER_PATH -u GCC_EXEC_PREFIX -u LIBRARY_PATH
    -u DYLD_LIBRARY_PATH -u DYLD_FALLBACK_LIBRARY_PATH
    -u PKG_CONFIG_PATH -u PKG_CONFIG_LIBDIR -u PKG_CONFIG_SYSROOT_DIR
    "CONFIG_SHELL=$config_shell"
    "SHELL=$config_shell"
    "PKG_CONFIG=$TOOLCHAIN_PKG_CONFIG"
    "CC=$TOOLCHAIN_HOST_CC"
    "CXX=$TOOLCHAIN_HOST_CXX"
    "CC_FOR_BUILD=$toolchain_cc_for_build"
    "CXX_FOR_BUILD=$toolchain_cxx_for_build"
    "AR=$TOOLCHAIN_HOST_AR"
    "NM=$TOOLCHAIN_HOST_NM"
    "RANLIB=$TOOLCHAIN_HOST_RANLIB"
    "STRIP=$TOOLCHAIN_HOST_STRIP"
    "AR_FOR_BUILD=$TOOLCHAIN_HOST_AR"
    "NM_FOR_BUILD=$TOOLCHAIN_HOST_NM"
    "RANLIB_FOR_BUILD=$TOOLCHAIN_HOST_RANLIB"
    "STRIP_FOR_BUILD=$TOOLCHAIN_HOST_STRIP"
    "CFLAGS=$TOOLCHAIN_HOST_CFLAGS"
    "CXXFLAGS=$TOOLCHAIN_HOST_CXXFLAGS"
    "CPPFLAGS=$TOOLCHAIN_HOST_CPPFLAGS"
    "LDFLAGS=$TOOLCHAIN_HOST_LDFLAGS"
)

prepare_target_tool_layout()
{
    local prefix_dir="$1"
    local target_bin="$prefix_dir/$TOOLCHAIN_TARGET/bin"
    local tool

    mkdir -p "$target_bin" "$prefix_dir/$TOOLCHAIN_TARGET/sys-root"
    for tool in "${binutils_tools[@]}"; do
        rm -f "$target_bin/$tool"
        ln -s "../../bin/${TOOLCHAIN_TARGET}-${tool}" "$target_bin/$tool"
    done
}

validate_binutils_output()
{
    local prefix_dir="$1"
    local smoke_dir="$TOOLCHAIN_WORK_DIR/binutils-smoke"
    local object="$smoke_dir/smoke.o"
    local linked="$smoke_dir/linked.o"
    local archive="$smoke_dir/libsmoke.a"

    rm -rf "$smoke_dir"
    mkdir -p "$smoke_dir"
    cat > "$smoke_dir/smoke.s" <<'ASSEMBLY'
.text
.globl whp_binutils_smoke
whp_binutils_smoke:
    nop
ASSEMBLY

    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-as" -o "$object" "$smoke_dir/smoke.s"
    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-ld" -r -o "$linked" "$object"
    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-ar" rc "$archive" "$object"
    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-ranlib" "$archive"
    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-nm" "$archive" >/dev/null

    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-readelf" -h "$linked" |
        grep -q 'Machine:.*PowerPC' || {
            printf 'error: staged binutils produced the wrong architecture\n' >&2
            return 1
        }
    "$prefix_dir/bin/${TOOLCHAIN_TARGET}-readelf" -h "$linked" |
        grep -q 'Data:.*big endian' || {
            printf 'error: staged binutils did not default to big-endian PowerPC\n' >&2
            return 1
        }
}

validate_final_toolchain()
{
    local prefix_dir="$1"
    local smoke_dir="$TOOLCHAIN_WORK_DIR/final-smoke"
    local gcc="$prefix_dir/bin/${TOOLCHAIN_TARGET}-gcc"
    local readelf="$prefix_dir/bin/${TOOLCHAIN_TARGET}-readelf"
    local safe_path=/usr/bin:/bin
    local sysroot

    rm -rf "$smoke_dir"
    mkdir -p "$smoke_dir"
    cat > "$smoke_dir/smoke.c" <<'SOURCE'
#if !defined(__powerpc__) && !defined(__POWERPC__) && !defined(__PPC__)
#error compiler is not targeting PowerPC
#endif
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
#error compiler does not default to big endian
#endif
int whp_powerpc_toolchain_smoke(void) { return 0; }
SOURCE

    env -u GCC_EXEC_PREFIX -u COMPILER_PATH -u LIBRARY_PATH \
        -u CPATH -u C_INCLUDE_PATH -u CPLUS_INCLUDE_PATH \
        PATH="$safe_path" \
        "$gcc" -m32 -mcpu=604 -msoft-float -ffreestanding \
        -c "$smoke_dir/smoke.c" -o "$smoke_dir/smoke.o" || return 1

    env -u GCC_EXEC_PREFIX -u COMPILER_PATH -u LIBRARY_PATH \
        PATH="$safe_path" \
        "$gcc" -m32 -mcpu=604 -msoft-float -nostdlib -Wl,-r \
        "$smoke_dir/smoke.o" -o "$smoke_dir/linked.o" || return 1

    "$readelf" -h "$smoke_dir/linked.o" |
        grep -q 'Machine:.*PowerPC' || {
            printf 'error: cross GCC produced the wrong architecture\n' >&2
            return 1
        }
    "$readelf" -h "$smoke_dir/linked.o" |
        grep -q 'Data:.*big endian' || {
            printf 'error: cross GCC did not default to big-endian PowerPC\n' >&2
            return 1
        }

    sysroot="$("$gcc" -print-sysroot)"
    case "$sysroot" in
        "$prefix_dir/$TOOLCHAIN_TARGET/sys-root"|\
        "$prefix_dir/$TOOLCHAIN_TARGET/sys-root/") ;;
        *)
            printf '%s\n' \
                'error: installed cross GCC reports an unexpected sysroot.' \
                "reported: ${sysroot:-<empty>}" \
                "expected: $prefix_dir/$TOOLCHAIN_TARGET/sys-root" >&2
            return 1
            ;;
    esac
}

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
        --with-sysroot \
        --disable-gdb \
        --disable-gdbserver \
        --disable-gprofng \
        --disable-gold \
        --disable-nls \
        --disable-shared \
        --disable-sim \
        --disable-werror \
        --enable-static \
        "${host_configure_args[@]}" \
        --without-zstd
    env "${common_host_env[@]}" \
        "$MAKE_CMD" -j"$JOBS" MAKEINFO=true
    env "${common_host_env[@]}" \
        "$MAKE_CMD" MAKEINFO=true DESTDIR="$stage_root" install
)

prepare_target_tool_layout "$staged_toolchain"

bootstrap_stage="validating staged binutils"
if ! binutils_is_usable "$staged_toolchain"; then
    printf 'error: staged PowerPC binutils installation is incomplete\n' >&2
    exit 1
fi
validate_binutils_output "$staged_toolchain"

bootstrap_stage="downloading and verifying GCC"
download_and_verify "$GCC_URL" "$gcc_tar" "$GCC_SHA256"
bootstrap_stage="extracting GCC"
extract_archive "$gcc_tar" "$gcc_src"
validate_source_triplets "$gcc_src" GCC

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
    CONFIG_SHELL="$config_shell" SHELL="$config_shell" \
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
        --with-build-time-tools="$staged_toolchain/$TOOLCHAIN_TARGET/bin" \
        --with-sysroot \
        "${host_configure_args[@]}" \
        --with-cpu=604 \
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
        "$MAKE_CMD" -j"$JOBS" MAKEINFO=true \
        "CC_FOR_BUILD=$toolchain_cc_for_build" \
        "CXX_FOR_BUILD=$toolchain_cxx_for_build" all-gcc
    env "${common_host_env[@]}" "${target_tool_env[@]}" \
        "$MAKE_CMD" MAKEINFO=true \
        "CC_FOR_BUILD=$toolchain_cc_for_build" \
        "CXX_FOR_BUILD=$toolchain_cxx_for_build" \
        DESTDIR="$stage_root" install-gcc
)

bootstrap_stage="validating complete staged PowerPC toolchain"
if ! toolchain_is_usable "$staged_toolchain"; then
    printf 'error: bootstrapped PowerPC toolchain is incomplete\n' >&2
    exit 1
fi

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

bootstrap_stage="validating installed PowerPC toolchain routing"
if ! validate_final_toolchain "$TOOLCHAIN_DIR"; then
    rm -rf "$TOOLCHAIN_DIR"
    [[ ! -e "$old_toolchain" ]] || mv "$old_toolchain" "$TOOLCHAIN_DIR"
    exit 1
fi

rm -rf "$old_toolchain" "$stage_root"
stage_root=""
bootstrap_stage="completed"
printf 'Bootstrapped PowerPC toolchain: %s/bin/%s-\n' \
    "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
