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
        -option-rom /path/to/compatible-ide.rom

A working compatible IDE expansion ROM is **not** provided by this change.
The ROM must implement the appropriate INT 13h services, initialize the
actual ISA IDE controller and cooperate with SeaBIOS drive enumeration and
boot ordering. Do not assume ATAPI, El Torito, EDD, reset or DOS/Windows boot
compatibility. Booting from IDE requires independent verification; the
normal BIOS is still recommended for existing guests.

Measure raw core bytes, not the final fixed-size padded image. Separately
account for the expansion ROM and its conventional option-ROM allocation
below 1 MiB; moving bytes out of the core does not eliminate them from the
guest address space. No arbitrary reduction of the 128 KiB ROM capacity or
memory reservations is part of this experiment.
