#!/usr/bin/env bash
set -euo pipefail

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
fi

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$(dirname -- "$1")"
case "$output_dir" in
    /*) ;;
    *) output_dir="$PWD/$output_dir" ;;
esac
mkdir -p "$output_dir"

if [[ "$mode" == grub ]]; then
    "$MAKE_CMD" -C "$SOURCE_DIR/roms" \
        SEABIOS_CROSS_PREFIX="$SEABIOS_CROSS_COMPILE" \
        SEABIOS_BUILD_ROOT="$SEABIOS_BUILD_ROOT" \
        SEABIOS_OUTPUT_DIR="$output_dir" \
        CPP="${SEABIOS_CROSS_COMPILE}cpp" \
        seabios-grub

    # SeaBIOS/roms still emits the historical lowercase filename. Keep that
    # upstream-facing convention at the boundary, then publish the WHP-owned
    # linked executable using the internal .ELF assignment.
    legacy_elf="$output_dir/seabios-grub.elf"
    canonical_elf="$output_dir/seabios-grub.ELF"
    if [[ -f "$legacy_elf" ]]; then
        mv -f "$legacy_elf" "$canonical_elf"
    fi
    expected=(seabios-grub.ELF)
else
    "$MAKE_CMD" -C "$SOURCE_DIR/roms" \
        SEABIOS_CROSS_PREFIX="$SEABIOS_CROSS_COMPILE" \
        SEABIOS_BUILD_ROOT="$SEABIOS_BUILD_ROOT" \
        SEABIOS_OUTPUT_DIR="$output_dir" \
        CPP="${SEABIOS_CROSS_COMPILE}cpp" \
        bios
    expected=(bios.bin bios-256k.bin bios-microvm.bin)
fi

for name in "${expected[@]}"; do
    [[ -f "$output_dir/$name" ]] || {
        printf 'error: SeaBIOS did not produce %s\n' "$output_dir/$name" >&2
        exit 1
    }
done
