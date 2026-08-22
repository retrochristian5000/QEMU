# Sierra Falcon/64 Display Device Design

## Goal

Add a staged emulation of the Sierra Semiconductor Falcon/64 SC15064 PCI VGA accelerator without pretending that undocumented Sierra acceleration registers are already implemented.

## Hardware boundary

The first device model represents the attested PCI identity and basic memory envelope of the SC15064:

- QEMU device name: `sierra-falcon64`
- PCI vendor ID: `0x1a08` (Sierra Semiconductor)
- PCI device ID: `0x0000` (SC15064)
- PCI class: VGA display controller
- Supported framebuffer sizes: 1, 2, or 4 MiB
- Default framebuffer size: 4 MiB

The surviving Sierra Falcon/64 product brief identifies the SC15064 as an integrated 64-bit GUI accelerator with PCI Local Bus support and hardware BitBLT, raster operations, line drawing, and pattern fill. Those acceleration blocks are not modeled in this first stage because a sufficiently complete register-level specification has not yet been recovered.

## Architecture

Implement `sierra-falcon64` as a QOM subtype of QEMU's existing PCI `VGA` device. This deliberately reuses the mature VGA-compatible core, framebuffer BAR, QEMU MMIO/VBE compatibility window, EDID support, migration state, and `vgabios-stdvga.bin` path instead of cloning that machinery.

The subtype overrides only the hardware identity and the SC15064-specific VRAM envelope. A realize wrapper validates that `vgamem_mb` is exactly 1, 2, or 4 before delegating to the inherited PCI VGA realize path.

This is a compatibility-stage implementation, not a claim that QEMU's Bochs/QEMU extension registers are native Sierra registers. The source must state that boundary explicitly.

## Power Macintosh use

Do not replace the PowerMac3,1/Sawtooth AGP default display. The Falcon/64 remains an explicitly requested PCI expansion display, for example with `-device sierra-falcon64` (and `-vga none` when it should be the only display).

Keeping the inherited QEMU PCI VGA BAR layout is intentional for the first stage: OpenBIOS and `qemu_vga.ndrv` already know how to initialize that compatibility ABI on PowerPC. This gives us a usable Sierra-identified PCI card while keeping future native SC15064 register work isolated.

## Build integration

Add a dedicated `SIERRA_FALCON64` display Kconfig symbol that depends on PCI and selects `VGA_PCI`. Build the implementation as `hw/display/sierra_falcon64.c`.

Add Sierra's PCI vendor/device constants to `include/hw/pci/pci_ids.h` in numeric vendor order.

## Verification

Add a PowerPC qtest that launches `mac99` with `-nodefaults -display none -device sierra-falcon64`, queries PCI state, and verifies the Sierra vendor/device identity. The test also confirms that 1, 2, and 4 MiB configurations can be instantiated.

The implementation is not considered verified until the repository build/CI provides fresh evidence after the commit.

## Evidence

- PCI ID Repository: vendor `1a08`, device `0000`, SC15064.
- Sierra Semiconductor Falcon/64 SC15064 product brief (archived by Datasheet Archive): PCI Local Bus support; hardware BitBLT, raster operations, line drawing, and pattern fill.
