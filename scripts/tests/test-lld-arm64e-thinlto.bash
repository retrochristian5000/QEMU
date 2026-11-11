#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Verify ARM64e ThinLTO native output and PAC fixups using the pinned LLVM.
set -euo pipefail
if [[ $# != 5 ]]; then
    echo 'usage: test-lld-arm64e-thinlto.bash <ld64.lld> <opt> <llvm-readobj> <llvm-objdump> <llvm-lto2>' >&2
    exit 2
fi
ld="$1"
opt="$2"
readobj="$3"
objdump="$4"
lto2="$5"
for tool in "$ld" "$opt" "$readobj" "$objdump" "$lto2"; do
    [[ -x "$tool" ]] || { echo "missing LLVM tool: $tool" >&2; exit 1; }
done

fixture="llvm-project/lld/test/MachO/thinlto-arm64e-abi.ll"
[[ -f "$fixture" ]] || { echo "missing pinned ThinLTO fixture: $fixture" >&2; exit 1; }
work="$(mktemp -d "${TMPDIR:-/tmp}/whp-arm64e-thinlto.XXXXXX")"
trap 'rm -rf "$work"' EXIT

awk -v dir="$work" '
    /^;--- / {file=$2; next}
    file!="" {print > (dir "/" file)}
' "$fixture"

for name in auth impl arm64; do
    "$opt" -module-summary "$work/$name.ll" -o "$work/$name.o"
done

"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
    -dylib -fixup_chains -object_path_lto "$work/generated" \
    -cache_path_lto "$work/cache" \
    "$work/auth.o" "$work/impl.o" -o "$work/libauth.dylib"

# LLVM writes individual native outputs under the architecture-specific name.
[[ -s "$work/generated/1.arm64e.lto.o" ]] || {
    echo 'missing ARM64e ThinLTO native object' >&2
    exit 1
}
"$readobj" --file-headers "$work/generated/1.arm64e.lto.o" >"$work/headers.txt"
grep -Fq 'CpuSubType: CPU_SUBTYPE_ARM64E (0x2)' "$work/headers.txt"
grep -Fq 'CpuSubTypeCapabilities: 0x80000000' "$work/headers.txt"
grep -Fq 'PointerAuthABI: Userland' "$work/headers.txt"
grep -Fq 'PointerAuthABIVersion: 0' "$work/headers.txt"

"$objdump" --macho --chained-fixups "$work/libauth.dylib" >"$work/fixups.txt"
grep -Fq 'DYLD_CHAINED_PTR_ARM64E_USERLAND24' "$work/fixups.txt"
"$readobj" --relocations "$work/generated/1.arm64e.lto.o" >"$work/relocs.txt"
grep -Fq 'ARM64_RELOC_AUTHENTICATED_POINTER' "$work/relocs.txt" || {
    cat "$work/relocs.txt" >&2
    echo 'ThinLTO lost ARM64e authenticated pointer relocation' >&2
    exit 1
}

# Re-link with a populated ThinLTO cache, so cached objects get the same PAC ABI.
"$ld" -arch arm64e -platform_version macos 13.0 13.0 \
    -dylib -fixup_chains -cache_path_lto "$work/cache" \
    "$work/auth.o" "$work/impl.o" -o "$work/libauth-cached.dylib"
"$objdump" --macho --chained-fixups "$work/libauth-cached.dylib" > "$work/cached.txt"
grep -Fq 'DYLD_CHAINED_PTR_ARM64E_USERLAND24' "$work/cached.txt"

# A regular ARM64 dylib can be a runtime import but ARM64 bitcode cannot be
# compiled as ARM64e. Test the inverse boundary too.
for target in arm64e arm64; do
    if [[ "$target" == arm64e ]]; then
        bitcode="$work/arm64.o"
        expected='arm64e output requires arm64e bitcode'
    else
        bitcode="$work/auth.o"
        expected='arm64e bitcode is incompatible with an arm64 output'
    fi
    if "$ld" -arch "$target" -platform_version macos 13.0 13.0 \
        -dylib "$bitcode" -o "$work/rejected-$target.dylib" \
        > "$work/rejection.log" 2>&1; then
        echo "LLD incorrectly accepted a ThinLTO ABI mismatch ($target)" >&2
        exit 1
    fi
    grep -Fq "$expected" "$work/rejection.log" || {
        cat "$work/rejection.log" >&2
        exit 1
    }
done

"$ld" -arch arm64 -platform_version macos 13.0 13.0 \
    -dylib "$work/arm64.o" -o "$work/libarm64.dylib"
"$readobj" --file-headers "$work/libarm64.dylib" >"$work/plain-headers.txt"
grep -Fq 'CpuSubType: CPU_SUBTYPE_ARM64_ALL (0x0)' "$work/plain-headers.txt"
# The shared LLVM LTO engine is also used by clients other than ld64.lld.
# Test it directly, including reversal of the input module order.
shared_fixture="llvm-project/llvm/test/ThinLTO/AArch64/darwin-arm64e-abi-mix.ll"
[[ -f "$shared_fixture" ]] || {
    echo "missing shared ThinLTO ARM64e regression" >&2
    exit 1
}
mkdir -p "$work/lto-shared"
awk -v dir="$work/lto-shared" '
    /^;--- / {file=$2; next}
    file!="" {print > (dir "/" file)}
' "$shared_fixture"
for target in arm64 arm64e; do
    "$opt" -thinlto-bc "$work/lto-shared/$target.ll" -o "$work/lto-shared/$target.bc"
done
for order in forward reverse; do
    if [[ "$order" == forward ]]; then
        first=arm64
        second=arm64e
    else
        first=arm64e
        second=arm64
    fi
    if "$lto2" run "$work/lto-shared/$first.bc" "$work/lto-shared/$second.bc" \
         -o "$work/lto-shared/$order" \
         -r="$work/lto-shared/arm64.bc,plain_entry,px" \
         -r="$work/lto-shared/arm64e.bc,auth_entry,px" \
         >"$work/lto-shared/error.log" 2>&1; then
        echo "shared LLVM ThinLTO accepted mixed Darwin ARM64 ABIs" >&2
        exit 1
    fi
    grep -Fq 'cannot mix Darwin arm64 and arm64e bitcode in one LTO link' \
        "$work/lto-shared/error.log" || {
        cat "$work/lto-shared/error.log" >&2
        exit 1
    }
done
echo 'ARM64e ThinLTO PAC, native ABI, caching, and cross-ABI guards: passed'
