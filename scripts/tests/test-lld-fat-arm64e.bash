#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Validate the pinned LLD universal-input selector, not system ld64.
set -euo pipefail
if [[ $# -ne 2 || ! -x "$1" || ! -x "$2" ]]; then
  echo "usage: $0 <ld64.lld> <llvm-lipo>" >&2
  exit 2
fi
ld="$1"
lipo="$2"
testfile="llvm-project/lld/test/MachO/fat-arm64e-selection.s"
[[ -f "$testfile" ]] || { echo "missing LLVM fat-slice fixture" >&2; exit 1; }
work="$(mktemp -d "${TMPDIR:-/tmp}/whp-fat-arm64e.XXXXXX")"
trap 'rm -rf "$work"' EXIT
awk -v dir="$work" '/^#--- / {file=$2; next} file!="" {print > (dir "/" file)}' "$testfile"

xcrun clang -arch arm64 -mmacosx-version-min=13.0 -c "$work/lib-arm64.s" -o "$work/lib-a.o"
xcrun clang -arch arm64e -mmacosx-version-min=13.0 -c "$work/lib-arm64e.s" -o "$work/lib-e.o"
xcrun clang -arch arm64e -mmacosx-version-min=13.0 -c "$work/client-a.s" -o "$work/client-a.o"
xcrun clang -arch arm64e -mmacosx-version-min=13.0 -c "$work/client-e.s" -o "$work/client-e.o"
"$ld" -arch arm64 -platform_version macos 13.0 13.0 -dylib \
  -install_name @rpath/libfat.dylib "$work/lib-a.o" -o "$work/lib-a.dylib"
"$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib -fixup_chains \
  -install_name @rpath/libfat.dylib "$work/lib-e.o" -o "$work/lib-e.dylib"

for fat in 32 64; do
  opts=()
  [[ "$fat" == 64 ]] && opts=(-fat64)
  "$lipo" -create "${opts[@]}" "$work/lib-a.dylib" "$work/lib-e.dylib" -o "$work/both-$fat.dylib"
  "$lipo" -create "${opts[@]}" "$work/lib-a.dylib" -o "$work/arm64-$fat.dylib"
  "$lipo" -create "${opts[@]}" "$work/lib-a.o" -o "$work/arm64-$fat.o"
  "$lipo" -create "${opts[@]}" "$work/client-e.o" -o "$work/arm64e-$fat.o"

  # The exact arm64e dependency must take precedence over arm64.
  "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib -fixup_chains \
    "$work/client-e.o" "$work/both-$fat.dylib" -o "$work/exact-$fat.dylib"

  # An arm64 dylib, unlike an arm64 object, can satisfy an arm64e import.
  "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib -fixup_chains \
    "$work/client-a.o" "$work/arm64-$fat.dylib" -o "$work/fallback-$fat.dylib"

  # FAT32 and FAT64 arm64e objects must still be accepted by exact selection.
  "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib -fixup_chains \
    "$work/arm64e-$fat.o" "$work/lib-e.dylib" -o "$work/object-$fat.dylib"

  if "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib \
      "$work/client-a.o" "$work/arm64-$fat.o" \
      -o "$work/invalid-$fat.dylib" > "$work/error.log" 2>&1; then
    echo "arm64 object incorrectly selected for arm64e output" >&2
    exit 1
  fi
  grep -Fq "ignoring file because it is universal (arm64) but does not contain the arm64e architecture" \
    "$work/error.log" || { cat "$work/error.log" >&2; exit 1; }
done

python3 - "$work/both-64.dylib" "$work/truncated.dylib" <<'PY'
import pathlib
import sys
pathlib.Path(sys.argv[2]).write_bytes(pathlib.Path(sys.argv[1]).read_bytes()[:12])
PY
if "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib \
    "$work/client-e.o" "$work/truncated.dylib" \
    -o "$work/malformed.dylib" > "$work/error.log" 2>&1; then
  echo "truncated FAT64 header incorrectly accepted" >&2
  exit 1
fi
grep -Fq 'truncated or malformed fat file' "$work/error.log" || {
  cat "$work/error.log" >&2
  exit 1
}
echo "ARM64e FAT32/FAT64 exact selection, dylib fallback and ABI guards: passed"
