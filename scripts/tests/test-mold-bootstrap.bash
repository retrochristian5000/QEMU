#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$SOURCE_DIR/scripts/whp-build/common.bash"
source "$SOURCE_DIR/scripts/whp-build/prepare-mold.bash"

tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/whp-mold-test.XXXXXX")"
trap 'rm -rf "$tmpdir"' EXIT

BUILD_DIR="$tmpdir/build"
HOST_ARCH=arm64
HOST_OS=Darwin
BOOTSTRAP_MOLD=0
QEMU_HOST_LINKER=mold
MOLD_TOOLS_DIR="$tmpdir/mold-tools"
CFLAGS=
CXXFLAGS=
CPPFLAGS=
LDFLAGS=
mkdir -p "$BUILD_DIR"

# An explicit conflicting selection fails even on Darwin; it is never silently
# changed to Apple ld based on an OS-name restriction.
stderr="$tmpdir/darwin.stderr"
if whp_prepare_mold 2> "$stderr"; then
    printf 'error: an explicit conflicting mold selection succeeded\n' >&2
    exit 1
fi
grep -Fq 'conflicts with BOOTSTRAP_MOLD=0' "$stderr"
[[ -z "${MOLD_LINKER:-}" ]]
[[ -z "$LDFLAGS" ]]
QEMU_HOST_LINKER=auto

HOST_ARCH=x86_64
HOST_OS=Linux
BOOTSTRAP_MOLD=0
MOLD_LINKER=stale
LDFLAGS=
whp_prepare_mold
[[ "$BOOTSTRAP_MOLD" == 0 ]]
[[ -z "$MOLD_LINKER" ]]
[[ -z "$LDFLAGS" ]]

# An LTO-capable mold probe must exercise the same boundary that QEMU's
# Meson build does: separately compiled IR objects, an archive containing IR,
# and a final compiler-driver link through mold.  Fake tools make the policy
# test independent of the host's installed compiler and linker.
fakebin="$tmpdir/fake-lto-tools"
log="$tmpdir/lto-tools.log"
mkdir -p "$fakebin"
cat > "$fakebin/cc" <<'EOF_CC'
#!/usr/bin/env bash
set -euo pipefail
: "${WHP_MOLD_TEST_LOG:?}"
printf 'cc' >> "$WHP_MOLD_TEST_LOG"
printf ' %s' "$@" >> "$WHP_MOLD_TEST_LOG"
printf '\n' >> "$WHP_MOLD_TEST_LOG"

output=
compile=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o)
            output="$2"
            shift 2
            ;;
        -c)
            compile=1
            shift
            ;;
        *)
            shift
            ;;
    esac
done
[[ -n "$output" ]]
if [[ "$compile" == 1 ]]; then
    printf 'fake object\n' > "$output"
else
    printf '#!/usr/bin/env bash\nexit 0\n' > "$output"
    chmod +x "$output"
fi
EOF_CC
cat > "$fakebin/ar" <<'EOF_AR'
#!/usr/bin/env bash
set -euo pipefail
: "${WHP_MOLD_TEST_LOG:?}"
printf 'ar' >> "$WHP_MOLD_TEST_LOG"
printf ' %s' "$@" >> "$WHP_MOLD_TEST_LOG"
printf '\n' >> "$WHP_MOLD_TEST_LOG"
[[ "$1" == rcs ]]
printf 'fake archive\n' > "$2"
EOF_AR
printf '#!/usr/bin/env bash\nexit 0\n' > "$fakebin/mold"
chmod +x "$fakebin/cc" "$fakebin/ar" "$fakebin/mold"

# A GNU/GCC LTO probe must not start using llvm-ar merely because it is
# installed. The native ar choice must be stable unless AR is explicit.
cp "$fakebin/ar" "$fakebin/llvm-ar"
saved_ar="${AR:-}"
AR=
whp_mold_archiver_command
[[ "${WHP_MOLD_AR_CMD[0]}" == ar ]]
AR="$fakebin/llvm-ar"
whp_mold_archiver_command
[[ "${WHP_MOLD_AR_CMD[0]}" == "$fakebin/llvm-ar" ]]
AR="$saved_ar"

export WHP_MOLD_TEST_LOG="$log"
CC="$fakebin/cc"
CXX="$fakebin/cc"
AR="$fakebin/ar"
QEMU_HOST_LTO=1
LDFLAGS=
export CC CXX AR QEMU_HOST_LTO LDFLAGS

# A Darwin host is admitted when its chosen linker passes real compiler
# probes.  The fake driver exercises orchestration without relying on Mach-O.
mkdir -p "$MOLD_TOOLS_DIR/install/bin"
cp "$fakebin/mold" "$MOLD_TOOLS_DIR/install/bin/mold"
BOOTSTRAP_MOLD=auto
QEMU_HOST_LINKER=auto
whp_prepare_mold
[[ "$BOOTSTRAP_MOLD" == 1 ]]
[[ " $LDFLAGS " == *' -fuse-ld=mold '* ]]
grep -Fq -- ' -x c++ ' "$log"

# Automatic mold must not displace the macOS linker required by ASan.
# This is a Darwin policy test even when the CI runner itself is Linux.
HOST_OS=Darwin
QEMU_ASAN=1
LDFLAGS=
BOOTSTRAP_MOLD=auto
whp_prepare_mold
[[ "$BOOTSTRAP_MOLD" == 0 ]]
[[ -z "$LDFLAGS" ]]
QEMU_ASAN=n
HOST_OS=Linux

# Linker changes are permitted on the same host, rather than requiring a new
# operating system or rebuild tree.
LDFLAGS=
BOOTSTRAP_MOLD=auto
QEMU_HOST_LINKER=lld
whp_prepare_mold
[[ "$BOOTSTRAP_MOLD" == 0 ]]
[[ " $LDFLAGS " == *' -fuse-ld=lld '* ]]
grep -Fq -- ' -fuse-ld=lld ' "$log"

# A managed exact Mach-O LLD path is accepted, but an arbitrary override
# cannot redirect the validated driver selection.
(
    NATIVE_LLVM_DIR=/mock/native-llvm
    NATIVE_LLVM_LDFLAG=-fuse-ld=lld
    LD="$NATIVE_LLVM_DIR/bin/ld64.lld"
    LDFLAGS="-fuse-ld=lld --ld-path=$LD"
    whp_linker_flags_compatible lld
    if whp_linker_flags_compatible system; then
        printf 'error: system policy accepted managed LLD flags\n' >&2
        exit 1
    fi
    LDFLAGS="-fuse-ld=lld --ld-path=/foreign/ld64.lld"
    if whp_linker_flags_compatible lld; then
        printf 'error: managed LLD policy accepted a foreign linker path\n' >&2
        exit 1
    fi
)

QEMU_HOST_LINKER=system
if whp_prepare_mold > /dev/null 2> "$stderr"; then
    printf 'error: the system linker ignored an inherited LLD override\n' >&2
    exit 1
fi
grep -Fq 'inherited linker override' "$stderr"
LDFLAGS=
whp_prepare_mold
[[ -z "$LDFLAGS" ]]
[[ "$BOOTSTRAP_MOLD" == 0 ]]
QEMU_HOST_LINKER=auto

# The earlier toolchain and linker probes also log compilations. Count only
# the standalone LTO probe below, not every preceding test in this fixture.
: > "$log"
whp_mold_link_probe "$fakebin/mold"
[[ "$(grep -Fc ' -flto -c ' "$log")" -eq 2 ]]
grep -Fq 'ar rcs ' "$log"
grep -Fq ' -flto -fuse-ld=mold ' "$log"

# Explicit ThinLTO must reach the real compiler/archive/linker probe.
: > "$log"
QEMU_HOST_LTO_MODE=thin
whp_mold_link_probe "$fakebin/mold"
[[ "$(grep -Fc ' -flto=thin -c ' "$log")" -eq 2 ]]
grep -Fq ' -flto=thin -fuse-ld=mold ' "$log"

# Automatic LTO must match the actual host Meson mode: ThinLTO on Darwin,
# full LTO elsewhere. The LTO archive and linker probes also need the same
# C/SDK architecture flags as the QEMU host objects.
: > "$log"
HOST_OS=Darwin
QEMU_HOST_LTO_MODE=auto
CPPFLAGS=-DHOST_CPP_PROBE=1
CFLAGS='-arch arm64e -DHOST_C_ABI=1'
CXXFLAGS='-arch arm64e -DHOST_CXX_ABI=1'
LDFLAGS='-arch arm64e'
whp_mold_link_probe "$fakebin/mold"
[[ "$(grep -Fc ' -flto=thin -c ' "$log")" -eq 2 ]]
grep -Fq 'cc -DHOST_CPP_PROBE=1 -arch arm64e -DHOST_C_ABI=1 -flto=thin -c ' "$log"
grep -Fq ' -arch arm64e -DHOST_C_ABI=1 -flto=thin -fuse-ld=mold ' "$log"

# Validate C and C++ host compiler lanes independently; CXXFLAGS must not
# be replaced by CFLAGS when selecting an LTO-capable linker.
: > "$log"
whp_linker_driver_probe mold "$fakebin"
grep -Fq ' -x c -DHOST_CPP_PROBE=1 -arch arm64e -DHOST_C_ABI=1 ' "$log"
grep -Fq ' -x c++ -DHOST_CPP_PROBE=1 -arch arm64e -DHOST_CXX_ABI=1 ' "$log"

: > "$log"
HOST_OS=Linux
whp_mold_link_probe "$fakebin/mold"
[[ "$(grep -Fc ' -flto -c ' "$log")" -eq 2 ]]
: > "$log"
HOST_OS=Darwin
QEMU_HOST_LTO_MODE=full
whp_mold_link_probe "$fakebin/mold"
[[ "$(grep -Fc ' -flto -c ' "$log")" -eq 2 ]]

grep -Fq '[submodule "toolchains/fast-linker"]' "$SOURCE_DIR/.gitmodules"
grep -Fq 'url = https://github.com/retrochristian5000/fast-linker.git' \
    "$SOURCE_DIR/.gitmodules"

printf 'mold bootstrap policy tests: passed\n'
