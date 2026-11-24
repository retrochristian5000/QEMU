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

Bank inspection
---------------

The read-only bank helper validates the Apple signature, CHRP header
checksum, and Adler checksum over offsets 0x14 through 0x1fff.
Multi-byte fields are decoded as big-endian regardless of host ISA.
It recognizes the historical Linux checksum variant separately because
the 32-bit high accumulator can wrap for dense payloads.

Selection compares valid banks by unsigned generation, chooses bank 0
on ties, and returns -1 when neither validates. Generation wraparound
policy and the exact Apple checksum algorithm require verification
against the historical Apple driver or authentic images. This helper
does not validate every CHRP partition, rewrite a bank, or attach a
device. The live legacy NVRAM ABI and image format remain unchanged.

Sources:

* Apple XNU IONVRAM.cpp (apple_nvram_header):
  https://github.com/apple/darwin-xnu/blob/main/iokit/Kernel/IONVRAM.cpp
* Linux PowerMac nvram.c:
  https://github.com/torvalds/linux/blob/master/arch/powerpc/platforms/powermac/nvram.c
* AppleCore99NVRAM 1.1 archive located but contents not retrieved:
  https://sourceforge.net/projects/darwinsource/files/AppleCore99NVRAM/1.1/
