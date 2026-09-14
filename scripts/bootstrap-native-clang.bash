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
ninja_cmd="${NINJA_CMD:-${NINJA:-ninja}}"
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
        host_tag=aarch64
        darwin_cmake_arch=arm64
        llvm_target=AArch64
        smoke_macro=__aarch64__
        ;;
    x86_64|amd64)
        host_tag=x86_64
        darwin_cmake_arch=x86_64
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

for tool in git cmake sed mkdir mv rm ln mktemp; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'error: native LLVM bootstrap dependency not found: %s\n' "$tool" >&2
        exit 1
    }
done
if [[ "$ninja_cmd" == */* ]]; then
    [[ -x "$ninja_cmd" ]] || {
        printf 'error: native LLVM Ninja is not executable: %s\n' "$ninja_cmd" >&2
        exit 1
    }
else
    resolved_ninja="$(command -v "$ninja_cmd" 2>/dev/null || true)"
    [[ -n "$resolved_ninja" ]] || {
        printf 'error: native LLVM bootstrap dependency not found: %s\n' "$ninja_cmd" >&2
        exit 1
    }
    ninja_cmd="$resolved_ninja"
    unset resolved_ninja
fi
printf 'WHP native LLVM Ninja: %s\n' "$ninja_cmd" >&2

# The normal QEMU build enables compiler caching later in builder.sh. Native
# LLVM is bootstrapped before that handoff, so opt it into the same cache policy
# explicitly. This avoids reparsing LLVM/Clang's large C++ headers on cache hits
# without changing Clang parser semantics or making cache state part of the
# installed toolchain ABI.
COMPILER_CACHE="${COMPILER_CACHE:-auto}"
case "$COMPILER_CACHE" in
    auto|ccache|sccache|none) ;;
    *)
        printf 'error: COMPILER_CACHE must be auto, ccache, sccache, or none: %s\n' \
            "$COMPILER_CACHE" >&2
        exit 1
        ;;
esac

compiler_cache_cmd="${WHP_COMPILER_CACHE_CMD:-}"
if [[ -z "$compiler_cache_cmd" ]]; then
    case "$COMPILER_CACHE" in
        auto)
            compiler_cache_cmd="$(command -v ccache 2>/dev/null || true)"
            if [[ -z "$compiler_cache_cmd" ]]; then
                compiler_cache_cmd="$(command -v sccache 2>/dev/null || true)"
            fi
            ;;
        ccache|sccache)
            compiler_cache_cmd="$(command -v "$COMPILER_CACHE" 2>/dev/null || true)"
            if [[ -z "$compiler_cache_cmd" ]]; then
                printf 'error: requested compiler cache is not installed: %s\n' \
                    "$COMPILER_CACHE" >&2
                exit 1
            fi
            ;;
        none)
            compiler_cache_cmd=""
            ;;
    esac
fi

cmake_compiler_launcher_args=(
    -DCMAKE_C_COMPILER_LAUNCHER=
    -DCMAKE_CXX_COMPILER_LAUNCHER=
)
if [[ -n "$compiler_cache_cmd" ]]; then
    case "$compiler_cache_cmd" in
        *' '*)
            printf 'error: WHP_COMPILER_CACHE_CMD must name one executable: %s\n' \
                "$compiler_cache_cmd" >&2
            exit 1
            ;;
        */*)
            [[ -x "$compiler_cache_cmd" ]] || {
                printf 'error: compiler cache is not executable: %s\n' \
                    "$compiler_cache_cmd" >&2
                exit 1
            }
            ;;
        *)
            resolved_cache="$(command -v "$compiler_cache_cmd" 2>/dev/null || true)"
            [[ -n "$resolved_cache" ]] || {
                printf 'error: compiler cache is not executable: %s\n' \
                    "$compiler_cache_cmd" >&2
                exit 1
            }
            compiler_cache_cmd="$resolved_cache"
            unset resolved_cache
            ;;
    esac

    cache_build_dir="${BUILD_DIR:-$SOURCE_DIR/build}"
    WHP_COMPILER_CACHE_ROOT="${WHP_COMPILER_CACHE_ROOT:-$(dirname -- "$cache_build_dir")/.whp-compiler-cache}"
    cache_tag="$host_kernel-$host_arch"
    cache_base="${compiler_cache_cmd##*/}"
    case "$cache_base" in
        ccache)
            CCACHE_DIR="${CCACHE_DIR:-$WHP_COMPILER_CACHE_ROOT/ccache-$cache_tag}"
            export CCACHE_DIR
            ;;
        sccache)
            SCCACHE_DIR="${SCCACHE_DIR:-$WHP_COMPILER_CACHE_ROOT/sccache-$cache_tag}"
            export SCCACHE_DIR
            ;;
        *)
            printf 'error: unsupported compiler cache command: %s\n' \
                "$compiler_cache_cmd" >&2
            exit 1
            ;;
    esac
    WHP_COMPILER_CACHE_CMD="$compiler_cache_cmd"
    export WHP_COMPILER_CACHE_CMD WHP_COMPILER_CACHE_ROOT
    cmake_compiler_launcher_args=(
        "-DCMAKE_C_COMPILER_LAUNCHER=$compiler_cache_cmd"
        "-DCMAKE_CXX_COMPILER_LAUNCHER=$compiler_cache_cmd"
    )
    printf 'WHP native LLVM compiler cache: %s (%s)\n' \
        "$cache_base" "$WHP_COMPILER_CACHE_ROOT" >&2
elif [[ "$COMPILER_CACHE" == none ]]; then
    CCACHE_DISABLE=1
    export CCACHE_DISABLE
    printf 'WHP native LLVM compiler cache: disabled\n' >&2
fi

cmake_host_args=()
cmake_darwin_runtime_args=()
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
        "-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch"
        "-DCMAKE_OSX_DEPLOYMENT_TARGET=$deployment_target"
    )
    # LLVM's builtins and runtimes are separate ExternalProject configurations.
    # Carry Darwin ABI inputs into both, but keep compiler-rt-only feature
    # policy out of builtins so CMake does not report irrelevant cache entries.
    darwin_external_cmake_args="-DCMAKE_OSX_SYSROOT=$sdkroot;-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch;-DCMAKE_OSX_DEPLOYMENT_TARGET=$deployment_target;-DCMAKE_C_COMPILER_LAUNCHER=$compiler_cache_cmd;-DCMAKE_CXX_COMPILER_LAUNCHER=$compiler_cache_cmd"
    darwin_runtimes_cmake_args="$darwin_external_cmake_args"
    for compiler_rt_option in \
        -DCOMPILER_RT_ENABLE_IOS=OFF \
        -DCOMPILER_RT_ENABLE_MACCATALYST=OFF \
        -DCOMPILER_RT_ENABLE_WATCHOS=OFF \
        -DCOMPILER_RT_ENABLE_TVOS=OFF \
        -DCOMPILER_RT_ENABLE_XROS=OFF \
        -DCOMPILER_RT_BUILD_XRAY=OFF \
        -DCOMPILER_RT_BUILD_CTX_PROFILE=OFF \
        -DCOMPILER_RT_BUILD_MEMPROF=OFF \
        -DCOMPILER_RT_BUILD_ORC=OFF \
        -DCOMPILER_RT_BUILD_GWP_ASAN=OFF \
        -DCOMPILER_RT_INCLUDE_TESTS=OFF \
        -DCOMPILER_RT_BUILD_SANITIZERS=ON \
        -DCOMPILER_RT_BUILD_LIBFUZZER=ON \
        -DCOMPILER_RT_BUILD_PROFILE=ON; do
        darwin_runtimes_cmake_args="${darwin_runtimes_cmake_args};${compiler_rt_option}"
    done
    cmake_darwin_runtime_args=(
        "-DRUNTIMES_CMAKE_ARGS=$darwin_runtimes_cmake_args"
        "-DBUILTINS_CMAKE_ARGS=$darwin_external_cmake_args"
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

# Native LLVM rebuilds already have a linker from the previous successful
# toolchain. On Darwin, reuse that ld64.lld only after proving Apple Clang can
# drive it against the selected SDK. This avoids routing every large Clang/LLVM
# relink through Apple's system ld, while preserving the system linker as the
# cold-bootstrap and incompatibility fallback. Keep input prefetch bounded by
# the existing link-job pool rather than increasing concurrent heavy links.
bootstrap_linker_args=()
bootstrap_linker_name=system
if [[ "$host_os" == macos && -x "$TOOLCHAIN_DIR/bin/ld64.lld" ]]; then
    if printf 'int main(void) { return 0; }\n' |
        PATH="$TOOLCHAIN_DIR/bin:$PATH" \
            "$bootstrap_cxx" -fuse-ld=lld \
            -Wl,--read-workers="$LLVM_LINK_JOBS" \
            -isysroot "$sdkroot" \
            "-mmacosx-version-min=$deployment_target" \
            -x c++ - -o /dev/null >/dev/null 2>&1; then
        PATH="$TOOLCHAIN_DIR/bin:$PATH"
        export PATH
        bootstrap_linker_name="$TOOLCHAIN_DIR/bin/ld64.lld"
        bootstrap_linker_args=(
            "-DLLVM_USE_LINKER=lld"
            "-DCMAKE_EXE_LINKER_FLAGS=-Wl,--read-workers=$LLVM_LINK_JOBS"
            "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--read-workers=$LLVM_LINK_JOBS"
            "-DCMAKE_MODULE_LINKER_FLAGS=-Wl,--read-workers=$LLVM_LINK_JOBS"
        )
    fi
fi
printf 'WHP native LLVM bootstrap linker: %s\n' "$bootstrap_linker_name" >&2

compiler_accepts_native_tune()
{
    local compiler="$1"
    local language="$2"

    printf 'int whp_native_llvm_tune_probe(void) { return 0; }\n' |
        "$compiler" -mtune=native -x "$language" -c - -o /dev/null \
            >/dev/null 2>&1
}

# LLVM itself is a build tool here. -O2 retains Release/NDEBUG semantics while
# reducing expensive optimizer work versus CMake's usual Release -O3. Native
# tuning is scheduling-only and therefore does not raise the generated
# toolchain's minimum ISA the way -mcpu=native or -march=native would.
llvm_bootstrap_cflags='-O2 -DNDEBUG'
llvm_bootstrap_cxxflags='-O2 -DNDEBUG'
if compiler_accepts_native_tune "$bootstrap_cc" c; then
    llvm_bootstrap_cflags="$llvm_bootstrap_cflags -mtune=native"
fi
if compiler_accepts_native_tune "$bootstrap_cxx" c++; then
    llvm_bootstrap_cxxflags="$llvm_bootstrap_cxxflags -mtune=native"
fi
printf 'WHP native LLVM C flags: %s\n' "$llvm_bootstrap_cflags" >&2
printf 'WHP native LLVM C++ flags: %s\n' "$llvm_bootstrap_cxxflags" >&2

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
        arm64|aarch64) printf 'aarch64\n' ;;
        x86_64|amd64) printf 'x86_64\n' ;;
        *) return 1 ;;
    esac
}

canonical_native_target_triple()
{
    local target="$1"
    local target_arch canonical_arch

    [[ "$target" == *-* ]] || return 1
    target_arch="${target%%-*}"
    canonical_arch="$(canonical_native_arch "$target_arch")" || return 1
    printf '%s-%s\n' "$canonical_arch" "${target#*-}"
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
bootstrap_cc_target_canonical="$(canonical_native_target_triple "$bootstrap_cc_target")" || {
    printf 'error: failed to canonicalize native LLVM bootstrap C target: %s\n' \
        "$bootstrap_cc_target" >&2
    exit 1
}
bootstrap_cxx_target_canonical="$(canonical_native_target_triple "$bootstrap_cxx_target")" || {
    printf 'error: failed to canonicalize native LLVM bootstrap C++ target: %s\n' \
        "$bootstrap_cxx_target" >&2
    exit 1
}
llvm_host_triple="$bootstrap_cc_target_canonical"
llvm_default_target_triple="$llvm_host_triple"

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
llvm_enable_projects=clang
llvm_distribution_components='clang;clang-resource-headers;llvm-ar;llvm-ranlib;llvm-nm'
llvm_enable_runtimes=''
llvm_include_runtimes=OFF
if [[ "$host_os" == macos ]]; then
    # Keep the Darwin linker and archive readers on the same LLVM revision as
    # the compiler that emits LTO bitcode. ld64.lld consumes LLVM IR directly,
    # while libLTO remains available for explicit system-ld64 compatibility.
    # compiler-rt also belongs to the same installed compiler runtime family.
    llvm_enable_projects="${llvm_enable_projects};lld"
    llvm_enable_runtimes=compiler-rt
    llvm_include_runtimes=ON
    llvm_distribution_components="${llvm_distribution_components};lld;LTO;builtins;runtimes"
fi
marker="$TOOLCHAIN_DIR/.whp-native-llvm"
expected_marker="$(cat <<EOF
BOOTSTRAP_SCHEMA=8
LLVM_GIT_COMMIT=$llvm_revision
HOST=$host_id
HOST_OS=$host_os
HOST_KERNEL=$host_kernel
HOST_ARCH=$host_arch
LLVM_TARGETS_TO_BUILD=$llvm_target
LLVM_HOST_TRIPLE=$llvm_host_triple
LLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple
LLVM_ENABLE_PROJECTS=$llvm_enable_projects
LLVM_ENABLE_RUNTIMES=$llvm_enable_runtimes
LLVM_INCLUDE_RUNTIMES=$llvm_include_runtimes
LLVM_DISTRIBUTION_COMPONENTS=$llvm_distribution_components
CMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags
CMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags
LLVM_ENABLE_TELEMETRY=OFF
COMPILER_RT_ENABLE_IOS=OFF
COMPILER_RT_ENABLE_MACCATALYST=OFF
COMPILER_RT_ENABLE_WATCHOS=OFF
COMPILER_RT_ENABLE_TVOS=OFF
COMPILER_RT_ENABLE_XROS=OFF
COMPILER_RT_BUILD_XRAY=OFF
COMPILER_RT_BUILD_CTX_PROFILE=OFF
COMPILER_RT_BUILD_MEMPROF=OFF
COMPILER_RT_BUILD_ORC=OFF
COMPILER_RT_BUILD_GWP_ASAN=OFF
COMPILER_RT_INCLUDE_TESTS=OFF
COMPILER_RT_BUILD_SANITIZERS=ON
COMPILER_RT_BUILD_LIBFUZZER=ON
COMPILER_RT_BUILD_PROFILE=ON
BOOTSTRAP_CC=$bootstrap_cc
BOOTSTRAP_CC_VERSION=$bootstrap_cc_version
BOOTSTRAP_CC_TARGET_TRIPLE=$bootstrap_cc_target
BOOTSTRAP_CC_TARGET_TRIPLE_CANONICAL=$bootstrap_cc_target_canonical
BOOTSTRAP_CXX=$bootstrap_cxx
BOOTSTRAP_CXX_VERSION=$bootstrap_cxx_version
BOOTSTRAP_CXX_TARGET_TRIPLE=$bootstrap_cxx_target
BOOTSTRAP_CXX_TARGET_TRIPLE_CANONICAL=$bootstrap_cxx_target_canonical
SDKROOT=$sdkroot
MACOSX_DEPLOYMENT_TARGET=$deployment_target
EOF
)"

usable()
{
    local prefix="$1"
    local target=''
    local ubsan_exe=''
    local objc_exe=''
    local objc_log=''

    [[ -x "$prefix/bin/clang" && -x "$prefix/bin/clang++" ]] || return 1
    [[ -x "$prefix/bin/llvm-ar" && -x "$prefix/bin/llvm-ranlib" &&
       -x "$prefix/bin/llvm-nm" ]] || return 1
    if [[ "$host_os" == macos ]]; then
        [[ -x "$prefix/bin/ld64.lld" ]] || return 1
        [[ -f "$prefix/lib/libLTO.dylib" ]] || return 1
        ubsan_exe="$(mktemp "${TMPDIR:-/tmp}/whp-native-llvm-ubsan.XXXXXX")" ||
            return 1
        if ! printf 'int main(void) { return 0; }\n' |
            "$prefix/bin/clang" -fsanitize=undefined -fuse-ld=lld \
                -isysroot "$sdkroot" \
                "-mmacosx-version-min=$deployment_target" \
                -x c - -o "$ubsan_exe" >/dev/null 2>&1; then
            rm -f "$ubsan_exe"
            return 1
        fi
        rm -f "$ubsan_exe"

        # A Darwin compiler is not usable by QEMU merely because C links. The
        # Cocoa UI is Objective-C, and Clang's runtime link adds -lobjc. Prove
        # that the installed Clang -> ld64.lld path can resolve both libobjc
        # and a system framework from the selected macOS SDK before publishing
        # or reusing the toolchain.
        objc_exe="$(mktemp "${TMPDIR:-/tmp}/whp-native-llvm-objc.XXXXXX")" ||
            return 1
        objc_log="$(mktemp "${TMPDIR:-/tmp}/whp-native-llvm-objc-log.XXXXXX")" || {
            rm -f "$objc_exe"
            return 1
        }
        if ! printf 'int main(void) { return 0; }\n' |
            "$prefix/bin/clang" -fuse-ld=lld \
                -isysroot "$sdkroot" \
                "-mmacosx-version-min=$deployment_target" \
                -fobjc-link-runtime -x objective-c - -framework Cocoa \
                -o "$objc_exe" >/dev/null 2>"$objc_log"; then
            printf 'error: WHP native LLVM cannot link Objective-C against SDK %s\n' \
                "$sdkroot" >&2
            cat "$objc_log" >&2
            rm -f "$objc_exe" "$objc_log"
            return 1
        fi
        rm -f "$objc_exe" "$objc_log"
    fi
    "$prefix/bin/clang" --version >/dev/null 2>&1 || return 1
    "$prefix/bin/clang++" --version >/dev/null 2>&1 || return 1
    target="$(query_target_triple "$prefix/bin/clang")"
    native_target_matches_host "$target" || return 1
    target="$(canonical_native_target_triple "$target" 2>/dev/null || true)"
    [[ "$target" == "$llvm_default_target_triple" ]] || return 1
    target="$(query_target_triple "$prefix/bin/clang++")"
    native_target_matches_host "$target" || return 1
    target="$(canonical_native_target_triple "$target" 2>/dev/null || true)"
    [[ "$target" == "$llvm_default_target_triple" ]] || return 1
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

# Keep the CMake/Ninja graph alive across interrupted builds and LLVM source
# revisions. Re-running CMake updates changed rules in place, while Ninja keeps
# object dependency state and rebuilds only affected outputs. A stale or
# partially installed toolchain is not evidence that the generated build graph
# is corrupt, because installation is staged separately below.
mkdir -p "$(dirname "$TOOLCHAIN_DIR")" "$TOOLCHAIN_WORK_DIR"
cmake_args=(
    -S "$LLVM_SOURCE_DIR/llvm"
    -B "$LLVM_BUILD_DIR"
    -G Ninja
    "-DCMAKE_MAKE_PROGRAM=$ninja_cmd"
    -DCMAKE_BUILD_TYPE=Release
    "-DCMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags"
    "-DCMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags"
    -DCMAKE_C_COMPILER="$bootstrap_cc"
    -DCMAKE_CXX_COMPILER="$bootstrap_cxx"
    "${cmake_compiler_launcher_args[@]}"
    "${bootstrap_linker_args[@]}"
    -DCMAKE_INSTALL_PREFIX="$TOOLCHAIN_DIR"
    -DCMAKE_EXPORT_COMPILE_COMMANDS=OFF
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=OFF
    -DCMAKE_SKIP_INSTALL_ALL_DEPENDENCY=ON
    -DCMAKE_INSTALL_MESSAGE=NEVER
    "-DLLVM_ENABLE_PROJECTS=$llvm_enable_projects"
    "-DLLVM_ENABLE_RUNTIMES=$llvm_enable_runtimes"
    "-DLLVM_TARGETS_TO_BUILD=$llvm_target"
    "-DLLVM_HOST_TRIPLE=$llvm_host_triple"
    "-DLLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple"
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
    "-DLLVM_INCLUDE_RUNTIMES=$llvm_include_runtimes"
    -DLLVM_ENABLE_BINDINGS=OFF
    -DLLVM_ENABLE_TELEMETRY=OFF
    -DCLANG_INCLUDE_TESTS=OFF
    -DCLANG_ENABLE_STATIC_ANALYZER=OFF
    -DLLVM_ENABLE_ZLIB=OFF
    -DLLVM_ENABLE_ZSTD=OFF
    -DLLVM_ENABLE_LIBXML2=OFF
    "${cmake_darwin_runtime_args[@]}"
    "${cmake_host_args[@]}"
)
cmake "${cmake_args[@]}"

if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then
    cmake --build "$LLVM_BUILD_DIR" --target clean "${cmake_parallel_args[@]}"
fi

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
