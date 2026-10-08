#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/whp-macos-sdk-test.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

FAKE_BIN="$TEST_DIR/bin"
ACTIVE_SDK="$TEST_DIR/MacOSX15.0.sdk"
SELECTED_SDK="$TEST_DIR/MacOSX13.3.sdk"
BETA_SDK="$TEST_DIR/MacOSX16.0.sdk"
DEVELOPER_DIR_FIXTURE="$TEST_DIR/Developer"
CLANG="$FAKE_BIN/clang"
CLANGXX="$FAKE_BIN/clang++"
STRIP="$FAKE_BIN/strip"

mkdir -p "$FAKE_BIN" "$ACTIVE_SDK" "$SELECTED_SDK" "$BETA_SDK" \
    "$DEVELOPER_DIR_FIXTURE"
: > "$ACTIVE_SDK/SDKSettings.json"
: > "$SELECTED_SDK/SDKSettings.json"
: > "$BETA_SDK/SDKSettings.json"

cat > "$FAKE_BIN/uname" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
    -s) printf 'Darwin\n' ;;
    -m) printf 'arm64\n' ;;
    *) printf 'Darwin\n' ;;
esac
EOF

cat > "$FAKE_BIN/xcode-select" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-p" ]]; then
    printf '%s\n' "$TEST_DEVELOPER_DIR"
    exit 0
fi
exit 1
EOF

cat > "$FAKE_BIN/sw_vers" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "-productVersion" ]]; then
    printf '15.0\n'
    exit 0
fi
exit 1
EOF

cat > "$FAKE_BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
sdk="${SDKROOT:-macosx}"
if [[ "${1:-}" == "--sdk" ]]; then
    sdk="$2"
    shift 2
fi

case "${1:-}" in
    --show-sdk-path)
        case "$sdk" in
            macosx) printf '%s\n' "$TEST_ACTIVE_SDK" ;;
            *) printf '%s\n' "$sdk" ;;
        esac
        ;;
    --show-sdk-version)
        case "$sdk" in
            "$TEST_SELECTED_SDK") printf '13.3\n' ;;
            "$TEST_BETA_SDK") printf '16.0\n' ;;
            macosx|"$TEST_ACTIVE_SDK") printf '15.0\n' ;;
            *) exit 1 ;;
        esac
        ;;
    --find)
        case "${2:-}" in
            clang) printf '%s\n' "$TEST_CLANG" ;;
            clang++) printf '%s\n' "$TEST_CLANGXX" ;;
            strip) printf '%s\n' "$TEST_STRIP" ;;
            *) exit 1 ;;
        esac
        ;;
    lipo)
        exit 1
        ;;
    *)
        exit 1
        ;;
esac
EOF

cat > "$FAKE_BIN/plutil" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" != "-extract" || "${3:-}" != "raw" ]]; then
    exit 1
fi
key="$2"
settings_file="${!#}"
case "$settings_file:$key" in
    "$TEST_SELECTED_SDK/SDKSettings.json:SupportedTargets.macosx.DefaultDeploymentTarget")
        printf '13.3\n' ;;
    "$TEST_SELECTED_SDK/SDKSettings.json:SupportedTargets.macosx.MinimumDeploymentTarget")
        printf '11.0\n' ;;
    "$TEST_SELECTED_SDK/SDKSettings.json:SupportedTargets.macosx.MaximumDeploymentTarget")
        printf '13.3.99\n' ;;
    "$TEST_ACTIVE_SDK/SDKSettings.json:SupportedTargets.macosx.DefaultDeploymentTarget")
        printf '15.0\n' ;;
    "$TEST_ACTIVE_SDK/SDKSettings.json:SupportedTargets.macosx.MinimumDeploymentTarget")
        printf '11.0\n' ;;
    "$TEST_ACTIVE_SDK/SDKSettings.json:SupportedTargets.macosx.MaximumDeploymentTarget")
        printf '15.0.99\n' ;;
    "$TEST_BETA_SDK/SDKSettings.json:SupportedTargets.macosx.DefaultDeploymentTarget")
        printf '16.0\n' ;;
    "$TEST_BETA_SDK/SDKSettings.json:SupportedTargets.macosx.MinimumDeploymentTarget")
        printf '11.0\n' ;;
    "$TEST_BETA_SDK/SDKSettings.json:SupportedTargets.macosx.MaximumDeploymentTarget")
        printf '16.0.99\n' ;;
    *) exit 1 ;;
esac
EOF

cat > "$CLANG" <<'EOF'
#!/usr/bin/env bash
for arg in "$@"; do
    case "$arg" in
        -Wl,--read-workers=*)
            if [[ "${TEST_LLD_READ_WORKERS:-accept}" == reject ]]; then
                exit 1
            fi
            ;;
    esac
done
case "${1:-}" in
    --version) printf 'Apple clang version 16.0.0\n' ;;
    -dumpmachine|-print-target-triple)
        printf '%s\n' "${TEST_TARGET_TRIPLE:-arm64-apple-darwin24.0.0}"
        ;;
    -print-resource-dir) printf '/tmp\n' ;;
    *) exit 0 ;;
esac
EOF
cp "$CLANG" "$CLANGXX"
cat > "$STRIP" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

cat > "$FAKE_BIN/build-bash" <<EOF
#!/usr/bin/env bash
for argument in "\$@"; do
    if [[ "\$argument" == "$SOURCE_DIR/builder.sh" ]]; then
        printf 'LDFLAGS=%s\n' "\${LDFLAGS:-}"
        printf 'builder reached\n'
        exit 0
    fi
done
exec /bin/bash "\$@"
EOF

chmod +x "$FAKE_BIN/uname" "$FAKE_BIN/xcode-select" \
    "$FAKE_BIN/sw_vers" "$FAKE_BIN/xcrun" "$FAKE_BIN/plutil" \
    "$FAKE_BIN/build-bash" "$CLANG" "$CLANGXX" "$STRIP"

export PATH="$FAKE_BIN:$PATH"
export TEST_ACTIVE_SDK="$ACTIVE_SDK"
export TEST_SELECTED_SDK="$SELECTED_SDK"
export TEST_BETA_SDK="$BETA_SDK"
export TEST_DEVELOPER_DIR="$DEVELOPER_DIR_FIXTURE"
export TEST_CLANG="$CLANG"
export TEST_CLANGXX="$CLANGXX"
export TEST_STRIP="$STRIP"

non_darwin_output="$TEST_DIR/non-darwin-output"
if TEST_TARGET_TRIPLE=arm64-unknown-linux-gnu \
   CC="$CLANG" CXX="$CLANGXX" OBJC="$CLANG" \
   CC_FOR_BUILD="$CLANG" CXX_FOR_BUILD="$CLANGXX" \
   bash --noprofile --norc -c \
       'source "$1/scripts/macos-compiler-policy.bash"' _ "$SOURCE_DIR" \
       >"$non_darwin_output" 2>&1; then
    printf '%s\n' \
        'error: macOS compiler policy accepted an arm64 non-Darwin target triple.' >&2
    cat "$non_darwin_output" >&2
    exit 1
fi
if ! grep -Fq 'Apple Darwin/macOS target triple' "$non_darwin_output"; then
    printf '%s\n' \
        'error: macOS compiler policy did not diagnose the non-Darwin target ABI.' >&2
    cat "$non_darwin_output" >&2
    exit 1
fi

wrapper_output="$TEST_DIR/wrapper-output"
if SDKROOT="$SELECTED_SDK" \
   MACOSX_DEPLOYMENT_TARGET=14.0 \
   BUILD_DIR="$TEST_DIR/wrapper-build" \
   OPENBIOS_TOOLS_DIR="$TEST_DIR/wrapper-tools" \
   WHP_BUILD_BASH="$FAKE_BIN/build-bash" \
   bash "$SOURCE_DIR/scripts/macos-builder.bash" \
       >"$wrapper_output" 2>&1; then
    printf '%s\n' \
        'error: macOS wrapper accepted a deployment target newer than the selected SDK.' >&2
    cat "$wrapper_output" >&2
    exit 1
fi
if ! grep -Fq \
    'deployment target 14.0 is newer than the selected SDK maximum 13.3.99' \
    "$wrapper_output"; then
    printf '%s\n' \
        'error: macOS wrapper did not diagnose the selected SDK deployment range.' >&2
    cat "$wrapper_output" >&2
    exit 1
fi

# When the running OS is newer than an explicitly selected older SDK, the
# automatic deployment target should clamp to the SDK default instead of
# rejecting the build.
older_sdk_output="$TEST_DIR/older-sdk-output"
if ! SDKROOT="$SELECTED_SDK" \
   MACOSX_DEPLOYMENT_TARGET= \
   BUILD_DIR="$TEST_DIR/older-sdk-build" \
   OPENBIOS_TOOLS_DIR="$TEST_DIR/older-sdk-tools" \
   WHP_BUILD_BASH="$FAKE_BIN/build-bash" \
   bash "$SOURCE_DIR/scripts/macos-builder.bash" \
       >"$older_sdk_output" 2>&1; then
    printf '%s\n' \
        'error: macOS wrapper rejected an older SDK on a newer host.' >&2
    cat "$older_sdk_output" >&2
    exit 1
fi
grep -Fq 'macOS deployment target: 13.3 (sdk-default)' "$older_sdk_output"
grep -Fq 'builder reached' "$older_sdk_output"

# A beta/newer SDK on an older host should keep the host runtime as the
# automatic deployment target so build-time executables remain runnable.
beta_sdk_output="$TEST_DIR/beta-sdk-output"
if ! SDKROOT="$BETA_SDK" \
   MACOSX_DEPLOYMENT_TARGET= \
   BUILD_DIR="$TEST_DIR/beta-sdk-build" \
   OPENBIOS_TOOLS_DIR="$TEST_DIR/beta-sdk-tools" \
   WHP_BUILD_BASH="$FAKE_BIN/build-bash" \
   bash "$SOURCE_DIR/scripts/macos-builder.bash" \
       >"$beta_sdk_output" 2>&1; then
    printf '%s\n' \
        'error: macOS wrapper rejected a newer SDK on an older host.' >&2
    cat "$beta_sdk_output" >&2
    exit 1
fi
grep -Fq 'macOS deployment target: 15.0 (host)' "$beta_sdk_output"
grep -Fq 'builder reached' "$beta_sdk_output"

# The generic stage consumes macOS policy resolved by the wrapper; it no longer
# rediscovers SDK/compiler identity.  Supply that resolved state explicitly.
stage_output="$TEST_DIR/stage-output"
SDKROOT="$SELECTED_SDK" \
MACOS_SDK_VERSION=13.3 \
MACOSX_DEPLOYMENT_TARGET=13.0 \
DEVELOPER_DIR="$DEVELOPER_DIR_FIXTURE" \
CC="$CLANG" CXX="$CLANGXX" OBJC="$CLANG" \
CC_FOR_BUILD="$CLANG" CXX_FOR_BUILD="$CLANGXX" OBJC_FOR_BUILD="$CLANG" \
STRIP_FOR_BUILD="$STRIP" \
BUILD_DIR="$TEST_DIR/stage-build" \
OPENBIOS_TOOLS_DIR="$TEST_DIR/stage-tools" \
SOURCE_DIR="$SOURCE_DIR" \
bash --noprofile --norc -c '
    source "$SOURCE_DIR/scripts/whp-build/stages.bash"
    whp_prepare_build
    printf "selected SDK version: %s\n" "$MACOS_SDK_VERSION"
' >"$stage_output" 2>&1
if ! grep -Fq 'selected SDK version: 13.3' "$stage_output"; then
    printf '%s\n' \
        'error: build stages changed the SDK identity resolved by the wrapper.' >&2
    cat "$stage_output" >&2
    exit 1
fi

legacy_build="$TEST_DIR/legacy-owned-build"
mkdir -p "$legacy_build"
cat > "$legacy_build/.whp-macos-build-identity" <<EOF
SCHEMA=3
SOURCE_DIR=$SOURCE_DIR
BUILD_DIR=$legacy_build
PROCESS_ARCH=aarch64
HOST_ARCH=aarch64
EOF

if ! SOURCE_DIR="$SOURCE_DIR" LEGACY_BUILD="$legacy_build" \
    bash --noprofile --norc -c '
        source "$SOURCE_DIR/scripts/macos-build-hygiene.bash"
        whp_build_tree_owned "$LEGACY_BUILD"
        [[ "$(whp_recorded_host_arch "$LEGACY_BUILD/.whp-macos-build-identity")" == arm64 ]]
    '; then
    printf '%s\n' \
        'error: legacy macOS WHP ownership identity was not accepted for arm64 migration.' >&2
    exit 1
fi

foreign_build="$TEST_DIR/foreign-build"
mkdir -p "$foreign_build"
cat > "$foreign_build/.whp-macos-build-identity" <<EOF
SCHEMA=3
SOURCE_DIR=$TEST_DIR/not-this-checkout
HOST_ARCH=arm64
EOF
if SOURCE_DIR="$SOURCE_DIR" FOREIGN_BUILD="$foreign_build" \
    bash --noprofile --norc -c '
        source "$SOURCE_DIR/scripts/macos-build-hygiene.bash"
        whp_build_tree_owned "$FOREIGN_BUILD"
    '; then
    printf '%s\n' \
        'error: macOS ownership guard accepted an identity from another source checkout.' >&2
    exit 1
fi

# A non-bootstrap Clang installation may carry its own LLVM archive tools.
# Prefer them only when the complete archive family is available beside the
# selected compiler.  A partial family must fall back to Apple's tools instead
# of mixing object/archive toolchains.
for tool in llvm-ar llvm-ranlib llvm-nm; do
    cat > "$FAKE_BIN/$tool" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
    chmod +x "$FAKE_BIN/$tool"
done

llvm_archive_output="$TEST_DIR/llvm-archive-output"
if ! AR= RANLIB= NM= \
   SDKROOT="$SELECTED_SDK" \
   MACOSX_DEPLOYMENT_TARGET=13.0 \
   BUILD_DIR="$TEST_DIR/llvm-archive-build" \
   OPENBIOS_TOOLS_DIR="$TEST_DIR/llvm-archive-tools" \
   WHP_BUILD_BASH="$FAKE_BIN/build-bash" \
   bash "$SOURCE_DIR/scripts/macos-builder.bash" \
       >"$llvm_archive_output" 2>&1; then
    printf '%s\n' \
        'error: macOS wrapper rejected a complete sibling LLVM archive family.' >&2
    cat "$llvm_archive_output" >&2
    exit 1
fi
grep -Fq "QEMU archiver:           $FAKE_BIN/llvm-ar" "$llvm_archive_output"
grep -Fq "QEMU archive indexer:    $FAKE_BIN/llvm-ranlib" "$llvm_archive_output"
grep -Fq "QEMU symbol reader:      $FAKE_BIN/llvm-nm" "$llvm_archive_output"

rm -f "$FAKE_BIN/llvm-ranlib"
partial_archive_output="$TEST_DIR/partial-archive-output"
if ! AR= RANLIB= NM= \
   SDKROOT="$SELECTED_SDK" \
   MACOSX_DEPLOYMENT_TARGET=13.0 \
   BUILD_DIR="$TEST_DIR/partial-archive-build" \
   OPENBIOS_TOOLS_DIR="$TEST_DIR/partial-archive-tools" \
   WHP_BUILD_BASH="$FAKE_BIN/build-bash" \
   bash "$SOURCE_DIR/scripts/macos-builder.bash" \
       >"$partial_archive_output" 2>&1; then
    printf '%s\n' \
        'error: macOS wrapper rejected the portable archive-tool fallback.' >&2
    cat "$partial_archive_output" >&2
    exit 1
fi
grep -Fq 'QEMU archiver:           /usr/bin/ar' "$partial_archive_output"
grep -Fq 'QEMU archive indexer:    /usr/bin/ranlib' "$partial_archive_output"
grep -Fq 'QEMU symbol reader:      /usr/bin/nm' "$partial_archive_output"

# Darwin's late Meson native file used to force /usr/bin/ar, nm, and ranlib
# after build.sh had selected a coherent native LLVM tool family.  Keep Apple
# tools as PATH-independent fallbacks in the wrapper, preserve explicit
# selections, and allow a complete compiler-sibling LLVM archive family to win.
# The later native file must remain unable to overwrite that decision.
macos_builder="$SOURCE_DIR/scripts/macos-builder.bash"
darwin_native="$SOURCE_DIR/configs/meson/darwin.txt"
for expected in \
    'export AR="${AR:-/usr/bin/ar}"' \
    'export NM="${NM:-/usr/bin/nm}"' \
    'export RANLIB="${RANLIB:-/usr/bin/ranlib}"' \
    'export STRIP="${STRIP:-/usr/bin/strip}"' \
    'export LIPO="${LIPO:-/usr/bin/lipo}"'; do
    if ! grep -Fq "$expected" "$macos_builder"; then
        printf 'error: missing Darwin tool default: %s\n' "$expected" >&2
        exit 1
    fi
done
if grep -Eq '^(ar|nm|ranlib|strip)[[:space:]]*=' "$darwin_native"; then
    printf '%s\n' \
        'error: Darwin native file overrides configure-selected archive tools.' >&2
    cat "$darwin_native" >&2
    exit 1
fi

# Native LLVM's --read-workers is optional: older / threadless ld64.lld
# builds must not receive it, while the supported linker keeps it. The tests
# capture the exported linker command actually handed to builder.sh.
native_tools="$TEST_DIR/native-llvm"
mkdir -p "$native_tools/bin"
printf '#!/bin/sh\nexit 0\n' > "$native_tools/bin/ld64.lld"
chmod +x "$native_tools/bin/ld64.lld"

linker_env=(
    SDKROOT="$SELECTED_SDK"
    MACOSX_DEPLOYMENT_TARGET=13.0
    WHP_BUILD_BASH="$FAKE_BIN/build-bash"
    NATIVE_LLVM_DIR="$native_tools"
    LD="$native_tools/bin/ld64.lld"
    NATIVE_LLVM_LDFLAG=-fuse-ld=lld
    CC="$CLANG"
    CXX="$CLANGXX"
)
link_reject="$TEST_DIR/llvm-reject-read-workers"
if ! env "${linker_env[@]}" TEST_LLD_READ_WORKERS=reject \
    JOBS=3 BUILD_DIR="$TEST_DIR/linker-reject-build" \
    OPENBIOS_TOOLS_DIR="$TEST_DIR/linker-reject-tools" \
    bash "$SOURCE_DIR/scripts/macos-builder.bash" > "$link_reject" 2>&1; then
    cat "$link_reject" >&2
    exit 1
fi
grep -Fq 'omitting optional link prefetch' "$link_reject"
grep -Fq -- '-Wl,-dead_strip' "$link_reject"
if grep '^LDFLAGS=' "$link_reject" | grep -Eq -- '(--read-workers|-Wl,-O2)'; then
    printf 'error: unsupported LLVM LDFLAGS leaked into the host build\n' >&2
    exit 1
fi

link_accept="$TEST_DIR/llvm-accept-read-workers"
env "${linker_env[@]}" TEST_LLD_READ_WORKERS=accept \
    JOBS=3 BUILD_DIR="$TEST_DIR/linker-accept-build" \
    OPENBIOS_TOOLS_DIR="$TEST_DIR/linker-accept-tools" \
    bash "$SOURCE_DIR/scripts/macos-builder.bash" > "$link_accept" 2>&1
grep '^LDFLAGS=' "$link_accept" | grep -Fq -- '-Wl,--read-workers=3'
if grep '^LDFLAGS=' "$link_accept" | grep -Fq -- '-Wl,-O2'; then
    printf 'error: Apple-only -O2 was passed to Mach-O LLD\n' >&2
    exit 1
fi

link_zero="$TEST_DIR/llvm-zero-read-workers"
env "${linker_env[@]}" NATIVE_LLVM_READ_WORKERS=0 \
    TEST_LLD_READ_WORKERS=reject JOBS=3 \
    BUILD_DIR="$TEST_DIR/linker-zero-build" \
    OPENBIOS_TOOLS_DIR="$TEST_DIR/linker-zero-tools" \
    bash "$SOURCE_DIR/scripts/macos-builder.bash" > "$link_zero" 2>&1
if grep '^LDFLAGS=' "$link_zero" | grep -Fq -- '--read-workers'; then
    printf 'error: explicit zero must omit optional LLD workers entirely\n' >&2
    exit 1
fi

link_forced="$TEST_DIR/llvm-forced-read-workers"
if env "${linker_env[@]}" NATIVE_LLVM_READ_WORKERS=4 \
    TEST_LLD_READ_WORKERS=reject JOBS=3 \
    BUILD_DIR="$TEST_DIR/linker-forced-build" \
    OPENBIOS_TOOLS_DIR="$TEST_DIR/linker-forced-tools" \
    bash "$SOURCE_DIR/scripts/macos-builder.bash" > "$link_forced" 2>&1; then
    printf 'error: unsupported explicit LLD read workers were silently accepted\n' >&2
    exit 1
fi
grep -Fq 'does not accept --read-workers=4' "$link_forced"

# Bare -threads is not the LLVM Mach-O --threads=N option. Reject inherited
# linker flags *before* fake Clang can silently accept them in a smoke test.
bad_thread_flags=(
    '-threads'
    '-threads=2'
    '-Wl,-threads'
    '-Wl,-threads=2'
    '-Wl,-threads,2'
    '-Xlinker -threads'
    '-Wl,--threads'
)
for i in "${!bad_thread_flags[@]}"; do
    bad_flag="${bad_thread_flags[$i]}"
    bad_output="$TEST_DIR/invalid-thread-option-$i.log"
    if env "${linker_env[@]}" LDFLAGS="$bad_flag" \
        BUILD_DIR="$TEST_DIR/invalid-thread-option-$i" \
        OPENBIOS_TOOLS_DIR="$TEST_DIR/invalid-thread-tools-$i" \
        bash "$SOURCE_DIR/scripts/macos-builder.bash" > "$bad_output" 2>&1; then
        printf 'error: invalid Mach-O thread flag accepted: %s\n' "$bad_flag" >&2
        exit 1
    fi
    grep -Fq 'unsupported Mach-O linker thread flag in LDFLAGS' "$bad_output"
    grep -Fq 'uses --threads=N, not -threads' "$bad_output"
done
printf 'macOS SDK selection tests: passed\n'
