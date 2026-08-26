#!/usr/bin/env bash
set -euo pipefail

if (( $# != 3 )); then
    printf 'usage: %s TOOL_CONFIG SEABIOS_GRUB_ELF OUTPUT_ISO\n' "$0" >&2
    exit 2
fi

tool_config="$1"
payload="$2"
output="$3"

[[ -f "$tool_config" ]] || {
    printf 'error: hybrid ISO tool configuration is missing: %s\n' "$tool_config" >&2
    exit 1
}
[[ -f "$payload" ]] || {
    printf 'error: GRUB-loadable SeaBIOS payload is missing: %s\n' "$payload" >&2
    exit 1
}

# shellcheck disable=SC1090
source "$tool_config"

legacy_grub_mkimage="${GRUB_MKIMAGE:-}"
GRUB_I386_MKIMAGE="${GRUB_I386_MKIMAGE:-${legacy_grub_mkimage:-i686-elf-grub-mkimage}}"
GRUB_X86_64_MKIMAGE="${GRUB_X86_64_MKIMAGE:-${legacy_grub_mkimage:-x86_64-elf-grub-mkimage}}"
GRUB_I386_MODULE_DIR="${GRUB_I386_MODULE_DIR:-${GRUB_I386_EFI_DIR:-}}"
GRUB_X86_64_MODULE_DIR="${GRUB_X86_64_MODULE_DIR:-${GRUB_X86_64_EFI_DIR:-}}"
GRUB_I386_PREFIX="${GRUB_I386_PREFIX:-}"
GRUB_X86_64_PREFIX="${GRUB_X86_64_PREFIX:-}"
XORRISO="${XORRISO:-xorriso}"
MFORMAT="${MFORMAT:-mformat}"
MMD="${MMD:-mmd}"
MCOPY="${MCOPY:-mcopy}"
: "${SEABIOS_BUILD_ROOT:?missing SEABIOS_BUILD_ROOT}"

vgabios="$SEABIOS_BUILD_ROOT/seabios-grub/vgabios.bin"
[[ -f "$vgabios" ]] || {
    printf 'error: GRUB framebuffer VGA BIOS is missing: %s\n' "$vgabios" >&2
    exit 1
}

require_tool()
{
    local name="$1"
    local value="$2"

    command -v "$value" >/dev/null 2>&1 || {
        printf 'error: %s tool was not found: %s\n' "$name" "$value" >&2
        return 1
    }
}

require_tool GRUB_I386_MKIMAGE "$GRUB_I386_MKIMAGE"
require_tool GRUB_X86_64_MKIMAGE "$GRUB_X86_64_MKIMAGE"
require_tool XORRISO "$XORRISO"
require_tool MFORMAT "$MFORMAT"
require_tool MMD "$MMD"
require_tool MCOPY "$MCOPY"
require_tool PYTHON "${PYTHON:-python3}"

homebrew_prefix="${HOMEBREW_PREFIX:-}"
if [[ -z "$homebrew_prefix" ]] && command -v brew >/dev/null 2>&1; then
    homebrew_prefix="$(brew --prefix 2>/dev/null || true)"
fi

find_grub_module_dir_under_prefix()
{
    local prefix="$1"
    local target_triple="$2"
    local format="$3"
    local dir

    [[ -n "$prefix" ]] || return 1

    for dir in \
        "$prefix/lib/$target_triple/grub/$format" \
        "$prefix/$target_triple/lib/grub/$format" \
        "$prefix/lib/grub/$format"; do
        if [[ -f "$dir/moddep.lst" ]]; then
            printf '%s\n' "$dir"
            return 0
        fi
    done

    return 1
}

resolve_grub_module_dir()
{
    local configured="$1"
    local configured_prefix="$2"
    local target_triple="$3"
    local format="$4"
    local formula="$5"
    local formula_prefix=
    local dir=

    if [[ -n "$configured" ]]; then
        [[ -f "$configured/moddep.lst" ]] || {
            printf 'error: GRUB %s module directory has no moddep.lst: %s\n' \
                "$format" "$configured" >&2
            return 1
        }
        printf '%s\n' "$configured"
        return 0
    fi

    if [[ -n "$configured_prefix" ]]; then
        dir="$(find_grub_module_dir_under_prefix \
            "$configured_prefix" "$target_triple" "$format" || true)"
        if [[ -n "$dir" ]]; then
            printf '%s\n' "$dir"
            return 0
        fi
        printf 'error: GRUB %s prefix has no matching module tree: %s\n' \
            "$format" "$configured_prefix" >&2
        return 1
    fi

    # Ask Homebrew for the formula's stable opt prefix first. This avoids the
    # versioned Cellar path compiled into a particular bottle and survives
    # formula upgrades without retaining an obsolete GRUB module directory.
    if command -v brew >/dev/null 2>&1; then
        formula_prefix="$(brew --prefix "$formula" 2>/dev/null || true)"
        if [[ -n "$formula_prefix" ]]; then
            dir="$(find_grub_module_dir_under_prefix \
                "$formula_prefix" "$target_triple" "$format" || true)"
            if [[ -n "$dir" ]]; then
                printf '%s\n' "$dir"
                return 0
            fi
        fi
    fi

    if [[ -n "$homebrew_prefix" ]]; then
        for formula_prefix in \
            "$homebrew_prefix/opt/$formula" \
            "$homebrew_prefix"; do
            dir="$(find_grub_module_dir_under_prefix \
                "$formula_prefix" "$target_triple" "$format" || true)"
            if [[ -n "$dir" ]]; then
                printf '%s\n' "$dir"
                return 0
            fi
        done
    fi

    return 0
}

i386_module_dir="$(resolve_grub_module_dir \
    "$GRUB_I386_MODULE_DIR" "$GRUB_I386_PREFIX" \
    i686-elf i386-efi i686-elf-grub)"
x86_64_module_dir="$(resolve_grub_module_dir \
    "$GRUB_X86_64_MODULE_DIR" "$GRUB_X86_64_PREFIX" \
    x86_64-elf x86_64-efi x86_64-elf-grub)"

if [[ -z "$i386_module_dir" &&
      "$(basename "$GRUB_I386_MKIMAGE")" == i686-elf-grub-mkimage ]]; then
    printf '%s\n' \
        'error: i686-elf-grub is a PC-platform GRUB build and has no i386-efi module tree.' \
        'Set GRUB_I386_MKIMAGE plus GRUB_I386_MODULE_DIR or GRUB_I386_PREFIX to an i386-efi build.' >&2
    exit 1
fi

if [[ -z "$x86_64_module_dir" &&
      "$(basename "$GRUB_X86_64_MKIMAGE")" == x86_64-elf-grub-mkimage ]]; then
    printf '%s\n' \
        'error: x86_64-elf-grub was selected but its x86_64-efi module tree could not be located.' \
        'Set GRUB_X86_64_MODULE_DIR or GRUB_X86_64_PREFIX to the active GRUB installation.' >&2
    exit 1
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/whp-seabios-iso.XXXXXX")"
trap 'rm -rf "$work"' EXIT

iso_root="$work/iso"
esp="$iso_root/EFI/efiboot.img"
efi_dir="$iso_root/EFI/BOOT"
grub_dir="$iso_root/boot/grub"
seabios_dir="$iso_root/boot/seabios"
early_cfg="$work/early.cfg"

mkdir -p "$efi_dir" "$grub_dir" "$seabios_dir" "$(dirname "$output")"
cp "$payload" "$seabios_dir/seabios-grub.elf"
cp "$vgabios" "$seabios_dir/seabios-grub-vgabios.bin"

cat > "$early_cfg" <<'EOF'
search --no-floppy --file --set=whp_root /boot/grub/grub.cfg
set root=$whp_root
configfile /boot/grub/grub.cfg
EOF

cat > "$grub_dir/grub.cfg" <<'EOF'
set default=0
set timeout=5

menuentry "SeaBIOS legacy environment" {
    # EFI GRUB already owns a working GOP framebuffer. Preserve that mode so
    # Multiboot reports its address, pitch, dimensions, bpp, and RGB masks.
    set gfxpayload=keep
    multiboot /boot/seabios/seabios-grub.elf
    module /boot/seabios/seabios-grub-vgabios.bin name=vgaroms/whp-grub-framebuffer.rom
    boot
}
EOF

modules=(
    part_gpt part_msdos fat iso9660
    search search_fs_file
    normal configfile echo
    multiboot multiboot2
    reboot halt
)

build_efi()
{
    local mkimage="$1"
    local format="$2"
    local target="$3"
    local module_dir="$4"
    local args=(-O "$format" -o "$target" -p /boot/grub -c "$early_cfg")

    if [[ -n "$module_dir" ]]; then
        args+=(-d "$module_dir")
    fi
    "$mkimage" "${args[@]}" "${modules[@]}"
}

build_efi "$GRUB_I386_MKIMAGE" i386-efi "$efi_dir/BOOTIA32.EFI" \
    "$i386_module_dir"
build_efi "$GRUB_X86_64_MKIMAGE" x86_64-efi "$efi_dir/BOOTX64.EFI" \
    "$x86_64_module_dir"

"${PYTHON:-python3}" - "$esp" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
with path.open('wb') as stream:
    stream.truncate(8 * 1024 * 1024)
PY

"$MFORMAT" -i "$esp" -v WHPSEABIOS ::
"$MMD" -i "$esp" ::/EFI
"$MMD" -i "$esp" ::/EFI/BOOT
"$MCOPY" -i "$esp" "$efi_dir/BOOTIA32.EFI" ::/EFI/BOOT/BOOTIA32.EFI
"$MCOPY" -i "$esp" "$efi_dir/BOOTX64.EFI" ::/EFI/BOOT/BOOTX64.EFI

# The FAT image is both the El Torito EFI boot image for optical media and a
# GPT EFI System Partition when the same ISO is written directly to USB media.
"$XORRISO" -as mkisofs \
    -R -J -V WHP_SEABIOS \
    -o "$output" \
    -e EFI/efiboot.img \
    -no-emul-boot \
    -efi-boot-part --efi-boot-image \
    "$iso_root"

printf 'Hybrid x86 UEFI SeaBIOS ISO: %s\n' "$output"
