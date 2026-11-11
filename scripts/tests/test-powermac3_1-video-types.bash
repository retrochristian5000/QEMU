#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
source_file="$repo_root/hw/ppc/powermac3_1.c"

if ! grep -Eq 'powermac3_1_vga_init\(PCIBus \*bus, VGAInterfaceType vga_type\)' "$source_file"; then
    echo "error: Sawtooth VGA helper must keep VGAInterfaceType" >&2
    exit 1
fi

if ! grep -Eq 'VGAInterfaceType requested_vga = .*vga_interface_type' "$source_file"; then
    echo "error: Sawtooth requested VGA must keep VGAInterfaceType" >&2
    exit 1
fi

if grep -Eq 'powermac3_1_vga_init\(PCIBus \*bus, int vga_type\)|int requested_vga = vga_interface_type' "$source_file"; then
    echo "error: Sawtooth VGA selector regressed to an untyped int" >&2
    exit 1
fi

if ! grep -Eq 'PCIHostState \*agp_host;' "$source_file"; then
    echo "error: Sawtooth AGP host must retain PCIHostState type" >&2
    exit 1
fi

if grep -Eq 'Object \*agp_host;' "$source_file"; then
    echo "error: Sawtooth AGP host regressed to generic Object type" >&2
    exit 1
fi

echo "PowerMac3,1 video type boundaries: verified"
