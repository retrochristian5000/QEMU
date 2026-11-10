#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Hermetic Homebrew CPP discovery checks; never install or modify Homebrew.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT

unset WHP_CPP_SEED WHP_CPP_LOCKED
native="$("$ROOT/seeds/cc.sh" --print-cc)"
test -x "$native"
test "$(WHP_CPP_PREFER_HOMEBREW=0 "$ROOT/seeds/cpp.sh" --print-seed)" = "$native"

if [[ "$(uname -s)" != Darwin ]]; then
    if WHP_CPP_PREFER_HOMEBREW=1 "$ROOT/seeds/cpp.sh" --print-seed >/dev/null 2>&1; then
        echo "error: Homebrew CPP preference was accepted off macOS" >&2
        exit 1
    fi
    exit 0
fi

mkdir -p "$tmp/brew/opt/llvm/bin"
mock="$tmp/brew/opt/llvm/bin/clang"
cat > "$mock" <<'EOF'
#!/bin/sh
exec "$WHP_TEST_CPP_NATIVE_CC" "$@"
EOF
chmod +x "$mock"
export WHP_TEST_CPP_NATIVE_CC="$native"
selected="$(HOMEBREW_PREFIX="$tmp/brew" WHP_CPP_PREFER_HOMEBREW=1 \
    "$ROOT/seeds/cpp.sh" --print-seed)"
test "$selected" = "$mock"
# An explicit driver remains authoritative, even in Homebrew preference mode.
selected="$(HOMEBREW_PREFIX="$tmp/brew" WHP_CPP_PREFER_HOMEBREW=1 \
    WHP_CPP_SEED="$native" "$ROOT/seeds/cpp.sh" --print-seed)"
test "$selected" = "$native"
# Reject a fake Homebrew compiler that cannot compile and link native code.
cat > "$mock" <<'EOF'
#!/bin/sh
if [ "${1:-}" = --version ]; then echo 'fake clang'; exit 0; fi
exit 1
EOF
chmod +x "$mock"
if HOMEBREW_PREFIX="$tmp/brew" WHP_CPP_PREFER_HOMEBREW=1 \
    "$ROOT/seeds/cpp.sh" --print-seed >/dev/null 2>&1; then
    echo "error: broken Homebrew CPP passed native admission" >&2
    exit 1
fi
printf '%s\n' 'WHP Homebrew CPP seed isolation: verified'
