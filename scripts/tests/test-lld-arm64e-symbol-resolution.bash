#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Exercise pinned LLD's ARM64e symbol resolution, not the host's ld64.
set -euo pipefail

if [[ $# != 1 ]]; then
    printf 'usage: %s <ld64.lld>\n' "$0" >&2
    exit 2
fi
linker="$1"
[[ -x "$linker" ]] || { echo "error: missing LLD: $linker" >&2; exit 1; }
objdump="${linker%/ld64.lld}/llvm-objdump"
[[ -x "$objdump" ]] || { echo "error: missing llvm-objdump" >&2; exit 1; }

fixture="llvm-project/lld/test/MachO/arm64e-symbol-resolution.s"
[[ -f "$fixture" ]] || { echo "error: missing pinned LLVM test fixture" >&2; exit 1; }
work="$(mktemp -d "${TMPDIR:-/tmp}/whp-arm64e-symbols.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# Read LLVM's authoritative split-file fixture; no duplicate assembly source.
awk -v directory="$work" '
  /^#--- / { file = $2; next }
  file != "" { print > (directory "/" file) }
' "$fixture"

for name in lib strong weak flat valid; do
    xcrun clang -arch arm64e -mmacosx-version-min=13.0 -c \
        "$work/$name.s" -o "$work/$name.o"
done

"$linker" -arch arm64e -platform_version macos 13.0 13.0 \
    -dylib -install_name @rpath/libtargets.dylib \
    "$work/lib.o" -o "$work/libtargets.dylib"

"$linker" -arch arm64e -platform_version macos 13.0 13.0 \
    -bundle -fixup_chains -undefined dynamic_lookup \
    "$work/valid.o" "$work/libtargets.dylib" -o "$work/valid.bundle"

"$objdump" --macho --chained-fixups "$work/valid.bundle" > "$work/fixups.txt"
for needle in 'DYLD_CHAINED_PTR_ARM64E_USERLAND24' '_external' '_weak' '_host'; do
    grep -Fq "$needle" "$work/fixups.txt" || {
        printf 'error: linked ARM64e bundle lost %s\n' "$needle" >&2
        exit 1
    }
done

cases=(strong weak flat)
symbols=(_external _weak _host)
for i in "${!cases[@]}"; do
    case_name="${cases[$i]}"
    symbol="${symbols[$i]}"
    args=(-arch arm64e -platform_version macos 13.0 13.0)
    if [[ "$case_name" == flat ]]; then
        args+=(-bundle -undefined dynamic_lookup "$work/flat.o")
        output="$work/invalid-flat.bundle"
    else
        args+=(-dylib "$work/$case_name.o" "$work/libtargets.dylib")
        output="$work/invalid-$case_name.dylib"
    fi
    if "$linker" "${args[@]}" -o "$output" > "$work/error.log" 2>&1; then
        printf 'error: LLD accepted branch into authenticated stub for %s\n' \
            "$symbol" >&2
        exit 1
    fi
    grep -Fq "BRANCH26 relocation cannot target an offset within dynamically bound symbol $symbol" \
        "$work/error.log" || {
        cat "$work/error.log" >&2
        exit 1
    }
done
echo "ARM64e symbol resolution: authenticated imports and stub offsets verified"
