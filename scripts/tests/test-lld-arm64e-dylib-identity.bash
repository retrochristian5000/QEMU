#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Check pinned LLD's LC_ID_DYLIB / LC_LOAD_DYLIB propagation on arm64e.
set -euo pipefail
if [[ $# -ne 1 || ! -x "$1" ]]; then
  printf 'usage: %s <ld64.lld>\n' "$0" >&2
  exit 2
fi
ld="$1"
fixture="llvm-project/lld/test/MachO/arm64e-dylib-identity.s"
decoder="llvm-project/lld/test/MachO/Inputs/arm64e-dylib-identity.py"
[[ -f "$fixture" && -f "$decoder" ]] || {
  echo 'missing pinned LLVM dylib-identity regression files' >&2
  exit 1
}
work="$(mktemp -d "${TMPDIR:-/tmp}/whp-dylib-id.XXXXXX")"
trap 'rm -rf "$work"' EXIT
awk -v dir="$work" '/^#--- / {file=$2; next} file!="" {print > (dir "/" file)}' "$fixture"

for name in provider client; do
  xcrun clang -arch arm64e -mmacosx-version-min=13.0 \
    -c "$work/$name.s" -o "$work/$name.o"
done

# ID in producer, independently set ID in consumer, imported LOAD from producer.
"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
  -dylib -fixup_chains -install_name @rpath/libwhp-identity.dylib \
  -current_version 12.34.56 -compatibility_version 3.4.5 \
  "$work/provider.o" -o "$work/provider.dylib"
python3 "$decoder" "$work/provider.dylib" 6 id \
  @rpath/libwhp-identity.dylib 12.34.56 3.4.5

"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
  -dylib -fixup_chains -install_name @rpath/libwhp-consumer.dylib \
  -current_version 7.8.9 -compatibility_version 1.2.3 \
  "$work/client.o" "$work/provider.dylib" -o "$work/client.dylib"
python3 "$decoder" "$work/client.dylib" 6 id \
  @rpath/libwhp-consumer.dylib 7.8.9 1.2.3
python3 "$decoder" "$work/client.dylib" 6 load \
  @rpath/libwhp-identity.dylib 12.34.56 3.4.5

"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
  -dylib "$work/provider.o" -o "$work/default.dylib"
python3 "$decoder" "$work/default.dylib" 6 id "$work/default.dylib" 0 0

"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
  -dylib -final_output @rpath/libwhp-universal.dylib \
  "$work/provider.o" -o "$work/temp-slice.dylib"
python3 "$decoder" "$work/temp-slice.dylib" 6 id \
  @rpath/libwhp-universal.dylib 0 0

"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
  -dylib -final_output @rpath/wrong-default.dylib \
  -dylib_install_name @loader_path/libwhp-alias.dylib \
  -dylib_current_version 65535.255.255 -dylib_compatibility_version 1.0.0 \
  "$work/provider.o" -o "$work/alias.dylib"
python3 "$decoder" "$work/alias.dylib" 6 id \
  @loader_path/libwhp-alias.dylib 65535.255.255 1.0.0

# QEMU plugins are bundles, even where the file suffix happens to be .dylib.
"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
  -bundle -install_name @rpath/not-an-id.dylib \
  "$work/provider.o" -o "$work/plugin.dylib"
python3 "$decoder" "$work/plugin.dylib" 8 none

if "$ld" -arch arm64e -platform_version macos 13.0 13.0 \
   -bundle -current_version 2.3 -compatibility_version 1.0 \
   "$work/provider.o" -o "$work/rejected.dylib" \
   >"$work/reject.log" 2>&1; then
  echo 'LLD improperly accepted dylib version flags for MH_BUNDLE' >&2
  exit 1
fi
grep -Fq 'only valid with -dylib' "$work/reject.log" || {
  cat "$work/reject.log" >&2
  exit 1
}
# Explicitly supplied zero-major versions and empty components are invalid,
# even though the *omitted* version fields legitimately default to zero.
for test_case in zero dots; do
  if [[ "$test_case" == zero ]]; then
    vers=(-current_version 0.1 -compatibility_version 0)
    expected=('-current_version 0.1: malformed version'
              '-compatibility_version 0: malformed version')
  else
    vers=(-current_version 2..3 -compatibility_version 1.2.)
    expected=('-current_version 2..3: malformed version'
              '-compatibility_version 1.2.: malformed version')
  fi
  if "$ld" -arch arm64e -platform_version macos 13.0 13.0 \
      -dylib "${vers[@]}" "$work/provider.o" -o "$work/bad-$test_case.dylib" \
      > "$work/version-error.log" 2>&1; then
    echo "LLD accepted invalid dylib version ($test_case)" >&2
    exit 1
  fi
  for message in "${expected[@]}"; do
    grep -Fq -- "$message" "$work/version-error.log" || {
      cat "$work/version-error.log" >&2
      exit 1
    }
  done
done
echo 'ARM64e dylib install-name/version identity and consumer propagation: passed'
