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
source_text="$(cat)"
# The fake driver cannot preprocess, so require the regression fixture to
# contain ABI feature checks before simulating Clang's accept/reject decision.
[[ "$source_text" == *'__arm64e__'* &&
   "$source_text" == *'__PTRAUTH__'* &&
   "$source_text" == *'__has_feature(ptrauth_calls)'* &&
   "$source_text" == *'int (*volatile callback)(void)'* ]] || exit 1
if [[ " $* " == *' -arch arm64e '* &&
      "${TEST_ARM64E_PTRAUTH:-1}" != 1 ]]; then
    exit 1
fi
if [[ " $* " == *' -arch arm64e '* && "${TEST_ARM64E_SUPPORTED:-1}" != 1 ]]; then
    exit 1
fi
if [[ " $* " == *' -x c++ '* && "${TEST_ARM64E_CXX_SUPPORTED:-1}" != 1 ]]; then
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
if [[ -n "$out" && "$out" != /dev/null ]]; then
    printf '%s\n' '#!/bin/sh' 'exit "${TEST_ARM64E_RUNTIME:-0}"' > "$out"
    chmod +x "$out"
fi
EOF
chmod +x "$FAKE_CLANG"

# The selector is intentionally sourceable: the macOS wrapper and the native
# LLVM bootstrap can share one Apple architecture policy without conflating
# arm64e with a separate LLVM backend.
source "$SOURCE_DIR/scripts/macos-arch-policy.bash"

# Auto selects arm64e only if both C and C++ compile/link/run PAC calls.
: > "$TEST_COMPILER_LOG"
selected="$(TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 "$FAKE_CLANG")"
[[ "$selected" == arm64e ]]
grep -Fq -- '-x c -' "$TEST_COMPILER_LOG"
grep -Fq -- '-x c++ -' "$TEST_COMPILER_LOG"

# An unusable macOS runtime must fall back even if compilation works.
selected="$(TEST_ARM64E_RUNTIME=1 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 "$FAKE_CLANG")"
[[ "$selected" == arm64 ]]

# An incorrect ABI on either compiler must also fall back.
selected="$(TEST_ARM64E_PTRAUTH=0 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 "$FAKE_CLANG")"
[[ "$selected" == arm64 ]]
selected="$(TEST_ARM64E_CXX_SUPPORTED=0 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 "$FAKE_CLANG")"
[[ "$selected" == arm64 ]]

# An LLD linker without the authenticated-fixup opt-in is never auto-selected.
: > "$TEST_COMPILER_LOG"
selected="$(NATIVE_LLVM_LDFLAG=-fuse-ld=lld WHP_ARM64E_USE_LLD=0 \
    WHP_MACOS_ARCH=auto whp_select_macos_arch \
    "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 "$FAKE_CLANG")"
[[ "$selected" == arm64 ]]
[[ ! -s "$TEST_COMPILER_LOG" ]]

# ASan retains the established arm64 lane in automatic mode.
: > "$TEST_COMPILER_LOG"
selected="$(QEMU_ASAN=1 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 "$FAKE_CLANG")"
[[ "$selected" == arm64 ]]
[[ ! -s "$TEST_COMPILER_LOG" ]]

# Explicit arm64e remains a probe-gated development lane.
: > "$TEST_COMPILER_LOG"
selected="$(TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=arm64e \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64)"
[[ "$selected" == arm64e ]]
grep -Fq -- '-arch arm64e' "$TEST_COMPILER_LOG"

# A driver accepting -arch arm64e without the arm64e call-authentication ABI
# is not a valid compiler for the explicit development lane.
if TEST_ARM64E_PTRAUTH=0 WHP_MACOS_ARCH=arm64e \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 \
        >"$TEST_DIR/no-ptrauth.out" 2>"$TEST_DIR/no-ptrauth.err"; then
    printf '%s\n' 'error: arm64e without authenticated calls unexpectedly succeeded' >&2
    exit 1
fi
grep -Fq 'requested arm64e' "$TEST_DIR/no-ptrauth.err"

if TEST_ARM64E_SUPPORTED=0 WHP_MACOS_ARCH=arm64e \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 arm64 \
        >"$TEST_DIR/explicit.out" 2>"$TEST_DIR/explicit.err"; then
    printf '%s\n' 'error: explicit arm64e unexpectedly succeeded' >&2
    exit 1
fi
grep -Fq 'requested arm64e' "$TEST_DIR/explicit.err"

: > "$TEST_COMPILER_LOG"
selected="$(TEST_ARM64E_SUPPORTED=1 WHP_MACOS_ARCH=auto \
    whp_select_macos_arch "$FAKE_CLANG" /tmp/MacOSX.sdk 15.0 x86_64 "$FAKE_CLANG")"
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

# Validate both Clang driver commands and flags against one selected linker.
# Each fixture uses an isolated environment: no user's compiler flags leak in.
audit_linker_flags()
{
    (
        local kind="$1"
        local variable="${2:-}"
        local setting="${3:-}"
        CC=clang
        CXX=clang++
        OBJC=clang
        CFLAGS=
        CXXFLAGS=
        OBJCFLAGS=
        CPPFLAGS=
        LDFLAGS=
        QEMU_ASAN=n
        NATIVE_LLVM_DIR=/mock/llvm
        if [[ "$kind" == lld ]]; then
            LD=/mock/llvm/bin/ld64.lld
            NATIVE_LLVM_LDFLAG=-fuse-ld=lld
            WHP_MACOS_ARCH=arm64
        else
            LD=/mock/Apple/ld
            NATIVE_LLVM_LDFLAG=
            WHP_MACOS_ARCH=arm64e
        fi
        if [[ -n "$variable" ]]; then
            printf -v "$variable" '%s' "$setting"
        fi
        whp_macos_audit_linker_driver_flags
    )
}

audit_linker_flags apple
# Inherited Homebrew LD does not override the Clang driver.
audit_linker_flags apple LD '/opt/homebrew/bin/ld64.lld'
audit_linker_flags apple LD 'ld64.lld'
# Managed native LLD must still match its own installation exactly.
if audit_linker_flags lld LD '/opt/homebrew/bin/ld64.lld' \
    >"$TEST_DIR/linker.out" 2>"$TEST_DIR/linker.err"; then
    printf 'error: native LLD accepted an unrelated Homebrew LD\n' >&2
    exit 1
fi
grep -Fq 'disagrees with LD' "$TEST_DIR/linker.err"
audit_linker_flags lld LDFLAGS '-fuse-ld=lld'
audit_linker_flags lld CC 'clang -fuse-ld=lld'
audit_linker_flags lld CXX 'clang++ --ld-path=/mock/llvm/bin/ld64.lld'
for variable in CC CXX CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
    case "$variable" in
        CC) override='clang -fuse-ld=lld' ;;
        CXX) override='clang++ -fuse-ld=lld' ;;
        *) override='-fuse-ld=lld' ;;
    esac
    if audit_linker_flags apple "$variable" "$override" >"$TEST_DIR/linker.out" 2>"$TEST_DIR/linker.err"; then
        printf 'error: Apple ld accepted LLVM override via %s\n' "$variable" >&2
        exit 1
    fi
    grep -Fq "$variable" "$TEST_DIR/linker.err"

    if audit_linker_flags apple "$variable" '--ld-path=/mock/other/ld' >"$TEST_DIR/linker.out" 2>"$TEST_DIR/linker.err"; then
        printf 'error: Apple ld accepted --ld-path via %s\n' "$variable" >&2
        exit 1
    fi
    grep -Fq "$variable" "$TEST_DIR/linker.err"

    if audit_linker_flags lld "$variable" '-fuse-ld=ld' >"$TEST_DIR/linker.out" 2>"$TEST_DIR/linker.err"; then
        printf 'error: Mach-O LLD accepted Apple override via %s\n' "$variable" >&2
        exit 1
    fi
    grep -Fq "$variable" "$TEST_DIR/linker.err"
done

for bad in '-Wl,-O2' '--ld-path=/mock/other/ld'; do
    if audit_linker_flags lld CXXFLAGS "$bad" >"$TEST_DIR/linker.out" 2>"$TEST_DIR/linker.err"; then
        printf 'error: Mach-O LLD accepted conflicting C++ link flag %s\n' "$bad" >&2
        exit 1
    fi
done
if audit_linker_flags apple CXXFLAGS '-Wl,--read-workers=8'         >"$TEST_DIR/linker.out" 2>"$TEST_DIR/linker.err"; then
    printf 'error: Apple ld accepted Mach-O LLD worker flags\n' >&2
    exit 1
fi

# Explicit ARM64e LLD cannot accidentally become the default.
if (
    LD=/mock/llvm/bin/ld64.lld
    NATIVE_LLVM_DIR=/mock/llvm
    NATIVE_LLVM_LDFLAG=-fuse-ld=lld
    WHP_MACOS_ARCH=arm64e
    WHP_ARM64E_USE_LLD=0
    QEMU_ASAN=n
    CC=clang CXX=clang++ OBJC=clang
    CFLAGS= CXXFLAGS= OBJCFLAGS= CPPFLAGS= LDFLAGS=
    whp_macos_audit_linker_driver_flags
) >"$TEST_DIR/disabled-lld.out" 2>"$TEST_DIR/disabled-lld.err"; then
    printf 'error: ARM64e LLD unexpectedly enabled without opt-in\n' >&2
    exit 1
fi
grep -Fq 'WHP_ARM64E_USE_LLD=1' "$TEST_DIR/disabled-lld.err"

# Check selected output ABI separately from the executing process ABI.
toolchain_verifier="$SOURCE_DIR/scripts/verify-macos-toolchain.bash"
grep -Fq 'link_arch="${WHP_MACOS_ARCH:-$host_arch}"' "$toolchain_verifier"
grep -Fq 'compile_c_probe CC "$CC" "$link_arch"' "$toolchain_verifier"
grep -Fq 'require_output_arch CXX "$output" "$link_arch"' "$toolchain_verifier"
grep -Fq 'require_output_arch OBJC "$output" "$link_arch"' "$toolchain_verifier"
grep -Fq 'compile_arm64e_cxx_unwind_probe()' "$toolchain_verifier"
grep -Fq 'throw std::runtime_error("arm64e-lld")' "$toolchain_verifier"
grep -Fq 'require_output_arch CXX_UNWIND "$output" "$link_arch"' "$toolchain_verifier"
grep -Fq 'if [[ "$link_arch" == arm64e && "${WHP_ARM64E_USE_LLD:-0}" == 1 ]]; then' "$toolchain_verifier"

# Integration contract: the macOS QEMU wrapper owns the final Apple -arch
# choice and applies it consistently to C, C++, Objective-C, and links.
macos_builder="$SOURCE_DIR/scripts/macos-builder.bash"
grep -Fq 'source "$SCRIPT_DIR/macos-arch-policy.bash"' "$macos_builder"
grep -Fq 'whp_select_macos_arch "$CC" "$SDKROOT"' "$macos_builder"
grep -Fq '"$process_arch" "$CXX")"' "$macos_builder"
grep -Fq 'whp_append_flag "$variable" "-arch $WHP_MACOS_ARCH"' "$macos_builder"
grep -Fq "*' -arch '*)" "$macos_builder"

printf 'macOS architecture policy tests: passed\n'
