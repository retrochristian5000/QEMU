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
    chmod +x "$developer/usr/bin/clang" "$developer/usr/bin/clang++"
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
case "$1" in
    --find) printf '%s/usr/bin/%s\n' "$developer" "$2" ;;
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
# Explicit Xcode.app override takes precedence over selected standalone CLT.
export DEVELOPER_DIR="$xcode_app"
test "$(whp_apple_developer_root)" = "$xcode"
test "$(whp_apple_find_tool clang++)" = "$xcode/usr/bin/clang++"
test "$(whp_apple_find_sdk)" = "$xcode/SDKs/MacOSX.sdk"
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
export DEVELOPER_DIR="$tmp/nonexistent.app"
if whp_apple_find_tool clang >/dev/null 2>&1; then
    echo 'error: invalid explicit developer directory ignored' >&2
    exit 1
fi
printf '%s\n' 'WHP macOS developer directory precedence and isolation: verified'
