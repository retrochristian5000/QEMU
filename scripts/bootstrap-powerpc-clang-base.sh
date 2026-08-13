#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
TOOLCHAIN_DOWNLOAD_DIR="${POWERPC_TOOLCHAIN_DOWNLOAD_DIR:-$SOURCE_DIR/build/toolchain-downloads}"
TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
TOOLCHAIN_HOST_CC="${TOOLCHAIN_HOST_CC:-${CC_FOR_BUILD:-${CC:-cc}}}"
TOOLCHAIN_HOST_CXX="${TOOLCHAIN_HOST_CXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
MAKE_CMD="${MAKE_CMD:-${MAKE:-make}}"
JOBS="${JOBS:-1}"

BINUTILS_VERSION="${POWERPC_BINUTILS_VERSION:-2.44}"
BINUTILS_ARCHIVE="binutils-${BINUTILS_VERSION}.tar.xz"
BINUTILS_URL="${POWERPC_BINUTILS_URL:-https://sourceware.org/pub/binutils/releases/$BINUTILS_ARCHIVE}"
BINUTILS_SHA256="${POWERPC_BINUTILS_SHA256:-ce2017e059d63e67ddb9240e9d4ec49c2893605035cd60e92ad53177f4377237}"

# Keep compiler source selection under WHP control. Standalone use follows the
# LLVM remote's default branch through HEAD; the QEMU orchestrator supplies the
# exact submodule gitlink commit so normal project builds remain reproducible.
LLVM_GIT_URL="${POWERPC_LLVM_GIT_URL:-https://github.com/retrochristian5000/LLVM.git}"
LLVM_GIT_REF="${POWERPC_LLVM_GIT_REF:-HEAD}"
LLVM_GIT_COMMIT="${POWERPC_LLVM_GIT_COMMIT:-}"
LLVM_GIT_OFFLINE="${POWERPC_LLVM_GIT_OFFLINE:-0}"
LLVM_SOURCE_DIR="${POWERPC_LLVM_SOURCE_DIR:-$TOOLCHAIN_WORK_DIR/llvm-source}"
LLVM_BUILD_DIR="${POWERPC_LLVM_BUILD_DIR:-$TOOLCHAIN_WORK_DIR/llvm-build}"

stage_root=""
temporary_download=""
bootstrap_stage="initialization"

case "$TOOLCHAIN_TARGET" in
    powerpc-elf) ;;
    *)
        printf 'error: the Clang migration lane currently supports only powerpc-elf\n' >&2
        exit 1
        ;;
esac
case "$TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac
case "$LLVM_GIT_OFFLINE" in
    0|1) ;;
    *)
        printf 'error: POWERPC_LLVM_GIT_OFFLINE must be 0 or 1\n' >&2
        exit 1
        ;;
esac

for build_path in "$SOURCE_DIR" "$TOOLCHAIN_DIR" "$TOOLCHAIN_WORK_DIR" \
                  "$TOOLCHAIN_DOWNLOAD_DIR" "$LLVM_SOURCE_DIR" "$LLVM_BUILD_DIR"; do
    case "$build_path" in
        *[' ':]*)
            printf 'error: PowerPC Clang build paths cannot contain spaces or colons: %s\n' \
                "$build_path" >&2
            exit 1
            ;;
    esac
done

for required in git cmake ninja tar sed grep awk bzip2 gzip perl ln mkdir mv rm; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: PowerPC Clang bootstrap dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done
if ! "$MAKE_CMD" --version 2>/dev/null | head -n 1 | grep -q 'GNU Make'; then
    printf 'error: PowerPC binutils bootstrap requires GNU Make\n' >&2
    printf 'set MAKE_CMD to gmake or another GNU Make executable\n' >&2
    exit 1
fi
if command -v curl >/dev/null 2>&1; then
    download_cmd=curl
elif command -v wget >/dev/null 2>&1; then
    download_cmd=wget
else
    printf 'error: curl or wget is required to download PowerPC binutils\n' >&2
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

case "$TOOLCHAIN_HOST_CC" in
    ''|*' '*|*$'\t'*|*';'*|*'|'*|*'&'*|*'<'*|*'>')
        printf 'error: LLVM bootstrap requires a single host C compiler executable: %s\n' \
            "$TOOLCHAIN_HOST_CC" >&2
        exit 1
        ;;
esac
case "$TOOLCHAIN_HOST_CXX" in
    ''|*' '*|*$'\t'*|*';'*|*'|'*|*'&'*|*'<'*|*'>')
        printf 'error: LLVM bootstrap requires a single host C++ compiler executable: %s\n' \
            "$TOOLCHAIN_HOST_CXX" >&2
        exit 1
        ;;
esac
if ! command -v "$TOOLCHAIN_HOST_CC" >/dev/null 2>&1; then
    printf 'error: host C compiler is not executable: %s\n' "$TOOLCHAIN_HOST_CC" >&2
    exit 1
fi
if ! command -v "$TOOLCHAIN_HOST_CXX" >/dev/null 2>&1; then
    printf 'error: host C++ compiler is not executable: %s\n' "$TOOLCHAIN_HOST_CXX" >&2
    exit 1
fi

host_cflags=""
host_cxxflags=""
host_cppflags=""
host_ldflags=""
host_configure_args=()
cmake_darwin_args=()

if [[ "$(uname -s)" == Darwin ]]; then
    for required in xcrun sw_vers; do
        if ! command -v "$required" >/dev/null 2>&1; then
            printf 'error: required Apple tool is missing: %s\n' "$required" >&2
            exit 1
        fi
    done
    if ! "$TOOLCHAIN_HOST_CC" -dM -E -x c /dev/null 2>/dev/null |
         grep -q '^#define __clang__ '; then
        printf '%s\n' \
            'error: the macOS LLVM bootstrap host compiler must be Apple/LLVM Clang.' \
            "selected: $TOOLCHAIN_HOST_CC" >&2
        exit 1
    fi

    SDKROOT="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
    MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion | awk -F. '{print $1 "." $2}')}"
    case "$(uname -m)" in
        arm64|aarch64) darwin_arch=arm64 ;;
        x86_64) darwin_arch=x86_64 ;;
        *)
            printf 'error: unsupported Darwin host architecture: %s\n' "$(uname -m)" >&2
            exit 1
            ;;
    esac
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

    host_cflags="-arch $darwin_arch -isysroot $SDKROOT -mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
    host_cxxflags="$host_cflags"
    host_cppflags="$host_cflags"
    host_ldflags="$host_cflags"
    host_configure_args+=(--with-system-zlib)
    cmake_darwin_args=(
        "-DCMAKE_OSX_SYSROOT=$SDKROOT"
        "-DCMAKE_OSX_ARCHITECTURES=$darwin_arch"
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET"
    )
fi

clean_env=(
    env
    -u CFLAGS_FOR_TARGET -u CXXFLAGS_FOR_TARGET
    -u CPPFLAGS_FOR_TARGET -u LDFLAGS_FOR_TARGET
    -u CPATH -u C_INCLUDE_PATH -u CPLUS_INCLUDE_PATH -u OBJC_INCLUDE_PATH
    -u COMPILER_PATH -u GCC_EXEC_PREFIX -u LIBRARY_PATH
    -u LD_LIBRARY_PATH -u DYLD_LIBRARY_PATH -u DYLD_FALLBACK_LIBRARY_PATH
    -u PKG_CONFIG_PATH -u PKG_CONFIG_LIBDIR -u PKG_CONFIG_SYSROOT_DIR
    -u CMAKE_PREFIX_PATH -u CMAKE_LIBRARY_PATH -u CMAKE_INCLUDE_PATH
)

cleanup()
{
    local status=$?
    [[ -z "$temporary_download" ]] || rm -f "$temporary_download"
    [[ -z "$stage_root" ]] || rm -rf "$stage_root"
    if [[ "$status" -ne 0 ]]; then
        printf 'error: PowerPC Clang bootstrap failed during %s (status %s)\n' \
            "$bootstrap_stage" "$status" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

mkdir -p "$TOOLCHAIN_DOWNLOAD_DIR" "$TOOLCHAIN_WORK_DIR"

bootstrap_stage="preparing LLVM source"
if [[ ! -d "$LLVM_SOURCE_DIR/.git" ]]; then
    if [[ "$LLVM_GIT_OFFLINE" == 1 ]]; then
        printf 'error: offline mode has no cached LLVM source: %s\n' \
            "$LLVM_SOURCE_DIR" >&2
        exit 1
    fi
    rm -rf "$LLVM_SOURCE_DIR"
    git clone --filter=blob:none --no-checkout "$LLVM_GIT_URL" "$LLVM_SOURCE_DIR"
    git -C "$LLVM_SOURCE_DIR" sparse-checkout init --cone
fi
git -C "$LLVM_SOURCE_DIR" remote set-url origin "$LLVM_GIT_URL"
# LLVM core now imports common utilities from the sibling libc project even
# when libc itself is not an enabled build project, so keep that source slice
# in the compiler cache alongside llvm/clang/cmake/third-party.
git -C "$LLVM_SOURCE_DIR" sparse-checkout set llvm clang cmake third-party libc
if [[ "$LLVM_GIT_OFFLINE" != 1 ]]; then
    if [[ -n "$LLVM_GIT_COMMIT" ]]; then
        git -C "$LLVM_SOURCE_DIR" fetch --depth=1 --force origin "$LLVM_GIT_COMMIT"
    else
        git -C "$LLVM_SOURCE_DIR" fetch --depth=1 --force origin "$LLVM_GIT_REF"
    fi
    llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse FETCH_HEAD)"
else
    if [[ -n "$LLVM_GIT_COMMIT" ]]; then
        llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse --verify "${LLVM_GIT_COMMIT}^{commit}")"
    else
        llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse --verify "${LLVM_GIT_REF}^{commit}")"
    fi
fi
if [[ -n "$LLVM_GIT_COMMIT" && "$llvm_revision" != "$LLVM_GIT_COMMIT" ]]; then
    printf '%s\n' \
        'error: LLVM source did not resolve to the pinned commit.' \
        "resolved: $llvm_revision" \
        "pinned:   $LLVM_GIT_COMMIT" >&2
    exit 1
fi
git -C "$LLVM_SOURCE_DIR" checkout --detach --force "$llvm_revision"
git -C "$LLVM_SOURCE_DIR" clean -fdx >/dev/null
if [[ ! -d "$LLVM_SOURCE_DIR/libc" ]]; then
    printf 'error: LLVM compiler cache is missing required libc common utilities\n' >&2
    exit 1
fi

marker="$TOOLCHAIN_DIR/.whp-powerpc-toolchain"
expected_marker="$(cat <<MARKER
BOOTSTRAP_SCHEMA=10
COMPILER=clang
ASSEMBLER=clang-integrated
GNU_GAS=disabled
GNU_GPROF=disabled
GNU_GPROFNG=disabled
TARGET=$TOOLCHAIN_TARGET
BINUTILS_VERSION=$BINUTILS_VERSION
BINUTILS_SHA256=$BINUTILS_SHA256
LLVM_GIT_URL=$LLVM_GIT_URL
LLVM_GIT_COMMIT=$llvm_revision
HOST_SYSTEM=$(uname -srm)
HOST_CC=$TOOLCHAIN_HOST_CC
HOST_CXX=$TOOLCHAIN_HOST_CXX
HOST_CFLAGS=$host_cflags
HOST_CXXFLAGS=$host_cxxflags
HOST_CPPFLAGS=$host_cppflags
HOST_LDFLAGS=$host_ldflags
MARKER
)"

clang_toolchain_is_usable()
{
    local prefix="$1"
    local tool

    for tool in gcc ar ld nm objcopy objdump readelf strip ranlib; do
        [[ -x "$prefix/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
    done
    [[ -x "$prefix/llvm/bin/clang" ]] || return 1
    [[ -x "$prefix/libexec/powerpc-clang-gnu/ld" ]] || return 1
    [[ ! -e "$prefix/libexec/powerpc-clang-gnu/as" ]] || return 1
    [[ ! -e "$prefix/libexec/powerpc-clang-gnu/as.bfd" ]] || return 1
    [[ ! -e "$prefix/bin/${TOOLCHAIN_TARGET}-gprof" ]] || return 1
    [[ ! -e "$prefix/$TOOLCHAIN_TARGET/bin/gprof" ]] || return 1
}

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 ]] &&
   [[ -f "$marker" ]] &&
   [[ "$(cat "$marker")" == "$expected_marker" ]] &&
   clang_toolchain_is_usable "$TOOLCHAIN_DIR"; then
    printf 'PowerPC Clang toolchain is current: %s/bin/%s-\n' \
        "$TOOLCHAIN_DIR" "$TOOLCHAIN_TARGET"
    stage_root=""
    exit 0
fi

binutils_tar="$TOOLCHAIN_DOWNLOAD_DIR/$BINUTILS_ARCHIVE"
binutils_src="$TOOLCHAIN_WORK_DIR/binutils-$BINUTILS_VERSION"
binutils_build="$TOOLCHAIN_WORK_DIR/build-binutils-$BINUTILS_VERSION"

bootstrap_stage="downloading and verifying binutils"
if [[ ! -f "$binutils_tar" ]]; then
    temporary_download="${binutils_tar}.tmp.$$"
    rm -f "$temporary_download"
    if [[ "$download_cmd" == curl ]]; then
        curl --fail --location --retry 3 --output "$temporary_download" "$BINUTILS_URL"
    else
        wget --tries=3 --output-document="$temporary_download" "$BINUTILS_URL"
    fi
    mv -f "$temporary_download" "$binutils_tar"
    temporary_download=""
fi
actual_sha="$("${hash_cmd[@]}" "$binutils_tar" | awk '{print $1}')"
if [[ "$actual_sha" != "$BINUTILS_SHA256" ]]; then
    rm -f "$binutils_tar"
    printf 'error: checksum mismatch for %s\n' "$binutils_tar" >&2
    printf 'expected: %s\nactual:   %s\n' "$BINUTILS_SHA256" "$actual_sha" >&2
    exit 1
fi

bootstrap_stage="extracting binutils"
rm -rf "$binutils_src"
tar -xf "$binutils_tar" -C "$TOOLCHAIN_WORK_DIR"

build_triplet="$("$binutils_src/config.guess")"
host_triplet="$build_triplet"

stage_root="$TOOLCHAIN_WORK_DIR/install-root.$$"
staged_toolchain="$stage_root$TOOLCHAIN_DIR"
rm -rf "$stage_root"
mkdir -p "$stage_root"

bootstrap_stage="configuring and building GNU binutils without GAS or profilers"
rm -rf "$binutils_build"
mkdir -p "$binutils_build"
(
    cd "$binutils_build"
    "${clean_env[@]}" \
        CC="$TOOLCHAIN_HOST_CC" \
        CXX="$TOOLCHAIN_HOST_CXX" \
        CFLAGS="$host_cflags" \
        CXXFLAGS="$host_cxxflags" \
        CPPFLAGS="$host_cppflags" \
        LDFLAGS="$host_ldflags" \
        PKG_CONFIG=false \
        "$binutils_src/configure" \
        --build="$build_triplet" \
        --host="$host_triplet" \
        --target="$TOOLCHAIN_TARGET" \
        --prefix="$TOOLCHAIN_DIR" \
        --with-sysroot \
        --disable-gas \
        --disable-gdb \
        --disable-gdbserver \
        --disable-gprof \
        --disable-gprofng \
        --disable-gold \
        --disable-nls \
        --disable-shared \
        --disable-sim \
        --disable-werror \
        --enable-static \
        "${host_configure_args[@]}" \
        --without-zstd
    "${clean_env[@]}" \
        CC="$TOOLCHAIN_HOST_CC" \
        CXX="$TOOLCHAIN_HOST_CXX" \
        CFLAGS="$host_cflags" \
        CXXFLAGS="$host_cxxflags" \
        CPPFLAGS="$host_cppflags" \
        LDFLAGS="$host_ldflags" \
        PKG_CONFIG=false \
        "$MAKE_CMD" -j"$JOBS" MAKEINFO=true
    "${clean_env[@]}" \
        "$MAKE_CMD" MAKEINFO=true DESTDIR="$stage_root" install
)

mkdir -p "$staged_toolchain/$TOOLCHAIN_TARGET/bin" \
         "$staged_toolchain/$TOOLCHAIN_TARGET/sys-root"
for tool in ar ld nm objcopy objdump readelf strip ranlib; do
    if [[ ! -x "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-${tool}" ]]; then
        printf 'error: staged GNU PowerPC binutils is missing %s\n' "$tool" >&2
        exit 1
    fi
    ln -sf "../../bin/${TOOLCHAIN_TARGET}-${tool}" \
        "$staged_toolchain/$TOOLCHAIN_TARGET/bin/$tool"
done
if [[ -e "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-as" ||
      -e "$staged_toolchain/$TOOLCHAIN_TARGET/bin/as" ]]; then
    printf 'error: GNU as was installed even though GAS is disabled\n' >&2
    exit 1
fi
if [[ -e "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-gprof" ||
      -e "$staged_toolchain/$TOOLCHAIN_TARGET/bin/gprof" ]]; then
    printf 'error: GNU gprof was installed even though profiling is disabled\n' >&2
    exit 1
fi

bootstrap_stage="configuring and building PowerPC-only Clang"
rm -rf "$LLVM_BUILD_DIR"
cmake -S "$LLVM_SOURCE_DIR/llvm" -B "$LLVM_BUILD_DIR" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="$TOOLCHAIN_HOST_CC" \
    -DCMAKE_CXX_COMPILER="$TOOLCHAIN_HOST_CXX" \
    -DCMAKE_INSTALL_PREFIX="$TOOLCHAIN_DIR/llvm" \
    "${cmake_darwin_args[@]}" \
    -DLLVM_ENABLE_PROJECTS=clang \
    -DLLVM_TARGETS_TO_BUILD=PowerPC \
    -DLLVM_ENABLE_ASSERTIONS=OFF \
    -DLLVM_INCLUDE_TESTS=OFF \
    -DLLVM_INCLUDE_EXAMPLES=OFF \
    -DLLVM_INCLUDE_BENCHMARKS=OFF \
    -DCLANG_INCLUDE_TESTS=OFF \
    -DLLVM_ENABLE_TERMINFO=OFF \
    -DLLVM_ENABLE_ZLIB=OFF \
    -DLLVM_ENABLE_ZSTD=OFF \
    -DLLVM_ENABLE_LIBXML2=OFF
cmake --build "$LLVM_BUILD_DIR" --parallel "$JOBS"
DESTDIR="$stage_root" cmake --install "$LLVM_BUILD_DIR"

clang="$staged_toolchain/llvm/bin/clang"
if [[ ! -x "$clang" ]]; then
    printf 'error: LLVM install did not produce Clang: %s\n' "$clang" >&2
    exit 1
fi
if ! "$clang" --print-targets | grep -Eq '(^|[[:space:]])ppc32([[:space:]]|$)'; then
    printf 'error: bootstrapped Clang does not contain the PowerPC 32 backend\n' >&2
    exit 1
fi

# Validate the retained binutils with an object produced by LLVM IAS.  This
# proves the GNU linker/object utilities interoperate without ever building GAS.
bootstrap_stage="validating binutils with LLVM integrated assembler"
smoke_dir="$TOOLCHAIN_WORK_DIR/binutils-smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/smoke.s" <<'ASSEMBLY'
.text
.globl whp_binutils_smoke
whp_binutils_smoke:
    nop
ASSEMBLY
"$clang" --target=powerpc-none-elf -c -x assembler \
    "$smoke_dir/smoke.s" -o "$smoke_dir/smoke.o"
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-ld" \
    -r -o "$smoke_dir/linked.o" "$smoke_dir/smoke.o"
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" -h "$smoke_dir/linked.o" |
    grep -q 'Machine:.*PowerPC'
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" -h "$smoke_dir/linked.o" |
    grep -q 'Data:.*big endian'

bootstrap_stage="installing the OpenBIOS Clang compatibility driver"
shim_dir="$staged_toolchain/libexec/powerpc-clang-gnu"
mkdir -p "$shim_dir"
ln -sf "../../bin/${TOOLCHAIN_TARGET}-ld" "$shim_dir/ld"

cat > "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-gcc" <<'WRAPPER'
#!/usr/bin/env bash
set -euo pipefail

prefix="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
clang="$prefix/llvm/bin/clang"
tool_shims="$prefix/libexec/powerpc-clang-gnu"
translated=()

# OpenBIOS carries three GCC-only PowerPC policy flags.  Clang's bare-metal
# PowerPC ABI already uses static, non-small-data addressing for this lane; the
# bootstrap smoke test below verifies that no .sdata/.sbss sections appear.
# Keep this translation local to the compatibility driver so PPC-Firmware does
# not have to change during the compiler migration.
for arg in "$@"; do
    case "$arg" in
        -mcall-sysv-noeabi|-msdata=none|-G0|\
        -Wbuiltin-declaration-mismatch|-Wmaybe-uninitialized|-Wno-maybe-uninitialized)
            ;;
        *)
            translated+=("$arg")
            ;;
    esac
done

exec "$clang" \
    --target=powerpc-none-elf \
    -fintegrated-as \
    -B"$tool_shims" \
    "${translated[@]}"
WRAPPER
chmod +x "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-gcc"

bootstrap_stage="validating Clang integrated assembler substitution"
clang_driver="$staged_toolchain/bin/${TOOLCHAIN_TARGET}-gcc"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat > "$smoke_dir/smoke.c" <<'SOURCE'
#if !defined(__powerpc__) && !defined(__POWERPC__) && !defined(__PPC__)
#error compiler is not targeting PowerPC
#endif
#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_BIG_ENDIAN__
#error compiler does not default to big endian
#endif
int whp_powerpc_global = 7;
int whp_powerpc_clang_smoke(int value) { return whp_powerpc_global + value; }
SOURCE

"$clang_driver" \
    -m32 -mcpu=604 -msoft-float \
    -mcall-sysv-noeabi -msdata=none -G0 \
    -ffreestanding -fno-pic -fno-pie -O0 \
    -c "$smoke_dir/smoke.c" -o "$smoke_dir/smoke.o"
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" -h "$smoke_dir/smoke.o" |
    grep -q 'Machine:.*PowerPC'
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" -h "$smoke_dir/smoke.o" |
    grep -q 'Data:.*big endian'
if "$staged_toolchain/bin/${TOOLCHAIN_TARGET}-readelf" -SW "$smoke_dir/smoke.o" |
   grep -Eq '[[:space:]]\.s(data|bss)([[:space:]]|$)'; then
    printf 'error: Clang generated a PowerPC small-data section unexpectedly\n' >&2
    exit 1
fi
"$staged_toolchain/bin/${TOOLCHAIN_TARGET}-ld" \
    -r -o "$smoke_dir/linked.o" "$smoke_dir/smoke.o"

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
stage_root=""
bootstrap_stage="completed"
printf '%s\n' \
    "Bootstrapped PowerPC compiler: Clang ($llvm_revision)" \
    "GNU binutils: $BINUTILS_VERSION (GAS/gprof disabled)" \
    "Assembler: Clang integrated assembler" \
    "Compatibility prefix: $TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-"