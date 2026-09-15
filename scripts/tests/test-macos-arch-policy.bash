#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
TEST_DIR="$(mktemp -d "${TMPDIR:-/tmp}/whp-macos-arch-test.XXXXXX")"
trap 'rm -rf "$TEST_DIR"' EXIT

FAKE_CLANG="$TEST_DIR/clang"
TEST_COMPILER_LOG="$TEST_DIR/compiler.log"
export TEST_COMPILER_LOG

cat > "$FAKE_CLANG" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "${TEST_COMPILER_LOG:?}"
if [[ " $* " == *' -arch arm64e '* && "${TEST_ARM64E_SUPPORTED:-1}" != 1 ]]; then
    exit 1
fi
out=''
while (($#)); do
    if [[ "$1" == -o && $# -ge 2 ]]; then
        out="$2"
        shift 2
        continue
    fi
    shift
done
[[ -z "$out" || "$out" == /dev/null ]] || : > "$out"
EOF
chmod +x "$FAKE_CLANG"

# The selector is intentionally sourceable: the macOS wrapper and the native
# LLVM bootstrap can share one Apple architecture policy without conflating
# arm64e with a separate LLVM backend.
source "$SOURCE_DIR/scripts/macos-arch-policy.bash"

# Auto must stay on the established arm64 ABI until TCG handles pointer
# authentication at both C -> JIT and JIT -> C call boundaries.  Merely having
# a compiler and SDK that can link arm64e is not enough.
: > "$TEST_COMPILER_LOG"
selected="$(TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64)"
[[ "$selected" == arm64 ]]
[[ ! -s "$TEST_COMPILER_LOG" ]]

# Explicit arm64e remains a probe-gated development lane.
: > "$TEST_COMPILER_LOG"
selected="$(TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=arm64e \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64)"
[[ "$selected" == arm64e ]]
grep -Fq -- '-arch arm64e' "$TEST_COMPILER_LOG"

if TEST_ARM64E_SUPPORTED=0 WHP_MACOS_ARCH=arm64e \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 \
        >"$TEST_DIR/explicit.out" 2>"$TEST_DIR/explicit.err"; then
    printf '%s\n' 'error: explicit arm64e unexpectedly succeeded' >&2
    exit 1
fi
grep -Fq 'requested arm64e' "$TEST_DIR/explicit.err"

: > "$TEST_COMPILER_LOG"
selected="$(TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 x86_64)"
[[ "$selected" == x86_64 ]]
[[ ! -s "$TEST_COMPILER_LOG" ]]

if WHP_MACOS_ARCH=bogus \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 \
        >/dev/null 2>"$TEST_DIR/invalid.err"; then
    printf '%s\n' 'error: invalid architecture policy unexpectedly succeeded' >&2
    exit 1
fi
grep -Fq 'WHP_MACOS_ARCH must be auto, arm64, arm64e, or x86_64' \
    "$TEST_DIR/invalid.err"

: > "$TEST_COMPILER_LOG"
selected="$(NATIVE_LLVM_LDFLAG=-fuse-ld=lld \
    TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=arm64e \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64)"
[[ "$selected" == arm64e ]]
grep -Fq -- '-fuse-ld=lld' "$TEST_COMPILER_LOG"

# Integration contract: the macOS QEMU wrapper owns the final Apple -arch
# choice and applies it consistently to C, C++, Objective-C, and links.
macos_builder="$SOURCE_DIR/scripts/macos-builder.bash"
grep -Fq 'source "$SCRIPT_DIR/macos-arch-policy.bash"' "$macos_builder"
grep -Fq 'whp_select_macos_arch "$CC" "$SDKROOT"' "$macos_builder"
grep -Fq 'whp_append_flag "$variable" "-arch $WHP_MACOS_ARCH"' "$macos_builder"
grep -Fq "*' -arch '*)" "$macos_builder"

printf 'macOS architecture policy tests: passed\n'
