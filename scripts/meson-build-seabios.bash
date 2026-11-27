#!/usr/bin/env bash
set -euo pipefail

if (($# < 2)); then
    printf 'usage: %s CONFIG_FILE [--grub | --vgabios | --ct1741 SDCC MAKEBIN] OUTPUT...\n' "$0" >&2
    exit 2
fi
config_file="$1"
shift
[[ -f "$config_file" ]] || { echo "error: SeaBIOS config is missing: $config_file" >&2; exit 1; }
# shellcheck disable=SC1090
source "$config_file"

: "${SEABIOS_DIR:?missing SEABIOS_DIR}"
: "${SEABIOS_BUILD_ROOT:?missing SEABIOS_BUILD_ROOT}"
: "${SEABIOS_CROSS_COMPILE:?missing SEABIOS_CROSS_COMPILE}"
: "${MAKE_CMD:?missing MAKE_CMD}"

mode=bios
if [[ "${1:-}" == --grub ]]; then
    mode=grub
    shift
elif [[ "${1:-}" == --vgabios ]]; then
    mode=vgabios
    shift
elif [[ "${1:-}" == --ct1741 ]]; then
    mode=ct1741
    shift
    if (($# != 3)); then
        printf 'error: CT1741 build requires SDCC, makebin and output path\n' >&2
        exit 2
    fi
    sdcc="$1"
    makebin="$2"
    shift 2
fi

# This is a fresh Make invocation from Meson, not a recursive make.
# Do not inherit host compiler overrides or a stale parent jobserver.
unset MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEFILES MAKEOVERRIDES MAKELEVEL
unset CC CXX CPP AS LD AR NM OBJCOPY OBJDUMP STRIP
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS HOSTCFLAGS HOSTCPPFLAGS HOSTLDFLAGS
unset CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH LIBRARY_PATH COMPILER_PATH GCC_EXEC_PREFIX
unset BASH_ENV ENV

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SEABIOS_DIR="$(cd -- "$SEABIOS_DIR" && pwd -P)"
[[ -f "$SEABIOS_DIR/Makefile" ]] || {
    printf 'error: SeaBIOS source Makefile is missing: %s\n' "$SEABIOS_DIR" >&2
    exit 1
}
if [[ "$mode" == grub ]]; then
    expected=(seabios-grub.ELF)
elif [[ "$mode" == vgabios ]]; then
    expected=(
        vgabios.bin vgabios-cirrus.bin vgabios-stdvga.bin
        vgabios-vmware.bin vgabios-qxl.bin vgabios-virtio.bin
        vgabios-ramfb.bin vgabios-bochs-display.bin vgabios-ati.bin
    )
elif [[ "$mode" == ct1741 ]]; then
    expected=(seabios-ct1741.bin)
else
    expected=(bios.bin bios-256k.bin bios-microvm.bin ide-isa.rom)
fi
if (($# != ${#expected[@]})); then
    printf 'error: incorrect number of SeaBIOS %s output paths\n' "$mode" >&2
    exit 2
fi
output_dir="$(dirname -- "$1")"
case "$output_dir" in
    /*) ;;
    *) output_dir="$PWD/$output_dir" ;;
esac
for name in "${expected[@]}"; do
    if [[ "$(basename -- "$1")" != "$name" ]]; then
        printf 'error: unexpected SeaBIOS output name: %s (expected %s)\n' "$1" "$name" >&2
        exit 2
    fi
    actual_dir="$(dirname -- "$1")"
    [[ "$actual_dir" == /* ]] || actual_dir="$PWD/$actual_dir"
    if [[ "$actual_dir" != "$output_dir" ]]; then
        printf 'error: SeaBIOS outputs must share one directory\n' >&2
        exit 2
    fi
    shift
done
mkdir -p "$output_dir"

if [[ "$mode" == ct1741 ]]; then
    dsp_source="$SEABIOS_DIR/firmware/ct1741"
    [[ -f "$dsp_source/Makefile" ]] || {
        printf 'error: CT1741 firmware source is missing from SeaBIOS: %s\n' "$dsp_source" >&2
        exit 1
    }
    # Use a fresh private output directory. MCU objects cannot leak across
    # toolchains or into the x86 firmware build or provider checkout.
    work="$(mktemp -d "$output_dir/.ct1741.XXXXXX")"
    trap 'rm -rf -- "$work"' EXIT
    "$MAKE_CMD" -C "$dsp_source" "BUILD_DIR=$work" \
        "SDCC=$sdcc" "MAKEBIN=$makebin" all
    [[ "$(wc -c < "$work/ct1741.bin")" -eq 8192 ]] || {
        printf 'error: SeaBIOS CT1741 firmware must be exactly 8192 bytes\n' >&2
        exit 1
    }
    chmod 0644 "$work/ct1741.bin"
    if ! cmp -s "$work/ct1741.bin" "$output_dir/seabios-ct1741.bin"; then
        mv -f "$work/ct1741.bin" "$output_dir/seabios-ct1741.bin"
    fi
    exit 0
fi

make_args=(
    -C "$SOURCE_DIR/roms"
    "SEABIOS_SOURCE_DIR=$SEABIOS_DIR"
    "SEABIOS_CROSS_PREFIX=$SEABIOS_CROSS_COMPILE"
    "SEABIOS_BUILD_ROOT=$SEABIOS_BUILD_ROOT"
    "SEABIOS_OUTPUT_DIR=$output_dir"
    "SEABIOS_HOSTCC=${SEABIOS_HOSTCC:-cc}"
)
if [[ "$mode" == grub ]]; then
    "$MAKE_CMD" "${make_args[@]}" seabios-grub

    # SeaBIOS/roms still emits the historical lowercase filename. Keep that
    # upstream-facing convention at the boundary, then publish the WHP-owned
    # linked executable using the internal .ELF assignment.
    legacy_elf="$output_dir/seabios-grub.elf"
    canonical_elf="$output_dir/seabios-grub.ELF"
    if [[ -f "$legacy_elf" ]]; then
        mv -f "$legacy_elf" "$canonical_elf"
    fi
elif [[ "$mode" == vgabios ]]; then
    "$MAKE_CMD" "${make_args[@]}" vgabios
else
    "$MAKE_CMD" "${make_args[@]}" bios
fi

for name in "${expected[@]}"; do
    [[ -f "$output_dir/$name" ]] || {
        printf 'error: SeaBIOS did not produce %s\n' "$output_dir/$name" >&2
        exit 1
    }
done
