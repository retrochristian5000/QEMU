Core99 NVRAM flash command engine
=================================

The Core99 command engine models two 8 KiB parameter banks at offsets
0 and 0x2000. It is intentionally separate from the legacy MacIO NVRAM
device, whose 8 KiB direct-write backing files and strided addressing
remain unchanged.

The engine implements byte programming (one-to-zero only), bank erase,
Sharp/Micron status and error handling, and AMD unlock, failure polling
and reset sequences. Commands are decoded separately from program data.
Operations complete synchronously. The caller owns persistence and must
save the changed byte or bank indicated by the return value.

This is a staged implementation, not a machine-visible flash device.
Before connecting it to Sawtooth, implement dual-bank CHRP checksums
and generation selection, migration state, backing-store compatibility,
firmware command-aware access, and the correct device-tree description.
Exact chip IDs, write-enable pins, timing, and optional command support
must be verified against the board and flash part. Whole-chip erase is
not supported by this parameter-bank model.

References:

* Linux PowerMac driver: arch/powerpc/platforms/powermac/nvram.c
* AMD Am29F080B data sheet, command definitions (protocol reference only)
* Micron MT28F008B3 data sheet, command definitions and status register
  (protocol reference only)

Neither reference part is asserted to be the Sawtooth's actual chip.
