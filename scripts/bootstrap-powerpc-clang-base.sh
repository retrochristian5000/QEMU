#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
TOOLCHAIN_TARGET="${POWERPC_TOOLCHAIN_TARGET:-powerpc-elf}"
TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$SOURCE_DIR/build/toolchains/$TOOLCHAIN_TARGET}"
TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/$TOOLCHAIN_TARGET-clang}"
TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
TOOLCHAIN_HOST_CC="${TOOLCHAIN_HOST_CC:-${CC_FOR_BUILD:-${CC:-cc}}}"
TOOLCHAIN_HOST_CXX="${TOOLCHAIN_HOST_CXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
JOBS="${JOBS:-1}"

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
                  "$LLVM_SOURCE_DIR" "$LLVM_BUILD_DIR"; do
    case "$build_path" in
        *[' ':]*)
            printf 'error: PowerPC Clang build paths cannot contain spaces or colons: %s\n' \
                "$build_path" >&2
            exit 1
            ;;
esac
done

for required in git cmake ninja grep awk ln mkdir mv rm; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: PowerPC Clang bootstrap dependency not found: %s\n' \
            "$required" >&2
        exit 1
    fi
done

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

# LLVM's normal Release profile uses the host compiler's most aggressive
# optimization setting (typically -O3 for GCC/Clang). That is useful for a
# shipped compiler release, but it substantially increases bootstrap latency.
# Use -O2 for GCC-compatible host compilers; other compiler families keep their
# native Release flags so this optimization does not narrow host portability.
cmake_host_release_args=()
host_release_flags="toolchain-default"
if "$TOOLCHAIN_HOST_CC" -dM -E -x c /dev/null 2>/dev/null |
       grep -Eq '^#define (__clang__|__GNUC__) ' &&
   "$TOOLCHAIN_HOST_CXX" -dM -E -x c++ /dev/null 2>/dev/null |
       grep -Eq '^#define (__clang__|__GNUC__) '; then
    host_release_flags="-O2 -DNDEBUG"
    cmake_host_release_args=(
        "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG"
        "-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG"
    )
fi

host_cflags=""
host_cxxflags=""
host_cppflags=""
host_ldflags=""
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
    cmake_darwin_args=(
        "-DCMAKE_OSX_SYSROOT=$SDKROOT"
        "-DCMAKE_OSX_ARCHITECTURES=$darwin_arch"
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET"
    )
fi

cleanup()
{
    local status=$?
    [[ -z "$stage_root" ]] || rm -rf "$stage_root"
    if [[ "$status" -ne 0 ]]; then
        printf 'error: PowerPC Clang bootstrap failed during %s (status %s)\n' \
            "$bootstrap_stage" "$status" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

mkdir -p "$TOOLCHAIN_WORK_DIR"

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
BOOTSTRAP_SCHEMA=14
COMPILER=clang
ASSEMBLER=clang-integrated
GNU_BINUTILS=disabled
SFRAME=disabled
TARGET=$TOOLCHAIN_TARGET
LLVM_GIT_URL=$LLVM_GIT_URL
LLVM_GIT_COMMIT=$llvm_revision
LLVM_CMAKE_MODE=incremental-distribution-fast-host-flags
HOST_SYSTEM=$(uname -srm)
HOST_CC=$TOOLCHAIN_HOST_CC
HOST_CXX=$TOOLCHAIN_HOST_CXX
HOST_CFLAGS=$host_cflags
HOST_CXXFLAGS=$host_cxxflags
HOST_CPPFLAGS=$host_cppflags
HOST_LDFLAGS=$host_ldflags
HOST_RELEASE_FLAGS=$host_release_flags
MARKER
)"

clang_toolchain_is_usable()
{
    local prefix="$1"
    local tool

    [[ -x "$prefix/bin/${TOOLCHAIN_TARGET}-gcc" ]] || return 1
    for tool in clang llvm-ar llvm-nm llvm-ranlib llvm-readelf llvm-strip \
                llvm-config llvm-tblgen; do
        [[ -x "$prefix/llvm/bin/$tool" ]] || return 1
    done
    for tool in as objcopy objdump readelf gprof; do
        [[ ! -e "$prefix/bin/${TOOLCHAIN_TARGET}-${tool}" ]] || return 1
        [[ ! -e "$prefix/$TOOLCHAIN_TARGET/bin/$tool" ]] || return 1
    done
    for tool in as ar ld nm objcopy objdump readelf strip ranlib; do
        [[ ! -e "$prefix/libexec/powerpc-clang-gnu/${tool}.bfd" ]] || return 1
    done
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

stage_root="$TOOLCHAIN_WORK_DIR/install-root.$$"
staged_toolchain="$stage_root$TOOLCHAIN_DIR"
rm -rf "$stage_root"
mkdir -p "$stage_root"

# Keep the CMake/Ninja graph alive across LLVM revisions. CMake reconfiguration
# updates changed rules in place, while Ninja retains object-level dependency
# state. A forced rebuild uses the backend's clean target instead of deleting
# CMakeCache.txt and rebuilding the project graph from scratch.
bootstrap_stage="configuring PowerPC-only Clang"
llvm_distribution_components='clang;clang-resource-headers;llvm-ar;llvm-ranlib;llvm-nm;llvm-objcopy;llvm-strip;llvm-readobj;llvm-readelf;llvm-config;llvm-tblgen;llvm-headers;llvm-libraries;cmake-exports'
cmake -S "$LLVM_SOURCE_DIR/llvm" -B "$LLVM_BUILD_DIR" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="$TOOLCHAIN_HOST_CC" \
    -DCMAKE_CXX_COMPILER="$TOOLCHAIN_HOST_CXX" \
    "${cmake_host_release_args[@]}" \
    -DCMAKE_INSTALL_PREFIX="$TOOLCHAIN_DIR/llvm" \
    "${cmake_darwin_args[@]}" \
    -DLLVM_ENABLE_PROJECTS=clang \
    -DLLVM_TARGETS_TO_BUILD=PowerPC \
    -DLLVM_DISTRIBUTION_COMPONENTS="$llvm_distribution_components" \
    -DLLVM_ENABLE_ASSERTIONS=OFF \
    -DLLVM_ENABLE_WARNINGS=OFF \
    -DLLVM_ENABLE_PEDANTIC=OFF \
    -DLLVM_INCLUDE_TESTS=OFF \
    -DLLVM_INCLUDE_EXAMPLES=OFF \
    -DLLVM_INCLUDE_BENCHMARKS=OFF \
    -DLLVM_INCLUDE_DOCS=OFF \
    -DLLVM_INCLUDE_UTILS=OFF \
    -DLLVM_INCLUDE_RUNTIMES=OFF \
    -DLLVM_ENABLE_BINDINGS=OFF \
    -DCLANG_INCLUDE_TESTS=OFF \
    -DLLVM_ENABLE_TERMINFO=OFF \
    -DLLVM_ENABLE_ZLIB=OFF \
    -DLLVM_ENABLE_ZSTD=OFF \
    -DLLVM_ENABLE_LIBXML2=OFF

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then
    bootstrap_stage="cleaning requested LLVM outputs"
    cmake --build "$LLVM_BUILD_DIR" --target clean
fi

bootstrap_stage="building PowerPC LLVM distribution"
cmake --build "$LLVM_BUILD_DIR" --target distribution --parallel "$JOBS"
bootstrap_stage="installing PowerPC LLVM distribution"
DESTDIR="$stage_root" \
    cmake --build "$LLVM_BUILD_DIR" --target install-distribution --parallel "$JOBS"

clang="$staged_toolchain/llvm/bin/clang"
llvm_readelf="$staged_toolchain/llvm/bin/llvm-readelf"
for tool in clang llvm-ar llvm-nm llvm-ranlib llvm-readelf llvm-strip \
            llvm-config llvm-tblgen; do
    if [[ ! -x "$staged_toolchain/llvm/bin/$tool" ]]; then
        printf 'error: LLVM distribution did not produce %s\n' "$tool" >&2
        exit 1
    fi
done
if [[ ! -f "$staged_toolchain/llvm/lib/cmake/llvm/LLVMConfig.cmake" ]]; then
    printf 'error: LLVM distribution did not install CMake package metadata\n' >&2
    exit 1
fi
if ! "$clang" --print-targets | grep -Eq '(^|[[:space:]])ppc32([[:space:]]|$)'; then
    printf 'error: bootstrapped Clang does not contain the PowerPC 32 backend\n' >&2
    exit 1
fi

bootstrap_stage="installing the OpenBIOS Clang compatibility driver"
shim_dir="$staged_toolchain/libexec/powerpc-clang-gnu"
mkdir -p "$staged_toolchain/bin" \
         "$staged_toolchain/$TOOLCHAIN_TARGET/bin" \
         "$staged_toolchain/$TOOLCHAIN_TARGET/sys-root" \
         "$shim_dir"

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
smoke_dir="$TOOLCHAIN_WORK_DIR/clang-smoke"
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
"$llvm_readelf" -h "$smoke_dir/smoke.o" |
    grep -q 'Machine:.*PowerPC'
"$llvm_readelf" -h "$smoke_dir/smoke.o" |
    grep -q 'Data:.*big endian'
if "$llvm_readelf" -SW "$smoke_dir/smoke.o" |
   grep -Eq '[[:space:]]\.s(data|bss)([[:space:]]|$)'; then
    printf 'error: Clang generated a PowerPC small-data section unexpectedly\n' >&2
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
rm -rf "$old_toolchain" "$stage_root"
stage_root=""
bootstrap_stage="completed"
printf '%s\n' \
    "Bootstrapped PowerPC compiler: Clang ($llvm_revision)" \
    "Binary utilities: LLVM only (SFrame not required)" \
    "Assembler: Clang integrated assembler" \
    "Compatibility prefix: $TOOLCHAIN_DIR/bin/$TOOLCHAIN_TARGET-"
