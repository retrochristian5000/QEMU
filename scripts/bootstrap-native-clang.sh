#!/usr/bin/env bash
set -euo pipefail

# build.sh captures stdout to obtain exactly one value: the installed prefix.
# Send CMake/Ninja/git chatter to stderr so the compiler path cannot be
# contaminated by bootstrap progress output.
exec 3>&1
exec 1>&2

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"
LLVM_SUBMODULE_PATH="${NATIVE_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
LLVM_SOURCE_DIR="$SOURCE_DIR/$LLVM_SUBMODULE_PATH"
TOOLCHAIN_FORCE_REBUILD="${NATIVE_LLVM_FORCE_REBUILD:-0}"
JOBS="${JOBS:-}"
LLVM_LINK_JOBS="${NATIVE_LLVM_LINK_JOBS:-2}"
stage_root=""

# This script builds the compiler used by QEMU; it is not itself a QEMU host
# object build. Do not let outer optimization, sanitizer, coverage, or frame-
# pointer policy become part of LLVM's bootstrap ABI. Platform ABI inputs such
# as SDKROOT and MACOSX_DEPLOYMENT_TARGET are handled explicitly below.
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS

case "$TOOLCHAIN_FORCE_REBUILD" in
    0|1) ;;
    *)
        printf 'error: NATIVE_LLVM_FORCE_REBUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac
case "$LLVM_LINK_JOBS" in
    0|*[!0-9]*)
        printf 'error: NATIVE_LLVM_LINK_JOBS must be a positive integer: %s\n' \
            "$LLVM_LINK_JOBS" >&2
        exit 1
        ;;
    *) ;;
esac

# build.sh owns host detection. Keep a direct-invocation fallback for this
# helper, but never reinterpret a normalized host identity supplied by the
# public build entry.
host_os="${WHP_HOST_OS:-}"
host_kernel="${WHP_HOST_KERNEL:-$(uname -s)}"
host_arch="${WHP_HOST_ARCH:-$(uname -m)}"
if [[ -z "$host_os" ]]; then
    case "$host_kernel" in
        Darwin) host_os=macos ;;
        Linux) host_os=linux ;;
        CYGWIN*|MINGW*|MSYS*) host_os=windows ;;
        FreeBSD) host_os=freebsd ;;
        NetBSD) host_os=netbsd ;;
        OpenBSD) host_os=openbsd ;;
        DragonFly) host_os=dragonfly ;;
        SunOS) host_os=solaris ;;
        Haiku) host_os=haiku ;;
        *) host_os=other ;;
    esac
fi

case "$host_arch" in
    arm64|aarch64)
        host_tag=arm64
        llvm_target=AArch64
        smoke_macro=__aarch64__
        ;;
    x86_64|amd64)
        host_tag=x86_64
        llvm_target=X86
        smoke_macro=__x86_64__
        ;;
    *)
        printf 'error: unsupported native LLVM host architecture: %s\n' "$host_arch" >&2
        exit 1
        ;;
esac
case "$host_os" in
    macos) host_platform=apple-darwin ;;
    linux) host_platform=linux ;;
    *)
        printf '%s\n' \
            'error: WHP native LLVM bootstrap does not support this host OS.' \
            "detected OS: $host_os" \
            "kernel:      $host_kernel" \
            "architecture: $host_arch" >&2
        exit 1
        ;;
esac

host_id="$host_tag-$host_platform"
TOOLCHAIN_DIR="${NATIVE_LLVM_DIR:-$SOURCE_DIR/build/toolchains/native-llvm/$host_id}"
TOOLCHAIN_WORK_DIR="${NATIVE_LLVM_WORK_DIR:-$SOURCE_DIR/build/toolchain-work/native-llvm-$host_id}"
LLVM_BUILD_DIR="${NATIVE_LLVM_BUILD_DIR:-$TOOLCHAIN_WORK_DIR/llvm-build}"

cleanup()
{
    local status=$?
    [[ -z "$stage_root" ]] || rm -rf "$stage_root"
    exit "$status"
}
trap cleanup EXIT

cmake_parallel_args=(--parallel)
if [[ -n "$JOBS" ]]; then
    case "$JOBS" in
        0|*[!0-9]*)
            printf 'error: JOBS must be a positive integer when set: %s\n' "$JOBS" >&2
            exit 1
            ;;
    esac
    cmake_parallel_args=(--parallel "$JOBS")
fi

for tool in git cmake ninja sed mkdir mv rm ln mktemp; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: native LLVM bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done

cmake_host_args=()
sdkroot=""
deployment_target=""
if [[ "$host_os" == macos ]]; then
    for tool in xcrun sw_vers; do
        command -v "$tool" >/dev/null 2>&1 || {
            printf 'error: native LLVM macOS dependency not found: %s\n' "$tool" >&2
            exit 1
        }
    done
    bootstrap_cc="${NATIVE_LLVM_BOOTSTRAP_CC:-$(xcrun --sdk macosx --find clang)}"
    bootstrap_cxx="${NATIVE_LLVM_BOOTSTRAP_CXX:-$(xcrun --sdk macosx --find clang++)}"
    sdkroot="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
    deployment_target="${MACOSX_DEPLOYMENT_TARGET:-$(sw_vers -productVersion | sed -E 's/^([0-9]+\.[0-9]+).*/\1/')}"
    [[ -d "$sdkroot" ]] || {
        printf 'error: native LLVM macOS SDK does not exist: %s\n' "$sdkroot" >&2
        exit 1
    }
    cmake_host_args=(
        "-DCMAKE_OSX_SYSROOT=$sdkroot"
        "-DCMAKE_OSX_ARCHITECTURES=$host_tag"
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=$deployment_target"
    )
else
    bootstrap_cc="${NATIVE_LLVM_BOOTSTRAP_CC:-${CC_FOR_BUILD:-cc}}"
    bootstrap_cxx="${NATIVE_LLVM_BOOTSTRAP_CXX:-${CXX_FOR_BUILD:-c++}}"
fi

for compiler in "$bootstrap_cc" "$bootstrap_cxx"; do
    [[ -x "$compiler" ]] || command -v "$compiler" >/dev/null 2>&1 || {
        printf 'error: native LLVM bootstrap compiler is not executable: %s\n' "$compiler" >&2
        exit 1
    }
done

query_target_triple()
{
    local compiler="$1"
    local target=''

    target="$("$compiler" -print-target-triple 2>/dev/null || true)"
    if [[ -z "$target" ]]; then
        target="$("$compiler" -dumpmachine 2>/dev/null || true)"
    fi
    printf '%s\n' "$target" | sed -n '1p'
}

canonical_native_arch()
{
    case "$1" in
        arm64|aarch64) printf 'arm64\n' ;;
        x86_64|amd64) printf 'x86_64\n' ;;
        *) return 1 ;;
    esac
}

native_target_matches_host()
{
    local target="$1"
    local arch target_arch target_vendor target_os

    [[ -n "$target" ]] || return 1
    IFS='-' read -r arch target_vendor target_os _ <<< "$target"
    target_arch="$(canonical_native_arch "$arch" 2>/dev/null || true)"
    [[ "$target_arch" == "$host_tag" ]] || return 1

    case "$host_os" in
        macos)
            [[ "$target_vendor" == apple ]] || return 1
            case "$target_os" in
                darwin*|macos*) ;;
                *) return 1 ;;
            esac
            ;;
        linux)
            case "$target" in
                *-linux-*|*-linux) ;;
                *) return 1 ;;
            esac
            ;;
        *) return 1 ;;
    esac
}

bootstrap_cc_target="$(query_target_triple "$bootstrap_cc")"
bootstrap_cxx_target="$(query_target_triple "$bootstrap_cxx")"
if ! native_target_matches_host "$bootstrap_cc_target"; then
    printf '%s\n' \
        'error: native LLVM bootstrap C compiler does not target the host ABI.' \
        "compiler: $bootstrap_cc" \
        "target:   ${bootstrap_cc_target:-<unknown>}" \
        "host:     $host_id ($host_os/$host_kernel)" >&2
    exit 1
fi
if ! native_target_matches_host "$bootstrap_cxx_target"; then
    printf '%s\n' \
        'error: native LLVM bootstrap C++ compiler does not target the host ABI.' \
        "compiler: $bootstrap_cxx" \
        "target:   ${bootstrap_cxx_target:-<unknown>}" \
        "host:     $host_id ($host_os/$host_kernel)" >&2
    exit 1
fi

# The WHP LLVM fork is already a QEMU submodule and is the single source for
# firmware, legacy-target, and native compiler profiles. Keep the native lane
# on that gitlink rather than cloning or pinning a second LLVM lineage.
git -C "$SOURCE_DIR" submodule update --init --depth 1 "$LLVM_SUBMODULE_PATH"
[[ -f "$LLVM_SOURCE_DIR/llvm/CMakeLists.txt" &&
   -f "$LLVM_SOURCE_DIR/clang/CMakeLists.txt" ]] || {
    printf 'error: WHP LLVM submodule is incomplete: %s\n' "$LLVM_SOURCE_DIR" >&2
    exit 1
}
llvm_revision="$(git -C "$LLVM_SOURCE_DIR" rev-parse HEAD)"
bootstrap_cc_version="$("$bootstrap_cc" --version 2>&1 | sed -n '1p')"
bootstrap_cxx_version="$("$bootstrap_cxx" --version 2>&1 | sed -n '1p')"
marker="$TOOLCHAIN_DIR/.whp-native-llvm"
expected_marker="$(cat <<EOF
BOOTSTRAP_SCHEMA=2
LLVM_GIT_COMMIT=$llvm_revision
HOST=$host_id
HOST_OS=$host_os
HOST_KERNEL=$host_kernel
HOST_ARCH=$host_arch
LLVM_TARGETS_TO_BUILD=$llvm_target
DISTRIBUTION=clang-native-minimal
BOOTSTRAP_CC=$bootstrap_cc
BOOTSTRAP_CC_VERSION=$bootstrap_cc_version
BOOTSTRAP_CC_TARGET_TRIPLE=$bootstrap_cc_target
BOOTSTRAP_CXX=$bootstrap_cxx
BOOTSTRAP_CXX_VERSION=$bootstrap_cxx_version
BOOTSTRAP_CXX_TARGET_TRIPLE=$bootstrap_cxx_target
SDKROOT=$sdkroot
MACOSX_DEPLOYMENT_TARGET=$deployment_target
EOF
)"

usable()
{
    local prefix="$1"
    local target=''

    [[ -x "$prefix/bin/clang" && -x "$prefix/bin/clang++" ]] || return 1
    "$prefix/bin/clang" --version >/dev/null 2>&1 || return 1
    "$prefix/bin/clang++" --version >/dev/null 2>&1 || return 1
    target="$(query_target_triple "$prefix/bin/clang")"
    native_target_matches_host "$target" || return 1
    target="$(query_target_triple "$prefix/bin/clang++")"
    native_target_matches_host "$target" || return 1
    printf 'int whp_native_llvm_usable(void) { return 0; }\n' |
        "$prefix/bin/clang" -x c -c - -o /dev/null >/dev/null 2>&1 || return 1
    printf '#include <stddef.h>\n#include <stdarg.h>\nsize_t whp_native_llvm_resource_size(void) { return sizeof(size_t) + sizeof(va_list); }\n' |
        "$prefix/bin/clang" -ffreestanding -x c -c - -o /dev/null \
            >/dev/null 2>&1 || return 1
    printf 'int whp_native_llvm_frame_pointer(void) { return 0; }\n' |
        "$prefix/bin/clang" -fno-omit-frame-pointer -momit-leaf-frame-pointer \
            -x c -c - -o /dev/null >/dev/null 2>&1 || return 1
    printf 'int whp_native_llvm_cxx_usable() { return 0; }\n' |
        "$prefix/bin/clang++" -x c++ -c - -o /dev/null >/dev/null 2>&1 || return 1
}

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0 && -f "$marker" &&
      "$(cat "$marker")" == "$expected_marker" ]] && usable "$TOOLCHAIN_DIR"; then
    printf 'WHP native LLVM is current: %s\n' "$TOOLCHAIN_DIR" >&2
    printf '%s\n' "$TOOLCHAIN_DIR" >&3
    exit 0
fi

# LLVM's IR, verifier, and installed resource-header contracts can change
# between revisions. If the installed compiler is stale, unhealthy, or only
# partially installed, do not reuse a CMake/Ninja graph containing objects from
# the suspect source state.
rm -rf "$LLVM_BUILD_DIR"
mkdir -p "$(dirname "$TOOLCHAIN_DIR")" "$TOOLCHAIN_WORK_DIR"
llvm_distribution_components='clang;clang-resource-headers'
cmake_args=(
    -S "$LLVM_SOURCE_DIR/llvm"
    -B "$LLVM_BUILD_DIR"
    -G Ninja
    -DCMAKE_BUILD_TYPE=Release
    -DCMAKE_C_COMPILER="$bootstrap_cc"
    -DCMAKE_CXX_COMPILER="$bootstrap_cxx"
    -DCMAKE_INSTALL_PREFIX="$TOOLCHAIN_DIR"
    -DCMAKE_EXPORT_COMPILE_COMMANDS=OFF
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF
    -DCMAKE_SKIP_INSTALL_ALL_DEPENDENCY=ON
    -DCMAKE_INSTALL_MESSAGE=NEVER
    -DLLVM_ENABLE_PROJECTS=clang
    "-DLLVM_TARGETS_TO_BUILD=$llvm_target"
    "-DLLVM_DISTRIBUTION_COMPONENTS=$llvm_distribution_components"
    -DLLVM_APPEND_VC_REV=OFF
    "-DLLVM_PARALLEL_LINK_JOBS=$LLVM_LINK_JOBS"
    -DLLVM_ENABLE_LTO=OFF
    -DLLVM_ENABLE_FATLTO=OFF
    -DLLVM_BUILD_INSTRUMENTED=OFF
    -DLLVM_ENABLE_ASSERTIONS=OFF
    -DLLVM_ENABLE_MODULES=OFF
    -DLLVM_ENABLE_PLUGINS=OFF
    -DLLVM_ENABLE_BACKTRACES=OFF
    -DLLVM_ENABLE_CRASH_OVERRIDES=OFF
    -DLLVM_ENABLE_UNWIND_TABLES=OFF
    -DLLVM_ENABLE_LIBEDIT=OFF
    -DLLVM_ENABLE_LIBPFM=OFF
    -DLLVM_ENABLE_Z3_SOLVER=OFF
    -DLLVM_ENABLE_WARNINGS=OFF
    -DLLVM_ENABLE_PEDANTIC=OFF
    -DLLVM_INCLUDE_TESTS=OFF
    -DLLVM_INCLUDE_EXAMPLES=OFF
    -DLLVM_INCLUDE_BENCHMARKS=OFF
    -DLLVM_INCLUDE_DOCS=OFF
    -DLLVM_INCLUDE_UTILS=OFF
    -DLLVM_INCLUDE_RUNTIMES=OFF
    -DLLVM_ENABLE_BINDINGS=OFF
    -DCLANG_INCLUDE_TESTS=OFF
    -DCLANG_ENABLE_STATIC_ANALYZER=OFF
    -DLLVM_ENABLE_ZLIB=OFF
    -DLLVM_ENABLE_ZSTD=OFF
    -DLLVM_ENABLE_LIBXML2=OFF
    "${cmake_host_args[@]}"
)
cmake "${cmake_args[@]}"
cmake --build "$LLVM_BUILD_DIR" --target distribution "${cmake_parallel_args[@]}"

stage_root="$TOOLCHAIN_WORK_DIR/install-root.$$"
rm -rf "$stage_root"
mkdir -p "$stage_root"
DESTDIR="$stage_root" \
    cmake --build "$LLVM_BUILD_DIR" --target install-distribution \
        "${cmake_parallel_args[@]}"
staged_toolchain="$stage_root$TOOLCHAIN_DIR"
[[ -x "$staged_toolchain/bin/clang" ]] || {
    printf 'error: WHP native LLVM did not install clang\n' >&2
    exit 1
}
if [[ ! -x "$staged_toolchain/bin/clang++" ]]; then
    ln -s clang "$staged_toolchain/bin/clang++"
fi

smoke_dir="$TOOLCHAIN_WORK_DIR/smoke"
rm -rf "$smoke_dir"
mkdir -p "$smoke_dir"
cat >"$smoke_dir/smoke.c" <<EOF
#ifndef $smoke_macro
#error native LLVM selected the wrong host backend
#endif
int whp_native_llvm_smoke(void) { return 0; }
EOF
cat >"$smoke_dir/smoke.cc" <<'EOF'
static_assert(sizeof(void *) >= 4, "unexpected native pointer width");
int whp_native_llvm_cxx_smoke() { return 0; }
EOF
"$staged_toolchain/bin/clang" -c "$smoke_dir/smoke.c" -o "$smoke_dir/smoke.o"
"$staged_toolchain/bin/clang++" -c "$smoke_dir/smoke.cc" -o "$smoke_dir/smoke-cxx.o"

printf '%s\n' "$expected_marker" > "$staged_toolchain/.whp-native-llvm"
usable "$staged_toolchain" || {
    printf 'error: staged WHP native LLVM toolchain is incomplete\n' >&2
    exit 1
}

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

printf 'WHP native LLVM ready: %s\n' "$TOOLCHAIN_DIR" >&2
printf '%s\n' "$TOOLCHAIN_DIR" >&3
