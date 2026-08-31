#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/whp-macos-sdk-test.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

FAKE_BIN="$TEST_DIR/bin"
ACTIVE_SDK="$TEST_DIR/MacOSX15.0.sdk"
SELECTED_SDK="$TEST_DIR/MacOSX13.3.sdk"
DEVELOPER_DIR_FIXTURE="$TEST_DIR/Developer"
CLANG="$FAKE_BIN/clang"
CLANGXX="$FAKE_BIN/clang++"
STRIP="$FAKE_BIN/strip"

mkdir -p "$FAKE_BIN" "$ACTIVE_SDK" "$SELECTED_SDK" \
    "$DEVELOPER_DIR_FIXTURE"

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

cat > "$CLANG" <<'EOF'
#!/usr/bin/env bash
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
        printf 'builder reached\n'
        exit 0
    fi
done
exec /bin/bash "\$@"
EOF

chmod +x "$FAKE_BIN/uname" "$FAKE_BIN/xcode-select" \
    "$FAKE_BIN/sw_vers" "$FAKE_BIN/xcrun" "$FAKE_BIN/build-bash" \
    "$CLANG" "$CLANGXX" "$STRIP"

export PATH="$FAKE_BIN:$PATH"
export TEST_ACTIVE_SDK="$ACTIVE_SDK"
export TEST_SELECTED_SDK="$SELECTED_SDK"
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
    'deployment target 14.0 is newer than SDK 13.3' "$wrapper_output"; then
    printf '%s\n' \
        'error: macOS wrapper did not diagnose the selected SDK version.' >&2
    cat "$wrapper_output" >&2
    exit 1
fi

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

printf 'macOS SDK selection tests: passed\n'