#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(CDPATH= cd -P -- "$(dirname "$0")/../.." && pwd -P)
seed=$root/seeds/objcopy.sh
unset WHP_OBJCOPY_SEED OBJCOPY_FOR_BUILD WHP_OBJCOPY_PROBE_OBJECT WHP_OBJCOPY_PROBE_BINARY
sh -n "$seed"
tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-objcopy-test.XXXXXX")
trap 'rm -rf -- "$tmp"' 0
trap 'exit 1' 1 2 3 15
reject()
{
    if "$@" >"$tmp/reject.out" 2>"$tmp/reject.err"; then
        printf '%s\n' 'error: unexpected objcopy seed success' >&2
        exit 1
    fi
    [ ! -s "$tmp/reject.out" ]
}
reject env WHP_OBJCOPY_SEED="$tmp/missing" "$seed" --print-seed
ln -s "$seed" "$tmp/recursive"
reject env WHP_OBJCOPY_SEED="$tmp/recursive" "$seed" --print-seed
reject env WHP_OBJCOPY_PROBE_OBJECT="$tmp/missing" "$seed" --print-seed
reject "$seed" --version
printf '%s\n' '.text' '.byte 0x12, 0x34, 0x56, 0x78' > "$tmp/input.S"
clang --target=i386-unknown-none -c "$tmp/input.S" -o "$tmp/input.o"
printf '\022\064\126\170' > "$tmp/expected.bin"
printf 'wrong' > "$tmp/wrong.bin"
provider=$("$seed" --print-seed)
[ -x "$provider" ]
env WHP_OBJCOPY_SEED="$provider" "$seed" --check
for name in objcopy llvm-objcopy gobjcopy; do
    tool=$(command -v "$name" 2>/dev/null) || continue
    # A native build tool need not understand a foreign object; require the
    # exact fixture only from providers that support i386 ELF conversion.
    if ! "$tool" -O binary "$tmp/input.o" "$tmp/candidate.bin" 2>/dev/null; then
        continue
    fi
    cmp -s "$tmp/expected.bin" "$tmp/candidate.bin"
    selected=$(env WHP_OBJCOPY_SEED="$tool" OBJCOPY_FOR_BUILD="$tmp/missing" \
        WHP_OBJCOPY_PROBE_OBJECT="$tmp/input.o" WHP_OBJCOPY_PROBE_BINARY="$tmp/expected.bin" \
        "$seed" --print-objcopy)
    [ "$selected" = "$tool" ]
    reject env WHP_OBJCOPY_SEED="$tool" WHP_OBJCOPY_PROBE_OBJECT="$tmp/input.o" \
        WHP_OBJCOPY_PROBE_BINARY="$tmp/wrong.bin" "$seed" --print-seed
    env WHP_OBJCOPY_SEED="$selected" "$seed" -O binary "$tmp/input.o" "$tmp/output with spaces.bin"
    cmp -s "$tmp/expected.bin" "$tmp/output with spaces.bin"
    tested=yes
done
[ "${tested:-no}" = yes ]
printf '%s\n' 'WHP objcopy seed: native and i386 firmware regression passed'
