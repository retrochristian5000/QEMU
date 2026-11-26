# Experimental external IDE firmware

The normal isapc BIOS stays unchanged. The optional
seabios-128k-external-ide variant retains the 128 KiB capacity, option-ROM
discovery, core INT 13h services and floppy support, but omits the internal
ATA driver. QEMU's existing general option-ROM path publishes a supplied
image through fw_cfg genroms/. SeaBIOS already supports legacy BCV and
PnP BCV/BEV initialization and boot registration. No new private firmware ABI
is introduced.

## Build only

    make -C roms seabios-external-ide \
        SEABIOS_CROSS_PREFIX=/path/to/i386-none-elf-

The explicit target emits bios-128k-external-ide.bin rather than replacing
bios.bin. Set SEABIOS_OUTPUT_DIR and SEABIOS_BUILD_ROOT to separate
directories if desired.

## Experimental use

    qemu-system-i386 -machine isapc \
        -bios /path/to/bios-128k-external-ide.bin \
        -option-rom /path/to/ide-isa.rom

The source-built x86 SeaBIOS target now also builds and installs the
experimental ide-isa.rom (make -C roms ide-option-rom builds it separately).
It has a checksummed ISA option-ROM header and PnP BCV, probes the primary
master using ATA IDENTIFY, and connects drive 80h only when no existing
hard disk BIOS provider is registered. The first implementation exposes
read-only CHS reads, geometry and last status; it rejects writes and
unsupported calls. It requires an i386 or later processor, 512-byte logical
sectors, writable option-ROM shadow during BCV, and a primary master disk.
CHS capacity is limited to 1024 cylinders, 16 heads and 63 sectors per
track. There is no ATA slave/secondary-channel support, EDD, reset recovery,
DMA, ATAPI, or El Torito support yet. Do not use it for existing DOS/Windows
installations. The normal BIOS remains unchanged and no machine
automatically attaches this ROM. CI uses a disposable synthetic disk to
test the initial read-only path. A successful build alone is not evidence
of guest boot compatibility.

Measure raw core bytes, not the final fixed-size padded image. Separately
account for the expansion ROM and its conventional option-ROM allocation
below 1 MiB; moving bytes out of the core does not eliminate them from the
guest address space. No arbitrary reduction of the 128 KiB ROM capacity or
memory reservations is part of this experiment.
