#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Validate the pinned LLD universal-input selector, not system ld64.
set -euo pipefail
if [[ $# -ne 4 || ! -x "$1" || ! -x "$2" || ! -x "$3" || ! -x "$4" ]]; then
  echo "usage: $0 <ld64.lld> <llvm-lipo> <llvm-ar> <llvm-ranlib>" >&2
  exit 2
fi
ld="$1"
lipo="$2"
ar="$3"
ranlib="$4"
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

# Each Mach-O ABI has a separately indexed archive. Only llvm-lipo creates
# the outer FAT container, and LLD must select a complete archive slice.
"$ar" --format=darwin crS "$work/lib-a.a" "$work/lib-a.o"
"$ar" --format=darwin crS "$work/lib-e.a" "$work/lib-e.o"
"$ranlib" "$work/lib-a.a"
"$ranlib" "$work/lib-e.a"

for fat in 32 64; do
  opts=()
  [[ "$fat" == 64 ]] && opts=(-fat64)
  "$lipo" -create "${opts[@]}" "$work/lib-a.dylib" "$work/lib-e.dylib" -o "$work/both-$fat.dylib"
  "$lipo" -create "${opts[@]}" "$work/lib-a.dylib" -o "$work/arm64-$fat.dylib"
  "$lipo" -create "${opts[@]}" "$work/lib-a.o" -o "$work/arm64-$fat.o"
  "$lipo" -create "${opts[@]}" "$work/client-e.o" -o "$work/arm64e-$fat.o"
  "$lipo" -create "${opts[@]}" "$work/lib-a.a" "$work/lib-e.a" -o "$work/both-$fat.a"
  "$lipo" -create "${opts[@]}" "$work/lib-a.a" -o "$work/arm64-$fat.a"
  "$lipo" -create "${opts[@]}" "$work/lib-e.a" -o "$work/arm64e-$fat.a"
  "$lipo" -create "${opts[@]}" "$work/lib-e.dylib" -o "$work/arm64e-$fat.dylib"
  archs="$("$lipo" -archs "$work/both-$fat.a")"
  read -r -a arch_list <<< "$archs"
  if [[ "${#arch_list[@]}" -ne 2 ||
        "${arch_list[0]}" != arm64 || "${arch_list[1]}" != arm64e ]]; then
    printf 'FAT%s static archive unexpectedly contains %s\n' "$fat" "$archs" >&2
    exit 1
  fi
  "$lipo" -thin arm64 "$work/both-$fat.a" -o "$work/thin-$fat-a.a"
  "$lipo" -thin arm64e "$work/both-$fat.a" -o "$work/thin-$fat-e.a"
  cmp "$work/lib-a.a" "$work/thin-$fat-a.a"
  cmp "$work/lib-e.a" "$work/thin-$fat-e.a"

  # The ARM64e linker must extract the indexed ARM64e member from FAT32
  # and FAT64 archives, retaining the PAC ABI in the linked image.
  "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib -fixup_chains \
    "$work/client-e.o" "$work/both-$fat.a" -o "$work/from-fat-$fat.dylib"
  python3 - "$work/from-fat-$fat.dylib" <<'PY'
import pathlib
import struct
import sys

header = pathlib.Path(sys.argv[1]).read_bytes()[:12]
assert struct.unpack('<III', header) == (0xfeedfacf, 0x0100000c, 0x80000002), \
    'LLD lost ARM64e PAC ABI when linking a universal static archive'
PY
  "$ld" -arch arm64 -platform_version macos 13.0 13.0 -dylib \
    -u _only_a "$work/both-$fat.a" -o "$work/from-fat-$fat-arm64.dylib"

  # Default ARM64 output must take the exact slice, even if a compatible
  # ARM64e one is present. Never reverse-fallback to an ARM64e-only image.
  "$ld" -arch arm64 -platform_version macos 13.0 13.0 -dylib \
    -u _only_a "$work/both-$fat.dylib" -o "$work/default-$fat.dylib"
  python3 - "$work/default-$fat.dylib" "$work/from-fat-$fat-arm64.dylib" <<'PY'
import pathlib
import struct
import sys

for filename in sys.argv[1:]:
    header = pathlib.Path(filename).read_bytes()[:12]
    assert struct.unpack('<III', header) == (
        0xfeedfacf, 0x0100000c, 0
    ), f"ordinary ARM64 output changed ABI: {filename}"
PY
  for suffix in a dylib; do
    input_file="$work/arm64e-$fat.$suffix"
    if "$ld" -arch arm64 -platform_version macos 13.0 13.0 -dylib \
        -u _only_e "$input_file" -o "$work/reverse-$fat-$suffix.dylib" \
        >"$work/reverse.log" 2>&1; then
      echo "ARM64 output improperly accepted ARM64e-only universal $suffix" >&2
      exit 1
    fi
    grep -Fq 'ignoring file because it is universal (arm64e) but does not contain the arm64 architecture' \
      "$work/reverse.log" || { cat "$work/reverse.log" >&2; exit 1; }
  done

  # Missing ARM64e archive slices must not fall back to plain ARM64 object
  # code, unlike the dynamic-library-only compatibility exception.
  if "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib \
      -u _only_a "$work/arm64-$fat.a" \
      -o "$work/invalid-archive-$fat.dylib" > "$work/archive-error.log" 2>&1; then
    echo "ARM64 archive incorrectly selected as ARM64e output" >&2
    exit 1
  fi
  grep -Fq 'ignoring file because it is universal (arm64) but does not contain the arm64e architecture' \
    "$work/archive-error.log" || { cat "$work/archive-error.log" >&2; exit 1; }

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

# Alter only FAT64 metadata: an arm64e-labeled outer archive cannot cause
# LLD to reinterpret an ordinary ARM64 object as authenticated ARM64e.
python3 - "$work/arm64-64.a" "$work/spoofed-arm64e.a" <<'PY'
import pathlib
import struct
import sys

data = bytearray(pathlib.Path(sys.argv[1]).read_bytes())
assert struct.unpack_from('>I', data, 0)[0] == 0xcafebabf
struct.pack_into('>I', data, 12, 0x80000002)
pathlib.Path(sys.argv[2]).write_bytes(data)
PY
if "$ld" -arch arm64e -platform_version macos 13.0 13.0 -dylib \
    -u _only_a "$work/spoofed-arm64e.a" \
    -o "$work/spoofed.dylib" > "$work/archive-error.log" 2>&1; then
  echo 'LLD accepted forged ARM64e fat archive descriptor' >&2
  exit 1
fi
grep -Fq 'unsupported arm64e pointer-authentication ABI' \
  "$work/archive-error.log" || { cat "$work/archive-error.log" >&2; exit 1; }

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
echo "Darwin FAT32/FAT64 default ABI, exact slices, compatible dylib fallback and ABI guards: passed"
