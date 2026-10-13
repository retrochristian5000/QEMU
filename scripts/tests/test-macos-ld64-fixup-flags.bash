#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

# Compare Apple ld and the pinned LLD on matching ARM64 Mach-O inputs.
# This is a *link and load-command* test; it does not prove dyld execution.
if [[ "$(uname -s)" != Darwin || $# != 2 ]]; then
    printf 'usage (macOS): %s <ld64.lld> <llvm-objdump>\n' "$0" >&2
    exit 2
fi
lld="$1"
objdump="$2"
[[ -x "$lld" && -x "$objdump" ]] || {
    printf 'error: Mach-O LLD and llvm-objdump must be executable\n' >&2
    exit 1
}
apple_ld="$(xcrun --find ld)"
clang="$(xcrun --find clang)"
sdk_version="$(xcrun --sdk macosx --show-sdk-version)"
work="$(mktemp -d "${TMPDIR:-/tmp}/whp-ld64-macos12.XXXXXX")"
trap 'rm -rf "$work"' EXIT

cat > "$work/fixups.s" <<'ASM'
.text
.globl _whp_linker_target
_whp_linker_target:
  ret
.data
.p2align 3
.quad _whp_linker_target
ASM
"$clang" -arch arm64 -c "$work/fixups.s" -o "$work/fixups.o"

inspect()
{
    local binary="$1"
    local expected="$2"
    local header="$binary.headers"
    "$objdump" --macho --all-headers "$binary" > "$header"
    if [[ "$expected" == chained ]]; then
        grep -Fq 'cmd LC_DYLD_CHAINED_FIXUPS' "$header"
        if grep -Fq 'cmd LC_DYLD_INFO_ONLY' "$header"; then
            printf 'error: unwanted legacy dyld fixups: %s\n' "$binary" >&2
            return 1
        fi
    else
        grep -Fq 'cmd LC_DYLD_INFO_ONLY' "$header"
        if grep -Fq 'cmd LC_DYLD_CHAINED_FIXUPS' "$header"; then
            printf 'error: unexpected chained fixups: %s\n' "$binary" >&2
            return 1
        fi
    fi
}

# Apple's default changes at macOS 12, not 13. Both linkers must respect
# explicit fixup flags on ordinary arm64; authenticated arm64e is separately
# tested by the existing PAC metadata and native dyld execution workflows.
for linker in apple lld; do
    if [[ "$linker" == apple ]]; then
        selected="$apple_ld"
    else
        selected="$lld"
    fi
    for case_name in default11 default12 optout12 optin11; do
        version=12.0
        extra=()
        expected=chained
        case "$case_name" in
            default11) version=11.0; expected=legacy ;;
            default12) ;;
            optout12) extra=(-no_fixup_chains); expected=legacy ;;
            optin11) version=11.0; extra=(-fixup_chains) ;;
        esac
        output="$work/$linker-$case_name.dylib"
        "$selected" -arch arm64 \
            -platform_version macos "$version" "$sdk_version" \
            -dylib "${extra[@]}" \
            -install_name @rpath/libwhp-linker-test.dylib \
            "$work/fixups.o" -o "$output"
        inspect "$output" "$expected"
        printf 'ld64 fixups: %s %s -> %s\n' "$linker" "$case_name" "$expected"
    done
done
