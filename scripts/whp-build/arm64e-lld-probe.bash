#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

# Link-only ARM64e Mach-O LLD capability check shared by the native LLVM
# bootstrap and QEMU host policy. A trivial main() link does not exercise
# ARM64_RELOC_AUTHENTICATED_POINTER. Never execute this test image: some
# macOS versions can link arm64e while disallowing third-party execution.
if [[ $# != 5 ]]; then
    printf 'usage: %s <clang> <SDKROOT> <deployment> <ld64.lld> <llvm-objdump>\n' "$0" >&2
    exit 2
fi
compiler="$1"
sdkroot="$2"
deployment_target="$3"
linker="$4"
objdump="$5"
[[ -x "$linker" && -x "$objdump" && -d "$sdkroot" ]] || exit 1

compiler_command=()
read -r -a compiler_command <<< "$compiler"
[[ -n "${compiler_command[0]:-}" ]] || exit 1

probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/whp-lld-arm64e.XXXXXX")"
trap 'rm -rf "$probe_dir"' EXIT

printf '%s\n' \
    '.text' '.globl _whp_auth_target' '_whp_auth_target:' '  ret' \
    '.data' '.p2align 3' \
    '.quad _whp_auth_target@AUTH(ia,42,addr)' \
    '.quad _whp_auth_target@AUTH(ib,4660)' \
    '.quad _whp_auth_target@AUTH(da,48879,addr)' \
    '.quad _whp_auth_target@AUTH(db,65535)' > "$probe_dir/auth.s"

"${compiler_command[@]}" -arch arm64e -isysroot "$sdkroot" \
    "-mmacosx-version-min=$deployment_target" -x assembler -c \
    "$probe_dir/auth.s" -o "$probe_dir/auth.o" >/dev/null 2>&1

"$linker" -arch arm64e \
    -platform_version macos "$deployment_target" "$deployment_target" \
    -dylib -install_name @rpath/libwhp_auth.dylib \
    "$probe_dir/auth.o" -o "$probe_dir/libwhp_auth.dylib" >/dev/null 2>&1

"$objdump" --macho --chained-fixups "$probe_dir/libwhp_auth.dylib" \
    > "$probe_dir/fixups.txt" 2>/dev/null
grep -Fq 'DYLD_CHAINED_PTR_ARM64E_USERLAND24' "$probe_dir/fixups.txt"

# llvm-otool is the same LLVM Mach-O parser accessed via the otool-compatible
# CLI. If installed next to llvm-objdump, verify that it can expose the same
# authenticated chain format. This is a CLI compatibility check, NOT an
# independent verification of fixup correctness (the Python decoder below
# remains the primary metadata test).
if [[ "$objdump" == */llvm-objdump ]]; then
    otool="${objdump%/llvm-objdump}/llvm-otool"
    if [[ -x "$otool" ]]; then
        "$otool" -chained_fixups "$probe_dir/libwhp_auth.dylib" \
            > "$probe_dir/otool-fixups.txt" 2>/dev/null
        grep -Fq 'DYLD_CHAINED_PTR_ARM64E_USERLAND24' \
            "$probe_dir/otool-fixups.txt"
        "$otool" -dyld_info "$probe_dir/libwhp_auth.dylib" \
            > "$probe_dir/otool-dyld.txt" 2>/dev/null
        grep -Eq '(^|[[:space:]])rebase([[:space:]]|$)' \
            "$probe_dir/otool-dyld.txt"
    fi
fi

# The format label alone cannot prove LLD has preserved signing metadata.
# Inspect all four PAC keys, 16-bit discriminators and address diversity in
# the encoded authenticated rebases, rather than only checking the pointer format.
"$objdump" --macho --dyld-info "$probe_dir/libwhp_auth.dylib" \
    > "$probe_dir/dyld.txt" 2>/dev/null
python3 - "$probe_dir/dyld.txt" <<'PY'
import pathlib
import sys

words = []
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    fields = line.split()
    if (len(fields) >= 5 and fields[0] == "__DATA" and
            fields[1] == "__data" and fields[4] == "rebase"):
        words.append(int(fields[3], 16))

expected = ((0, 42, 1), (1, 4660, 0), (2, 48879, 1),
            (3, 65535, 0))
if len(words) != len(expected):
    sys.exit(f"arm64e PAC probe: expected 4 authenticated rebases, "
             f"found {len(words)}")
for index, (word, schema) in enumerate(zip(words, expected)):
    actual = ((word >> 49) & 3, (word >> 32) & 65535,
              (word >> 48) & 1)
    if (word >> 63 != 1 or ((word >> 62) & 1) != 0 or actual != schema):
        sys.exit(f"arm64e PAC probe: relocation {index} lost metadata "
                 f"(expected {schema}, got {actual})")
if len({word & 0xffffffff for word in words}) != 1:
    sys.exit("arm64e PAC probe: authenticated rebase target drift")
PY

# A successful link is not enough: the compiler must emit authenticated
# indirect calls under the arm64e C ABI instead of plain BLR.
cat > "$probe_dir/call.c" <<'C'
__attribute__((noinline))
int whp_indirect_call(int (*volatile callback)(void)) {
    return callback();
}
C
"${compiler_command[@]}" -arch arm64e -isysroot "$sdkroot" \
    "-mmacosx-version-min=$deployment_target" -O0 -S \
    "$probe_dir/call.c" -o "$probe_dir/call.s" >/dev/null 2>&1
if ! grep -Eiq '(^|[[:space:]])blraa(z)?[[:space:]]' "$probe_dir/call.s"; then
    printf 'error: ARM64e Clang did not emit an authenticated indirect call\n' >&2
    exit 1
fi
