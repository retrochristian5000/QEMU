#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Native seed probes must explain real failures without contaminating stdout.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$ROOT/scripts/whp-build/compiler-seed-common.sh"
seed_root="$ROOT"  # Same source root as cc.sh and cxx.sh.
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

# Reject a compiler with working link but missing C/POSIX SDK headers.
cat > "$tmp/headerless" <<'SH'
#!/bin/sh
if [ "$1" = --version ]; then printf '%s\n' 'mock headerless cc'; exit 0; fi
for item in "$@"; do
    case "$item" in *.c|*.cc)
        if grep -Fq '#include <unistd.h>' "$item"; then
            printf '%s\n' 'WHP_HEADERLESS_CC: missing unistd.h' >&2
            exit 71
        fi ;;
    esac
done
exec "$WHP_REAL_NATIVE_CC" "$@"
SH
chmod +x "$tmp/headerless"
export WHP_REAL_NATIVE_CC="$(command -v cc)"
if WHP_CC_SEED="$tmp/headerless" "$ROOT/cc.sh" --print-cc \
    > "$tmp/stdout" 2> "$tmp/stderr"; then
    echo 'error: headerless native C compiler passed' >&2
    exit 1
fi
test ! -s "$tmp/stdout"
grep -Fq 'WHP_HEADERLESS_CC' "$tmp/stderr"

# No target include or library search override may influence seed admission.
cat > "$tmp/env-tainted" <<'SH'
#!/bin/sh
if [ "$1" = --version ]; then printf '%s\n' 'mock native cc'; exit 0; fi
for key in CPATH LIBRARY_PATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LD_LIBRARY_PATH; do
    if printenv "$key" >/dev/null 2>&1; then
        printf '%s\n' "WHP_PROBE_ENV_POISON: $key" >&2
        exit 72
    fi
done
exec "$WHP_REAL_NATIVE_CC" "$@"
SH
chmod +x "$tmp/env-tainted"
selected="$(CPATH=/target/include LIBRARY_PATH=/target/lib \
    C_INCLUDE_PATH=/target/c CPLUS_INCLUDE_PATH=/target/cxx \
    LD_LIBRARY_PATH=/target/lib \
    try_compiler c "$tmp/env-tainted" report)"
test "$selected" = "$tmp/env-tainted"
mkdir -p "$tmp/relative"
cp "$tmp/env-tainted" "$tmp/relative/relative-cc"
(
    cd "$tmp"
    selected="$(try_compiler c relative/relative-cc report)"
    test "$selected" = "$tmp/relative/relative-cc"
)
printf '%s\n' 'WHP compiler seed failure diagnostics: verified'
