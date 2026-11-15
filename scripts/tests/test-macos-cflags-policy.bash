#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Hermetic tests: no Xcode, SDK downloads, or QEMU compilation.
set -euo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$SOURCE_DIR/scripts/whp-build/macos-cflags.bash"
work="$(mktemp -d "${TMPDIR:-/tmp}/whp-macos-cflags.XXXXXX")"
trap 'rm -rf "$work"' EXIT

cat > "$work/cc" <<'COMPILER'
#!/bin/sh
printf '%s\n' "$*" >> "$WHP_FLAGS_PROBE_LOG"
case " $* " in
    *' -fgnu-only '*) printf 'error: unsupported GCC-only flag\n' >&2; exit 1 ;;
    *' -Wno-ignored-flag '*)
        printf 'warning: unknown warning option -Wno-ignored-flag\n' >&2 ;;
    *' -Wno-unused-linker-flag '*)
        printf 'warning: argument unused during compilation\n' >&2 ;;
esac
cat >/dev/null
exit 0
COMPILER
chmod +x "$work/cc"
export WHP_FLAGS_PROBE_LOG="$work/flags.log"
CC="$work/cc"
CXX="$work/cc"
OBJC="$work/cc"
SDKROOT=/mock/MacOSX.sdk
MACOSX_DEPLOYMENT_TARGET=15.0
WHP_MACOS_ARCH=arm64
MACOS_EFFECTIVE_COMPILER_FAMILY=clang
export CC CXX OBJC SDKROOT MACOSX_DEPLOYMENT_TARGET WHP_MACOS_ARCH \
    MACOS_EFFECTIVE_COMPILER_FAMILY

# Only retained flags reach the corresponding language frontend. Inherited
# optimization, CPU tuning, sanitizer and coverage choices are QEMU-owned.
CFLAGS='-march=native -O3 -fsanitize=address -DKEEP_C=1'
CXXFLAGS='-mcpu apple-m4 -Og -DKEEP_CXX=1'
OBJCFLAGS='-mtune=native -O0 -DKEEP_OBJC=1'
CPPFLAGS='-DKEEP_COMMON=1'
whp_macos_preflight_cflags
[[ $(wc -l < "$WHP_FLAGS_PROBE_LOG") -eq 3 ]]
grep -Fq -- '-DKEEP_COMMON=1 -DKEEP_C=1 -x c -c -o /dev/null -' "$WHP_FLAGS_PROBE_LOG"
grep -Fq -- '-DKEEP_COMMON=1 -DKEEP_CXX=1 -x c++ -c -o /dev/null -' "$WHP_FLAGS_PROBE_LOG"
grep -Fq -- '-DKEEP_COMMON=1 -DKEEP_OBJC=1 -x objective-c -c -o /dev/null -' "$WHP_FLAGS_PROBE_LOG"
if grep -Eq -- '-march=|-mcpu[= ]|-mtune=|-O3|-Og|-fsanitize' "$WHP_FLAGS_PROBE_LOG"; then
    printf 'error: filtered compiler flags leaked into macOS preflight\n' >&2
    exit 1
fi
[[ "$CFLAGS" == '-march=native -O3 -fsanitize=address -DKEEP_C=1' ]]

# A mismatched compiler flag must fail in its owning language, rather than
# waiting for Meson or silently falling back to another compiler.
for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS; do
    CFLAGS= CXXFLAGS= OBJCFLAGS= CPPFLAGS=
    printf -v "$variable" '%s' '-fgnu-only'
    if whp_macos_preflight_cflags >"$work/stdout" 2>"$work/stderr"; then
        printf 'error: %s accepted an unsupported compiler option\n' "$variable" >&2
        exit 1
    fi
    grep -Fq "macOS $variable rejected by" "$work/stderr"
done

for diagnostic_flag in -Wno-ignored-flag -Wno-unused-linker-flag; do
    CFLAGS="$diagnostic_flag"
    CPPFLAGS= CXXFLAGS= OBJCFLAGS=
    if whp_macos_preflight_cflags >"$work/stdout" 2>"$work/stderr"; then
        printf 'error: accepted ignored macOS compiler option %s\n' "$diagnostic_flag" >&2
        exit 1
    fi
    grep -Fq 'ignored or unsupported CC options' "$work/stderr"
done

CFLAGS='-Wl,-dead_strip'
CPPFLAGS= CXXFLAGS= OBJCFLAGS=
if whp_macos_preflight_cflags >"$work/stdout" 2>"$work/stderr"; then
    printf 'error: linker-only flag passed through CFLAGS\n' >&2
    exit 1
fi
grep -Fq 'use LDFLAGS' "$work/stderr"

printf '%s\n' 'macOS compiler CFLAGS compatibility: verified'
