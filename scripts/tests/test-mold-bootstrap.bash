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
BOOTSTRAP_MOLD=1
MOLD_TOOLS_DIR="$tmpdir/mold-tools"
LDFLAGS=
mkdir -p "$BUILD_DIR"

stderr="$tmpdir/darwin.stderr"
whp_prepare_mold 2> "$stderr"
[[ "$BOOTSTRAP_MOLD" == 0 ]]
[[ -z "${MOLD_LINKER:-}" ]]
[[ -z "$LDFLAGS" ]]
grep -Fq 'cannot link macOS Mach-O binaries' "$stderr"

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

export WHP_MOLD_TEST_LOG="$log"
CC="$fakebin/cc"
AR="$fakebin/ar"
QEMU_HOST_LTO=1
LDFLAGS=
export CC AR QEMU_HOST_LTO LDFLAGS
whp_mold_link_probe "$fakebin/mold"
[[ "$(grep -Fc ' -flto -c ' "$log")" -eq 2 ]]
grep -Fq 'ar rcs ' "$log"
grep -Fq ' -flto -fuse-ld=mold ' "$log"

grep -Fq '[submodule "toolchains/fast-linker"]' "$SOURCE_DIR/.gitmodules"
grep -Fq 'url = https://github.com/retrochristian5000/fast-linker.git' \
    "$SOURCE_DIR/.gitmodules"

printf 'mold bootstrap policy tests: passed\n'
