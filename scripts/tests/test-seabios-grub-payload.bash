#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
roms="$root/roms"
seabios="$roms/seabios"
config="$roms/config.seabios-grub"
config_tool="$root/scripts/whp-config/config.py"
grub_prepare="$root/scripts/whp-build/prepare-seabios-grub.bash"
stages="$root/scripts/whp-build/stages.bash"
builder="$root/builder.sh"
targets="$root/scripts/whp-build/build-targets.bash"
meson="$root/pc-bios/meson.build"
meson_builder="$root/scripts/meson-build-seabios.sh"

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
grep -Fxq 'CONFIG_VGA_COREBOOT=y' "$config"
grep -Fq 'seabios-grub' "$roms/Makefile"
grep -Fq 'seabios-grub.elf' "$roms/Makefile"
python3 "$seabios/scripts/test-multiboot-video.py"

menu_dump="$(python3 "$config_tool" --dump-menu)"
grep -Fq 'Firmware' <<<"$menu_dump"
grep -Fq 'BUILD_SEABIOS_GRUB=n' <<<"$menu_dump"
grep -Fq "Option('BUILD_SEABIOS_GRUB', 'Firmware', 'Build GRUB-loadable SeaBIOS', 'bool', 'n')" "$config_tool"
grep -Fq 'BUILD_SEABIOS_GRUB' "$grub_prepare"
grep -Fq '.whp-seabios-grub-meson.env' "$grub_prepare"
grep -Fq 'rm -f "$BUILD_DIR/.whp-config"' "$grub_prepare"
grep -Fq 'prepare-seabios-grub.bash' "$stages"
grep -Fq 'whp_prepare_seabios_grub_sources' "$builder"
grep -Fq 'BUILD_SEABIOS_GRUB' "$targets"
grep -Fq 'whp-seabios-grub' "$meson"
grep -Fq -- '--grub' "$meson_builder"

for tool in make python3 cc ld objcopy objdump strip; do
    command -v "$tool" >/dev/null 2>&1 || {
        printf 'missing GRUB SeaBIOS payload test tool: %s\n' "$tool" >&2
        exit 1
    }
done

scratch="$(mktemp -d "${TMPDIR:-/tmp}/seabios-grub.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
mkdir -p "$scratch/output" "$scratch/bin" "$scratch/prep"

# Changing the GRUB payload marker must force one Meson reconfigure without
# deleting the persistent build tree. Repeating the same state must not cause
# needless reconfigure churn.
: > "$scratch/prep/.whp-config"
BUILD_DIR="$scratch/prep" BUILD_SEABIOS_GRUB=1 BUILD_SEABIOS=0 QEMU_TARGET_LIST= \
    bash -c '
        set -euo pipefail
        source "$1"
        whp_prepare_sources() { printf "prepared\n" > "$BUILD_DIR/.whp-seabios-meson.env"; }
        whp_prepare_seabios_grub_sources
    ' _ "$grub_prepare"
[[ -f "$scratch/prep/.whp-seabios-grub-meson.env" ]]
[[ ! -f "$scratch/prep/.whp-seabios-meson.env" ]]
[[ ! -f "$scratch/prep/.whp-config" ]]

: > "$scratch/prep/.whp-config"
BUILD_DIR="$scratch/prep" BUILD_SEABIOS_GRUB=1 BUILD_SEABIOS=0 QEMU_TARGET_LIST= \
    bash -c '
        set -euo pipefail
        source "$1"
        whp_prepare_sources() { printf "prepared\n" > "$BUILD_DIR/.whp-seabios-meson.env"; }
        whp_prepare_seabios_grub_sources
    ' _ "$grub_prepare"
[[ -f "$scratch/prep/.whp-config" ]]

BUILD_DIR="$scratch/prep" BUILD_SEABIOS_GRUB=0 BUILD_SEABIOS=0 QEMU_TARGET_LIST= \
    bash -c '
        set -euo pipefail
        source "$1"
        whp_prepare_sources() { :; }
        whp_prepare_seabios_grub_sources
    ' _ "$grub_prepare"
[[ ! -f "$scratch/prep/.whp-seabios-grub-meson.env" ]]
[[ ! -f "$scratch/prep/.whp-config" ]]

cat > "$scratch/bin/ninja" <<'SCRIPT'
#!/bin/sh
printf '%s\n' "$@" > "$WHP_GRUB_TEST_LOG"
SCRIPT
chmod +x "$scratch/bin/ninja"

BUILD_DIR="$scratch/qemu-build" \
BUILD_TARGETS=qemu-img \
BUILD_OPENBIOS=0 \
BUILD_SEABIOS=0 \
BUILD_SEABIOS_GRUB=1 \
INSTALL=0 \
JOBS=1 \
NINJA_CMD="$scratch/bin/ninja" \
MAKE_CMD= \
WHP_GRUB_TEST_LOG="$scratch/enabled.log" \
bash -c 'set -euo pipefail; source "$1"; whp_build_targets' _ "$targets"
grep -Fxq 'whp-seabios-grub' "$scratch/enabled.log"

BUILD_DIR="$scratch/qemu-build" \
BUILD_TARGETS=qemu-img \
BUILD_OPENBIOS=0 \
BUILD_SEABIOS=0 \
BUILD_SEABIOS_GRUB=0 \
INSTALL=0 \
JOBS=1 \
NINJA_CMD="$scratch/bin/ninja" \
MAKE_CMD= \
WHP_GRUB_TEST_LOG="$scratch/disabled.log" \
bash -c 'set -euo pipefail; source "$1"; whp_build_targets' _ "$targets"
if grep -Fxq 'whp-seabios-grub' "$scratch/disabled.log"; then
    printf 'GRUB SeaBIOS target was requested while disabled\n' >&2
    exit 1
fi

make --no-print-directory -C "$roms" \
    SEABIOS_BUILD_ROOT="$scratch/build" \
    SEABIOS_OUTPUT_DIR="$scratch/output" \
    SEABIOS_CROSS_PREFIX= \
    seabios-grub

payload="$scratch/output/seabios-grub.elf"
vgabios="$scratch/build/seabios-grub/vgabios.bin"
[[ -f "$payload" ]] || {
    printf 'GRUB SeaBIOS payload was not produced: %s\n' "$payload" >&2
    exit 1
}
[[ -f "$vgabios" ]] || {
    printf 'GRUB framebuffer VGA BIOS was not produced: %s\n' "$vgabios" >&2
    exit 1
}

python3 - "$payload" "$vgabios" <<'PY'
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

rom = pathlib.Path(sys.argv[2]).read_bytes()
if len(rom) < 512 or rom[:2] != b'\x55\xaa':
    raise SystemExit('GRUB framebuffer VGA BIOS is not an option ROM')
if sum(rom) & 0xff:
    raise SystemExit('GRUB framebuffer VGA BIOS has an invalid option-ROM checksum')

print(f'SeaBIOS GRUB payload: ELF32/i386 entry=0x{entry:08x} multiboot@0x{offset:x}')
print(f'GRUB framebuffer VGA BIOS: {len(rom)} bytes, checksum valid')
PY

printf 'GRUB-loadable SeaBIOS payload with framebuffer VGA: verified\n'
