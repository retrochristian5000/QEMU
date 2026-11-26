# Experimental external IDE firmware

The normal isapc BIOS explicitly retains CONFIG_ATA=y and remains the boot
default. The separately named seabios-128k-external-ide variant retains the 128 KiB capacity, option-ROM
discovery, core INT 13h services and floppy support, but omits the internal
ATA driver. QEMU's existing general option-ROM path publishes a supplied
image through fw_cfg genroms/. SeaBIOS already supports legacy BCV and
PnP BCV/BEV initialization and boot registration. No new private firmware ABI
is introduced.

## Build only

    make -C roms seabios-external-ide \
        SEABIOS_CROSS_PREFIX=/path/to/i386-none-elf-

Only the explicit seabios-external-ide target builds the second 128 KiB
core. The ordinary x86 build produces one 128 KiB BIOS and ide-isa.rom,
not both core variants. The experimental image does not replace bios.bin. CI checks the generated Kconfig and retained linker-script input
sections for ATA implementation helpers. Set SEABIOS_OUTPUT_DIR and SEABIOS_BUILD_ROOT to separate
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
read-only CHS and EDD packet reads, basic EDD drive parameters, geometry
and last status; it rejects writes and unsupported calls. The EDD subset
is not advertised by AH=41h until all mandatory services are available. It requires an i386 or later processor, 512-byte logical
sectors, writable option-ROM shadow during BCV, and a primary master disk.
CHS capacity is limited to 1024 cylinders, 16 heads and 63 sectors per
track. There is no ATA slave/secondary-channel support, complete EDD subset, reset recovery,
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

## Linker layout

The IDE ROM uses its own ide-rom.ld script, with an ELF32/i386 load segment
and both virtual and physical addresses at zero. ELF metadata remains outside
the loadable ROM section. The raw image contains only .text; linker assertions
check the entry offset, sector granularity, first-stage size limit and unexpected
code/data sections. GNU ld and LLD are tested independently. The script is a
link dependency, so layout edits do not reuse an outdated linked image.

The EDD 1.1 reference is T10 95-153r0, sections 3.1.1–3.2.8:
https://www.t10.org/ftp/t10/document.95/95-153r0.pdf
