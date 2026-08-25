#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
roms="$root/roms"
seabios="$roms/seabios"
config="$roms/config.seabios-grub"

[[ -f "$seabios/Makefile" ]] || {
    printf 'SeaBIOS test source is not initialized: %s\n' "$seabios" >&2
    exit 1
}
[[ -f "$config" ]] || {
    printf 'GRUB SeaBIOS configuration is missing: %s\n' "$config" >&2
    exit 1
}

grep -Fxq 'CONFIG_COREBOOT=y' "$config"
grep -Fxq 'CONFIG_MULTIBOOT=y' "$config"
grep -Fxq 'CONFIG_COREBOOT_FLASH=n' "$config"
grep -Fq 'seabios-grub' "$roms/Makefile"
grep -Fq 'seabios-grub.elf' "$roms/Makefile"

for tool in make python3 cc ld objcopy objdump strip; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'missing GRUB SeaBIOS payload test tool: %s\n' "$tool" >&2
        exit 1
    }
done

scratch="$(mktemp -d "${TMPDIR:-/tmp}/seabios-grub.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/output"

make --no-print-directory -C "$roms" \
    SEABIOS_BUILD_ROOT="$scratch/build" \
    SEABIOS_OUTPUT_DIR="$scratch/output" \
    SEABIOS_CROSS_PREFIX= \
    seabios-grub

payload="$scratch/output/seabios-grub.elf"
[[ -f "$payload" ]] || {
    printf 'GRUB SeaBIOS payload was not produced: %s\n' "$payload" >&2
    exit 1
}

python3 - "$payload" <<'PY'
import pathlib
import struct
import sys

path = pathlib.Path(sys.argv[1])
data = path.read_bytes()
if len(data) < 52 or data[:4] != b'\x7fELF':
    raise SystemExit('SeaBIOS GRUB payload is not ELF')
if data[4] != 1 or data[5] != 1:
    raise SystemExit('SeaBIOS GRUB payload must be little-endian ELF32')
if struct.unpack_from('<H', data, 18)[0] != 3:
    raise SystemExit('SeaBIOS GRUB payload must target EM_386')
entry = struct.unpack_from('<I', data, 24)[0]
if entry == 0:
    raise SystemExit('SeaBIOS GRUB payload has no ELF entry point')

magic = 0x1BADB002
window = data[:8192]
for offset in range(0, max(0, len(window) - 11), 4):
    got_magic, flags, checksum = struct.unpack_from('<III', window, offset)
    if got_magic == magic and ((got_magic + flags + checksum) & 0xffffffff) == 0:
        break
else:
    raise SystemExit('SeaBIOS GRUB payload has no valid Multiboot header in its first 8 KiB')

print(f'SeaBIOS GRUB payload: ELF32/i386 entry=0x{entry:08x} multiboot@0x{offset:x}')
PY

printf 'GRUB-loadable SeaBIOS payload: verified\n'
