#!/usr/bin/env bash
set -euo pipefail

config_file="$1"
shift
[[ -f "$config_file" ]] || { echo "error: SeaBIOS config is missing: $config_file" >&2; exit 1; }
# shellcheck disable=SC1090
source "$config_file"

: "${SEABIOS_DIR:?missing SEABIOS_DIR}"
: "${SEABIOS_CROSS_COMPILE:?missing SEABIOS_CROSS_COMPILE}"
: "${MAKE_CMD:?missing MAKE_CMD}"

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
output_dir="$(dirname -- "$1")"
mkdir -p "$output_dir"

"$MAKE_CMD" -C "$SOURCE_DIR/roms" \
    SEABIOS_CROSS_PREFIX="$SEABIOS_CROSS_COMPILE" \
    SEABIOS_OUTPUT_DIR="$output_dir" \
    CPP="${SEABIOS_CROSS_COMPILE}cpp" \
    bios

expected=(bios.bin bios-256k.bin bios-microvm.bin)
for name in "${expected[@]}"; do
    [[ -f "$output_dir/$name" ]] || {
        printf 'error: SeaBIOS did not produce %s\n' "$output_dir/$name" >&2
        exit 1
    }
done
