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
[[ ${#compiler_command[@]} -gt 0 ]] || exit 1

probe_dir="$(mktemp -d "${TMPDIR:-/tmp}/whp-lld-arm64e.XXXXXX")"
trap 'rm -rf "$probe_dir"' EXIT

printf '%s\n' \
    '.text' '.globl _whp_auth_target' '_whp_auth_target:' '  ret' \
    '.data' '.p2align 3' \
    '.quad _whp_auth_target@AUTH(ia,42,addr)' > "$probe_dir/auth.s"

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
