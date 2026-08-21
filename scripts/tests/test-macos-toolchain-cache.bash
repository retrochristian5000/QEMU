#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/whp-macos-toolchain-cache-test.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

FAKE_BIN="$TEST_DIR/bin"
SDKROOT_FIXTURE="$TEST_DIR/MacOSX15.0.sdk"
RESOURCE_DIR="$TEST_DIR/clang-resource"
MANIFEST="$TEST_DIR/build/.whp-macos-toolchain"
PROBE_DIR="$TEST_DIR/build/.whp-macos-toolchain.d"
COMPILE_LOG="$TEST_DIR/compiler-probes.log"
CLANG="$FAKE_BIN/clang"
CLANGXX="$FAKE_BIN/clang++"

mkdir -p "$FAKE_BIN" "$SDKROOT_FIXTURE" "$RESOURCE_DIR" "$(dirname "$MANIFEST")"
: > "$COMPILE_LOG"

cat > "$FAKE_BIN/uname" <<'EOF'
#!/usr/bin/env bash
case "${1:-}" in
    -m) printf 'arm64\n' ;;
    -s) printf 'Darwin\n' ;;
    *) printf 'Darwin\n' ;;
esac
EOF

cat > "$FAKE_BIN/xcrun" <<'EOF'
#!/usr/bin/env bash
if [[ "${1:-}" == "--sdk" ]]; then
    sdk="$2"
    shift 2
else
    sdk=macosx
fi

case "${1:-}" in
    --show-sdk-version)
        printf '15.0\n'
        ;;
    lipo)
        if [[ "${2:-}" == "-archs" ]]; then
            printf 'arm64\n'
            exit 0
        fi
        exit 1
        ;;
    *)
        exit 1
        ;;
esac
EOF

cat > "$CLANG" <<'EOF'
#!/usr/bin/env bash

for argument in "$@"; do
    case "$argument" in
        --version)
            printf '%s\n' "${TEST_COMPILER_VERSION:-Apple clang version 16.0.0}"
            exit 0
            ;;
        -print-target-triple|-dumpmachine)
            printf 'arm64-apple-darwin24.0.0\n'
            exit 0
            ;;
        -print-resource-dir)
            printf '%s\n' "$TEST_RESOURCE_DIR"
            exit 0
            ;;
    esac
done

for argument in "$@"; do
    if [[ "$argument" == -### ]]; then
        exit 0
    fi
done

output=""
previous=""
for argument in "$@"; do
    if [[ "$previous" == -o ]]; then
        output="$argument"
        break
    fi
    previous="$argument"
done

if [[ -n "$output" ]]; then
    mkdir -p "$(dirname "$output")"
    printf 'fake Mach-O output\n' > "$output"
    chmod +x "$output"
    printf 'compile\n' >> "$TEST_COMPILE_LOG"
fi
exit 0
EOF
cp "$CLANG" "$CLANGXX"

chmod +x "$FAKE_BIN/uname" "$FAKE_BIN/xcrun" "$CLANG" "$CLANGXX"

export PATH="$FAKE_BIN:$PATH"
export TEST_RESOURCE_DIR="$RESOURCE_DIR"
export TEST_COMPILE_LOG="$COMPILE_LOG"
export TEST_COMPILER_VERSION='Apple clang version 16.0.0'

run_verifier()
{
    local output_file="$1"
    shift
    env \
        CC="$CLANG" \
        CXX="$CLANGXX" \
        OBJC="$CLANG" \
        CC_FOR_BUILD="$CLANG" \
        SDKROOT="$SDKROOT_FIXTURE" \
        MACOS_SDK_VERSION=15.0 \
        MACOSX_DEPLOYMENT_TARGET=15.0 \
        MACOS_COMPILER_MANIFEST="$MANIFEST" \
        MACOS_COMPILER_PROBE_DIR="$PROBE_DIR" \
        "$@" \
        bash "$SOURCE_DIR/scripts/verify-macos-toolchain.sh" \
        >"$output_file" 2>&1
}

probe_count()
{
    wc -l < "$COMPILE_LOG" | tr -d '[:space:]'
}

first_output="$TEST_DIR/first.out"
run_verifier "$first_output"
first_count="$(probe_count)"
if [[ "$first_count" != 4 ]]; then
    printf 'error: initial macOS toolchain verification ran %s compile probes, expected 4\n' \
        "$first_count" >&2
    cat "$first_output" >&2
    exit 1
fi

second_output="$TEST_DIR/second.out"
run_verifier "$second_output"
second_count="$(probe_count)"
if [[ "$second_count" != "$first_count" ]]; then
    printf '%s\n' \
        'error: unchanged macOS toolchain verification reran compile/link probes.' \
        "first probe count:  $first_count" \
        "second probe count: $second_count" >&2
    cat "$second_output" >&2
    exit 1
fi
if ! grep -Fq 'Reused cached macOS compiler toolchain verification:' "$second_output"; then
    printf 'error: unchanged macOS toolchain verification did not report a cache hit\n' >&2
    cat "$second_output" >&2
    exit 1
fi

# Probe executables are diagnostics, not cache identity. Removing them must not
# turn an unchanged verified compiler/SDK tuple into another expensive probe.
rm -rf "$PROBE_DIR"
third_output="$TEST_DIR/third.out"
run_verifier "$third_output"
third_count="$(probe_count)"
if [[ "$third_count" != "$first_count" ]]; then
    printf 'error: missing diagnostic probe outputs invalidated the toolchain cache\n' >&2
    cat "$third_output" >&2
    exit 1
fi

flags_output="$TEST_DIR/flags.out"
run_verifier "$flags_output" CFLAGS=-DWHPCacheInvalidation=1
flags_count="$(probe_count)"
if [[ "$flags_count" -le "$third_count" ]]; then
    printf 'error: changed CFLAGS did not invalidate the macOS toolchain cache\n' >&2
    cat "$flags_output" >&2
    exit 1
fi

export TEST_COMPILER_VERSION='Apple clang version 16.0.1'
version_output="$TEST_DIR/version.out"
run_verifier "$version_output" CFLAGS=-DWHPCacheInvalidation=1
version_count="$(probe_count)"
if [[ "$version_count" -le "$flags_count" ]]; then
    printf 'error: changed compiler version did not invalidate the macOS toolchain cache\n' >&2
    cat "$version_output" >&2
    exit 1
fi

# A manifest without its matching verified-input identity must fail closed and
# re-probe rather than trusting an incomplete cache record.
rm -f "$MANIFEST.inputs"
missing_identity_output="$TEST_DIR/missing-identity.out"
run_verifier "$missing_identity_output" CFLAGS=-DWHPCacheInvalidation=1
missing_identity_count="$(probe_count)"
if [[ "$missing_identity_count" -le "$version_count" ]]; then
    printf 'error: missing macOS toolchain cache identity did not force verification\n' >&2
    cat "$missing_identity_output" >&2
    exit 1
fi

printf 'macOS toolchain cache tests: passed\n'
