#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Verify ARM64e LTO symbol resolution with the pinned LLVM tools.
set -euo pipefail

if [[ $# -ne 6 ]]; then
    printf '%s\n' 'usage: test-lld-arm64e-lto-symbols.bash <ld64.lld> <opt> <llvm-readobj> <llvm-objdump> <llvm-ar> <llvm-ranlib>' >&2
    exit 2
fi
ld="$1"
opt="$2"
readobj="$3"
objdump="$4"
ar="$5"
ranlib="$6"

for tool in "$ld" "$opt" "$readobj" "$objdump" "$ar" "$ranlib"; do
    [[ -x "$tool" ]] || { printf 'missing LLVM tool: %s\n' "$tool" >&2; exit 1; }
done
fixture="llvm-project/lld/test/MachO/lto-arm64e-symbol-name-order.ll"
[[ -f "$fixture" ]] || {
    printf 'missing pinned ARM64e LTO symbol fixture: %s\n' "$fixture" >&2
    exit 1
}
work="$(mktemp -d "/tmp/whp-arm64e-lto-symbols.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# Reuse the LLVM lit fixture to prevent test-source drift between projects.
awk -v dir="$work" '
    /^;--- / {name=$2; next}
    name!="" {print > (dir "/" name)}
' "$fixture"

for mode in thin full; do
    for name in reference definition; do
        if [[ "$mode" == thin ]]; then
            "$opt" -module-summary "$work/$name.ll" -o "$work/$name.$mode.o"
        else
            "$opt" "$work/$name.ll" -o "$work/$name.$mode.o"
        fi
    done
done

check_symbols()
{
    local output="$1"
    local label="$2"
    local symbols="$work/$label.syms"
    local header="$work/$label.header"

    "$objdump" --syms "$output" >"$symbols"
    for name in __Z6symboli _main; do
        if ! grep -Fq "$name" "$symbols"; then
            cat "$symbols" >&2
            printf 'error: %s lost Mach-O LTO symbol %s\n' "$label" "$name" >&2
            exit 1
        fi
    done
    "$readobj" --file-headers "$output" >"$header"
    for expected in \
        'CpuSubType: CPU_SUBTYPE_ARM64E (0x2)' \
        'CpuSubTypeCapabilities: 0x80000000' \
        'PointerAuthABI: Userland' \
        'PointerAuthABIVersion: 0'; do
        if ! grep -Fq "$expected" "$header"; then
            cat "$header" >&2
            printf 'error: %s lost ARM64e ABI metadata: %s\n' "$label" "$expected" >&2
            exit 1
        fi
    done
}

# Reference-first must not lose the symbol before its prevailing definition.
for mode in thin full; do
    for order in reference-first definition-first; do
        if [[ "$order" == reference-first ]]; then
            first=reference
            second=definition
        else
            first=definition
            second=reference
        fi
        output="$work/$mode-$order.dylib"
        "$ld" -arch arm64e -platform_version macos 13.0 13.0 \
            -dylib -fixup_chains -u _main \
            "$work/$first.$mode.o" "$work/$second.$mode.o" \
            -o "$output"
        check_symbols "$output" "$mode-$order"
    done
done

# Archive symbol indexing must resolve the same name in either input order.
"$ar" rcs "$work/definitions.a" "$work/definition.thin.o"
"$ranlib" "$work/definitions.a"
for order in reference-first archive-first; do
    if [[ "$order" == reference-first ]]; then
        first="$work/reference.thin.o"
        second="$work/definitions.a"
    else
        first="$work/definitions.a"
        second="$work/reference.thin.o"
    fi
    output="$work/$order.dylib"
    "$ld" -arch arm64e -platform_version macos 13.0 13.0 \
        -dylib -fixup_chains -u _main "$first" "$second" -o "$output"
    check_symbols "$output" "$order"
done

printf '%s\n' 'ARM64e FullLTO/ThinLTO C++ symbols, input order, and indexed archive: passed'
