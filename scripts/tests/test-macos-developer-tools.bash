#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Hermetic Xcode/CLT search-order tests: no global developer selection change.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/whp-build/macos-developer-tools.sh"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
clt="$tmp/CommandLineTools"
xcode_app="$tmp/Xcode-beta.app"
xcode="$xcode_app/Contents/Developer"
for developer in "$clt" "$xcode"; do
    mkdir -p "$developer/usr/bin" "$developer/SDKs/MacOSX.sdk"
    printf '#!/bin/sh\nexit 0\n' > "$developer/usr/bin/clang"
    printf '#!/bin/sh\nexit 0\n' > "$developer/usr/bin/clang++"
    printf '#!/bin/sh\nexit 0\n' > "$developer/usr/bin/ld"
    printf '#!/bin/sh\nexit 0\n' > "$developer/usr/bin/strip"
    chmod +x "$developer/usr/bin/clang" "$developer/usr/bin/clang++" \
        "$developer/usr/bin/ld" "$developer/usr/bin/strip"
done
mkdir "$tmp/bin"
cat > "$tmp/bin/xcode-select" <<'EOF'
#!/bin/sh
test "$1" = -p || exit 1
printf '%s\n' "$WHP_TEST_CLT"
EOF
cat > "$tmp/bin/xcrun" <<'EOF'
#!/bin/sh
test "$1" = --sdk && test "$2" = macosx || exit 1
shift 2
developer=${DEVELOPER_DIR:-$WHP_TEST_CLT}
case "$developer" in *.app) developer=$developer/Contents/Developer ;; esac
if [ "${WHP_TEST_FOREIGN:-0}" = 1 ]; then developer=$WHP_TEST_CLT; fi
if [ "${WHP_TEST_XCRUN_FAIL:-0}" = 1 ]; then exit 1; fi
case "$1" in
    --find)
        if [ "${WHP_TEST_SYSTEM_SHIM:-0}" = 1 ]; then
            printf '/usr/bin/%s\n' "$2"
        else
            printf '%s/usr/bin/%s\n' "$developer" "$2"
        fi
        ;;
    --show-sdk-path) printf '%s/SDKs/MacOSX.sdk\n' "$developer" ;;
    *) exit 1 ;;
esac
EOF
chmod +x "$tmp/bin/xcode-select" "$tmp/bin/xcrun"
export WHP_TEST_CLT="$clt"
export PATH="$tmp/bin:$PATH"
unset DEVELOPER_DIR || true
test "$(whp_apple_developer_root)" = "$clt"
test "$(whp_apple_find_tool clang)" = "$clt/usr/bin/clang"
test "$(whp_apple_find_sdk)" = "$clt/SDKs/MacOSX.sdk"
test "$(whp_apple_find_tool ld system)" = "$clt/usr/bin/ld"
test "$(whp_apple_find_tool strip system)" = "$clt/usr/bin/strip"
# Explicit Xcode.app override takes precedence over selected standalone CLT.
export DEVELOPER_DIR="$xcode_app"
test "$(whp_apple_developer_root)" = "$xcode"
test "$(whp_apple_find_tool clang++)" = "$xcode/usr/bin/clang++"
test "$(whp_apple_find_sdk)" = "$xcode/SDKs/MacOSX.sdk"
test "$(whp_apple_find_tool ld system)" = "$xcode/usr/bin/ld"
if [ -x /usr/bin/strip ]; then
    test "$(WHP_TEST_SYSTEM_SHIM=1 whp_apple_find_tool strip system)" = /usr/bin/strip
fi
if WHP_TEST_SYSTEM_SHIM=1 whp_apple_find_tool clang >/dev/null 2>&1; then
    echo 'error: compiler accepted a system tool shim' >&2
    exit 1
fi
if whp_apple_find_tool xcodebuild system >/dev/null 2>&1; then
    echo 'error: Xcode-only command accepted as a system utility' >&2
    exit 1
fi
if whp_apple_check_sdkroot "$clt/SDKs/MacOSX.sdk" >/dev/null 2>&1; then
    echo 'error: foreign CLT SDK accepted with Xcode selected' >&2
    exit 1
fi
if WHP_TEST_FOREIGN=1 whp_apple_find_tool clang >/dev/null 2>&1; then
    echo 'error: foreign CLT compiler accepted with Xcode selected' >&2
    exit 1
fi
if WHP_TEST_FOREIGN=1 whp_apple_find_sdk >/dev/null 2>&1; then
    echo 'error: foreign CLT SDK discovery accepted with Xcode selected' >&2
    exit 1
fi
# On Linux the native linker can be exercised against a synthetic Apple
# selection with the real GNU C/linker drivers. A failed xcrun must fail
# closed even when /usr/bin/ld is available on PATH.
if [ "$(uname -s)" = Linux ]; then
    native_cc=$(command -v cc)
    native_ld=$(command -v ld)
    # The synthetic Apple Clang above deliberately only tests discovery.
    # For the *linker* smoke, delegate the mock to the real Linux compiler.
    # The Linux driver must not receive a nonexistent fake MacOSX.sdk via
    # -isysroot; the developer/SDK root checks remain exercised separately.
    cat > "$xcode/usr/bin/clang" <<'SH'
#!/bin/sh
if [ "${1:-}" = -isysroot ]; then shift 2; fi
exec "$WHP_TEST_NATIVE_CC" "$@"
SH
    chmod +x "$xcode/usr/bin/clang"
    export WHP_TEST_NATIVE_CC="$native_cc"
    printf '#!/bin/sh\nexec "$WHP_TEST_NATIVE_LD" "$@"\n' > "$xcode/usr/bin/ld"
    chmod +x "$xcode/usr/bin/ld"
    cat > "$tmp/bin/uname" <<'EOF'
#!/bin/sh
if [ "$1" = -s ]; then printf 'Darwin\n'; else exec "$WHP_TEST_UNAME" "$@"; fi
EOF
    chmod +x "$tmp/bin/uname"
    export WHP_TEST_UNAME="$(command -v /usr/bin/uname)"
    export WHP_TEST_NATIVE_LD="$native_ld"
    selected_ld="$(WHP_CC_SEED="$xcode/usr/bin/clang" "$ROOT/ld.sh" --print-ld)"
    test "$selected_ld" = "$xcode/usr/bin/ld"
    if WHP_TEST_XCRUN_FAIL=1 WHP_CC_SEED="$xcode/usr/bin/clang" \
        "$ROOT/ld.sh" --print-ld >/dev/null 2>&1; then
        echo 'error: broken Apple developer selection fell back to PATH ld' >&2
        exit 1
    fi
fi
export DEVELOPER_DIR="$tmp/nonexistent.app"
if whp_apple_find_tool clang >/dev/null 2>&1; then
    echo 'error: invalid explicit developer directory ignored' >&2
    exit 1
fi
printf '%s\n' 'WHP macOS developer directory precedence and isolation: verified'
