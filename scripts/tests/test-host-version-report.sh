#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Hermetic macOS/Xcode/SDK and toolchain-version identity smoke test.
set -eu
root=$(CDPATH= cd -P -- "$(dirname -- "$0")/../.." && pwd -P) || exit 1
reporter="$root/scripts/whp-build/host-version-report.sh"
work=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-version-audit.XXXXXX") || exit 1
trap 'rm -rf -- "$work"' 0
mkdir -p "$work/bin"

cat > "$work/bin/uname" <<'SH'
#!/bin/sh
case "${1:-}" in -s) echo Darwin ;; -r) echo 25.6.0 ;; -m) echo arm64 ;; *) exit 2 ;; esac
SH
cat > "$work/bin/sw_vers" <<'SH'
#!/bin/sh
[ "${1:-}" = -productVersion ] || exit 1
echo 26.5
SH
cat > "$work/bin/xcode-select" <<'SH'
#!/bin/sh
[ "${1:-}" = -p ] || exit 1
echo /Applications/Xcode_26.6.app/Contents/Developer
SH
cat > "$work/bin/xcrun" <<'SH'
#!/bin/sh
case "$*" in
    '--sdk macosx --show-sdk-path') echo /Applications/Xcode_26.6.app/Contents/Developer/SDKs/MacOSX26.5.sdk ;;
    '--sdk macosx --show-sdk-version') echo 26.5 ;;
    '--sdk macosx --find clang') echo "$WHP_AUDIT_TEST_CLANG" ;;
    --version) echo 'xcrun version test' ;;
    *) exit 1 ;;
esac
SH
cat > "$work/bin/clang" <<'SH'
#!/bin/sh
[ "${1:-}" = --version ] || exit 1
printf 'Apple clang version 26.6.0\nTarget: arm64-apple-darwin\n'
SH
cat > "$work/bin/xcodebuild" <<'SH'
#!/bin/sh
[ "${1:-}" = -version ] || exit 1
printf 'Xcode 26.6\nBuild version test\n'
SH
cat > "$work/bin/git" <<'SH'
#!/bin/sh
case "${1:-}:${3:-}" in
    -C:rev-parse) printf '%040d\n' 1 ;;
    -C:ls-tree) printf '160000 commit %040d\t%s\n' 2 "$6" ;;
    --version:*) echo 'git version 2.56.0' ;;
    *) exit 1 ;;
esac
SH
chmod +x "$work/bin/"*

WHP_AUDIT_TEST_CLANG="$work/bin/clang" \
PATH="$work/bin:$PATH" \
DEVELOPER_DIR= \
SDKROOT= \
CC='clang -arch arm64e' \
    /bin/sh "$reporter" > "$work/report"
for key in \
    'report.schema=1' \
    'host.kernel=Darwin' \
    'host.release=25.6.0' \
    'apple.os_version=26.5' \
    'apple.developer_origin=xcode-select' \
    'apple.active_sdk_version=26.5' \
    'apple.xcode_version=Xcode 26.6' \
    'apple.xcrun_clang_version=Apple clang version 26.6.0' \
    'tool.clang.version=Apple clang version 26.6.0' \
    'source.toolchains/llvm-project=0000000000000000000000000000000000000002' \
    'selected.CC=clang -arch arm64e'; do
    if ! grep -Fxq "$key" "$work/report"; then
        printf 'error: version report lacked %s\n' "$key" >&2
        cat "$work/report" >&2
        exit 1
    fi
done
# An explicit SDK/developer root must be disclosed, not mistaken for the
# system's default selected version. No read-only report changes either one.
WHP_AUDIT_TEST_CLANG="$work/bin/clang" \
PATH="$work/bin:$PATH" \
DEVELOPER_DIR='/Library/Developer/CommandLineTools' \
SDKROOT='/chosen/MacOSX15.sdk' \
    /bin/sh "$reporter" > "$work/explicit-report"
grep -Fxq 'apple.developer_origin=DEVELOPER_DIR' "$work/explicit-report"
grep -Fxq 'apple.developer_root=/Library/Developer/CommandLineTools' "$work/explicit-report"
grep -Fxq 'apple.sdk_override=/chosen/MacOSX15.sdk' "$work/explicit-report"

printf '%s\n' 'WHP host version report and macOS SDK drift: verified'
