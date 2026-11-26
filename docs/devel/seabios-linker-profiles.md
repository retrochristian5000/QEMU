# SeaBIOS variant-specific linker layouts

Each BIOS variant generates its own coordinated 16-bit, 32-bit segmented,
and 32-bit flat linker scripts in its existing build directory. The scripts
identify their profile in a comment. QEMU supplies the variant explicitly
rather than treating every 128 KiB BIOS as isapc.

- seabios-128k: ISA PC, 128 KiB.
- seabios-256k: conventional PC, 256 KiB.
- seabios-microvm: microvm, 128 KiB.
- seabios-grub: coreboot Multiboot payload.
- Standalone and VGA builds retain their automatic profile.

The default placement is unchanged. The optional compact layout sorts
movable 32-bit initialization text by descending input alignment, only
accepting the order when the calculated span shrinks. Fixed entries,
runtime sections, data ordering and required alignments are unchanged.

To compare layouts in a separate firmware build directory:

```sh
WHP_ROM_SIZE_REPORT=1 make -C roms build-seabios-config-seabios-128k \
  SEABIOS_BUILD_ROOT=/path/to/comparison SEABIOS_LAYOUT_PACK=1
```

Set SEABIOS_LAYOUT_PACK=0 for the baseline. Use the same compiler,
configuration and build root; changing the policy regenerates linker
scripts without deliberately invalidating the compiled objects.
The internal-gap inventory includes mandatory reservations as well as
alignment gaps, so it is not a claim that every reported byte can be saved.
