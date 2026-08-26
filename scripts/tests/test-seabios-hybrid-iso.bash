#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
config_tool="$root/scripts/whp-config/config.py"
prepare="$root/scripts/whp-build/prepare-seabios-grub.bash"
targets="$root/scripts/whp-build/build-targets.bash"
meson="$root/pc-bios/meson.build"
iso_builder="$root/scripts/build-seabios-hybrid-iso.sh"

menu_dump="$(python3 "$config_tool" --dump-menu)"
grep -Fq 'BUILD_SEABIOS_HYBRID_ISO=n' <<<"$menu_dump"
grep -Fq "Option('BUILD_SEABIOS_HYBRID_ISO', 'Firmware', 'Build hybrid x86 UEFI SeaBIOS ISO', 'bool', 'n')" "$config_tool"
grep -Fq 'BUILD_SEABIOS_HYBRID_ISO' "$prepare"
grep -Fq '.whp-seabios-hybrid-iso.env' "$prepare"
grep -Fq "printf 'SEABIOS_BUILD_ROOT=%q" "$prepare"
grep -Fq 'GRUB_I386_MKIMAGE' "$prepare"
grep -Fq 'GRUB_X86_64_MKIMAGE' "$prepare"
grep -Fq 'GRUB_I386_MODULE_DIR' "$prepare"
grep -Fq 'GRUB_X86_64_MODULE_DIR' "$prepare"
grep -Fq 'GRUB_I386_INSTALL_PREFIX' "$prepare"
grep -Fq 'GRUB_X86_64_INSTALL_PREFIX' "$prepare"
grep -Fq 'HOMEBREW_PREFIX' "$prepare"
grep -Fq 'BUILD_SEABIOS_HYBRID_ISO' "$targets"
grep -Fq 'whp-seabios-hybrid-iso' "$meson"
[[ -f "$iso_builder" ]] || {
    printf 'hybrid SeaBIOS ISO builder is missing: %s\n' "$iso_builder" >&2
    exit 1
}

grep -Fq 'i686-elf-grub-mkimage' "$iso_builder"
grep -Fq 'x86_64-elf-grub-mkimage' "$iso_builder"
grep -Fq 'GRUB_I386_MODULE_DIR' "$iso_builder"
grep -Fq 'GRUB_X86_64_MODULE_DIR' "$iso_builder"
grep -Fq 'GRUB_I386_INSTALL_PREFIX' "$iso_builder"
grep -Fq 'GRUB_X86_64_INSTALL_PREFIX' "$iso_builder"
grep -Fq 'brew --prefix "$formula"' "$iso_builder"
grep -Fq 'moddep.lst' "$iso_builder"
grep -Fq 'i386-efi' "$iso_builder"
grep -Fq 'x86_64-efi' "$iso_builder"
grep -Fq 'BOOTIA32.EFI' "$iso_builder"
grep -Fq 'BOOTX64.EFI' "$iso_builder"
grep -Fq 'EFI/efiboot.img' "$iso_builder"
grep -Fq 'seabios-grub/vgabios.bin' "$iso_builder"
grep -Fq 'set gfxpayload=keep' "$iso_builder"
grep -Fq 'name=vgaroms/whp-grub-framebuffer.rom' "$iso_builder"
grep -Fq -- '-efi-boot-part' "$iso_builder"
grep -Fq -- '--efi-boot-image' "$iso_builder"

scratch="$(mktemp -d "${TMPDIR:-/tmp}/seabios-hybrid-iso.XXXXXX")"
trap 'rm -rf "$scratch"' EXIT
seabios_build_root="$scratch/firmware-build/seabios"
homebrew_prefix="$scratch/homebrew"
i386_modules="$scratch/grub-i386/lib/grub/i386-efi"
x86_64_formula_prefix="$homebrew_prefix/opt/x86_64-elf-grub"
x86_64_modules="$x86_64_formula_prefix/lib/x86_64-elf/grub/x86_64-efi"
mkdir -p "$scratch/bin" "$scratch/build" "$seabios_build_root/seabios-grub" \
    "$i386_modules" "$x86_64_modules"
printf 'multiboot-seabios\n' > "$scratch/seabios-grub.elf"
printf '\x55\xaaGRUB-framebuffer-vgabios\n' > "$seabios_build_root/seabios-grub/vgabios.bin"
: > "$i386_modules/moddep.lst"
: > "$x86_64_modules/moddep.lst"

cat > "$scratch/bin/grub-mkimage" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$WHP_ISO_TEST_MKIMAGE_LOG"
out=
format=
while (( $# )); do
    case "$1" in
        -o) out="$2"; shift 2 ;;
        -O) format="$2"; shift 2 ;;
        *) shift ;;
    esac
done
[[ -n "$out" && -n "$format" ]]
printf 'EFI:%s\n' "$format" > "$out"
SCRIPT

cat > "$scratch/bin/brew" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
[[ "${1:-}" == --prefix ]] || exit 2
case "${2:-}" in
    '') printf '%s\n' "$WHP_TEST_HOMEBREW_PREFIX" ;;
    x86_64-elf-grub) printf '%s\n' "$WHP_TEST_X86_64_GRUB_PREFIX" ;;
    i686-elf-grub) printf '%s\n' "$WHP_TEST_I686_GRUB_PREFIX" ;;
    *) exit 1 ;;
esac
SCRIPT

cat > "$scratch/bin/mformat" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf 'mformat %s\n' "$*" >> "$WHP_ISO_TEST_MTOOLS_LOG"
SCRIPT

cat > "$scratch/bin/mmd" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf 'mmd %s\n' "$*" >> "$WHP_ISO_TEST_MTOOLS_LOG"
SCRIPT

cat > "$scratch/bin/mcopy" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf 'mcopy %s\n' "$*" >> "$WHP_ISO_TEST_MTOOLS_LOG"
SCRIPT

cat > "$scratch/bin/xorriso" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" > "$WHP_ISO_TEST_XORRISO_LOG"
out=
for (( i=1; i <= $#; i++ )); do
    if [[ "${!i}" == -o ]]; then
        j=$((i + 1))
        out="${!j}"
        break
    fi
done
[[ -n "$out" ]]
root="${!#}"
find "$root" -type f -print | sort > "$WHP_ISO_TEST_TREE_LOG"
cat "$root/boot/grub/grub.cfg" > "$WHP_ISO_TEST_GRUB_CFG_LOG"
printf 'hybrid-iso\n' > "$out"
SCRIPT
chmod +x "$scratch/bin/"*

cat > "$scratch/tools.env" <<EOF
GRUB_MKIMAGE=$scratch/bin/grub-mkimage
GRUB_I386_MODULE_DIR=$i386_modules
HOMEBREW_PREFIX=$homebrew_prefix
XORRISO=$scratch/bin/xorriso
MFORMAT=$scratch/bin/mformat
MMD=$scratch/bin/mmd
MCOPY=$scratch/bin/mcopy
SEABIOS_BUILD_ROOT=$seabios_build_root
EOF

PATH="$scratch/bin:$PATH" \
WHP_TEST_HOMEBREW_PREFIX="$homebrew_prefix" \
WHP_TEST_X86_64_GRUB_PREFIX="$x86_64_formula_prefix" \
WHP_TEST_I686_GRUB_PREFIX="$homebrew_prefix/opt/i686-elf-grub" \
WHP_ISO_TEST_MKIMAGE_LOG="$scratch/mkimage.log" \
WHP_ISO_TEST_MTOOLS_LOG="$scratch/mtools.log" \
WHP_ISO_TEST_XORRISO_LOG="$scratch/xorriso.log" \
WHP_ISO_TEST_TREE_LOG="$scratch/tree.log" \
WHP_ISO_TEST_GRUB_CFG_LOG="$scratch/grub.cfg.log" \
bash "$iso_builder" "$scratch/tools.env" \
    "$scratch/seabios-grub.elf" "$scratch/build/whp-seabios-hybrid.iso"

[[ -f "$scratch/build/whp-seabios-hybrid.iso" ]]
grep -F -- '-O i386-efi' "$scratch/mkimage.log" | grep -Fq -- "-d $i386_modules"
grep -F -- '-O x86_64-efi' "$scratch/mkimage.log" | grep -Fq -- "-d $x86_64_modules"
grep -Fq 'BOOTIA32.EFI' "$scratch/mkimage.log"
grep -Fq 'BOOTX64.EFI' "$scratch/mkimage.log"
grep -Fq 'multiboot' "$scratch/mkimage.log"
grep -Fq 'iso9660' "$scratch/mkimage.log"
grep -Fq 'search_fs_file' "$scratch/mkimage.log"
grep -Fq 'EFI/efiboot.img' "$scratch/xorriso.log"
grep -Fq -- '-efi-boot-part --efi-boot-image' "$scratch/xorriso.log"
grep -Fq '/boot/seabios/seabios-grub.elf' "$scratch/grub.cfg.log"
grep -Fq 'set gfxpayload=keep' "$scratch/grub.cfg.log"
grep -Fq 'multiboot /boot/seabios/seabios-grub.elf' "$scratch/grub.cfg.log"
grep -Fq 'module /boot/seabios/seabios-grub-vgabios.bin name=vgaroms/whp-grub-framebuffer.rom' "$scratch/grub.cfg.log"
grep -Fq 'seabios-grub.elf' "$scratch/tree.log"
grep -Fq 'seabios-grub-vgabios.bin' "$scratch/tree.log"

cat > "$scratch/bin/ninja" <<'SCRIPT'
#!/bin/sh
printf '%s\n' "$@" > "$WHP_ISO_TEST_TARGET_LOG"
SCRIPT
chmod +x "$scratch/bin/ninja"

BUILD_DIR="$scratch/qemu-build" \
BUILD_TARGETS=qemu-img \
BUILD_OPENBIOS=0 \
BUILD_SEABIOS=0 \
BUILD_SEABIOS_GRUB=0 \
BUILD_SEABIOS_HYBRID_ISO=1 \
INSTALL=0 JOBS=1 \
NINJA_CMD="$scratch/bin/ninja" MAKE_CMD= \
WHP_ISO_TEST_TARGET_LOG="$scratch/target.log" \
bash -c 'set -euo pipefail; source "$1"; whp_build_targets' _ "$targets"
grep -Fxq 'whp-seabios-hybrid-iso' "$scratch/target.log"

printf 'hybrid x86 UEFI SeaBIOS stable GRUB module wiring: verified\n'
