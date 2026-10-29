#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Native seed probes must explain real failures without contaminating stdout.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/whp-build/compiler-seed-common.sh"
tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT
export TMPDIR="$tmp"

cat > "$tmp/bad-compile" <<'SH'
#!/bin/sh
if [ "$1" = --version ]; then echo 'mock compiler 1.0'; exit 0; fi
printf 'WHP_FAKE_COMPILE_FAILURE: missing native SDK/libSystem\n' >&2
exit 43
SH
cat > "$tmp/bad-version" <<'SH'
#!/bin/sh
printf 'WHP_FAKE_VERSION_FAILURE: developer tools unavailable\n' >&2
exit 47
SH
cat > "$tmp/bad-run" <<'SH'
#!/bin/sh
if [ "$1" = --version ]; then echo 'mock compiler 2.0'; exit 0; fi
while [ "$#" -gt 0 ]; do
    if [ "$1" = -o ]; then shift; outfile=$1; fi
    shift
done
printf '#!/bin/sh\nprintf "WHP_FAKE_RUNTIME_FAILURE: wrong architecture\\n" >&2\nexit 38\n' > "$outfile"
chmod +x "$outfile"
SH
chmod +x "$tmp/bad-compile" "$tmp/bad-version" "$tmp/bad-run"

if WHP_CC_SEED="$tmp/bad-compile" "$ROOT/cc.sh" --print-cc \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: failing C compiler passed' >&2; exit 1
fi
test ! -s "$tmp/stdout"
grep -Fq 'native C compile/link probe failed (exit 43)' "$tmp/stderr"
grep -Fq 'WHP_FAKE_COMPILE_FAILURE' "$tmp/stderr"
grep -Fq 'requested build C compiler is not native/usable' "$tmp/stderr"

if WHP_CXX_SEED="$tmp/bad-compile" "$ROOT/cxx.sh" --print-cxx \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: failing C++ compiler passed' >&2; exit 1
fi
test ! -s "$tmp/stdout"
grep -Fq 'native C++17 compile/link probe failed (exit 43)' "$tmp/stderr"
grep -Fq -- '-std=c++17' "$tmp/stderr"
grep -Fq 'WHP_FAKE_COMPILE_FAILURE' "$tmp/stderr"

if WHP_CC_SEED="$tmp/bad-version" "$ROOT/cc.sh" --print-cc \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: broken compiler --version passed' >&2; exit 1
fi
test ! -s "$tmp/stdout"
grep -Fq 'compiler --version failed (exit 47)' "$tmp/stderr"
grep -Fq 'WHP_FAKE_VERSION_FAILURE' "$tmp/stderr"

if WHP_CC_SEED="$tmp/bad-run" "$ROOT/cc.sh" --check \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: failing native executable passed' >&2; exit 1
fi
test ! -s "$tmp/stdout"
grep -Fq 'native c executable probe failed (exit 38)' "$tmp/stderr"
grep -Fq 'WHP_FAKE_RUNTIME_FAILURE' "$tmp/stderr"

if try_compiler c "$tmp/bad-compile" quiet \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: failing fallback compiler passed' >&2; exit 1
fi
test ! -s "$tmp/stdout"
test ! -s "$tmp/stderr"

if TMPDIR="$tmp/missing-parent" try_compiler c "$(command -v cc)" report \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: broken native probe directory accepted' >&2; exit 1
fi
grep -Fq 'cannot create native compiler probe directory' "$tmp/stderr"

selected="$(try_compiler c "$(command -v cc)" report)"
test "$selected" = "$(command -v cc)"
# No failed or successful native probe may leave an owned temporary directory.
for directory in "$tmp"/whp-cc-seed.*; do
    if [ -e "$directory" ]; then
        printf 'error: native compiler probe leaked directory: %s\n' "$directory" >&2
        exit 1
    fi
done
printf '%s\n' 'WHP compiler seed failure diagnostics: verified'
