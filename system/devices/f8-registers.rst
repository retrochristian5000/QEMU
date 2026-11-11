Fairchild F8 register model
===========================

Scope and provenance
--------------------

The register file implemented in ``target/f8/regs.[ch]`` follows the 1976
Fairchild *F8 Guide to Programming*, section 2.4.2/2.4.3 (CPU registers
and W flags) and section 2.5.2 (memory-support address counters):

https://bitsavers.computerhistory.org/components/fairchild/f8/67095664_F8_Guide_To_Programming_1976.pdf

Cross-reference with the independently written MAME F8 core:
https://github.com/mamedev/mame/blob/master/src/devices/cpu/f8/f8.cpp

The original **3850 CPU chip** contains the accumulator, status W, ISAR,
and scratchpad.  The **3851/3852/3853 memory-support chips** contain
PC0/PC1 and data-counter machinery; they are *architectural state for
the complete F8 system*, not physically registers inside a bare 3850.
The integrated **Mostek MK3870** combines CPU and memory-support
functions in one package.  DC1 availability and swapping depend on
the particular memory-support device; no blanket 3851 DC1 claim.

Implemented architectural storage
---------------------------------

================== ======= ==============================================
Register/alias     Width   Meaning
================== ======= ==============================================
A                  8       Accumulator
W                  5       I/O/Z/C/S = 0x10/08/04/02/01
ISAR               6       Indirect scratchpad address (3+3 bit octals)
Scratchpad         64x8    Internal scratch registers, addresses 0 to 63
J                  8       Scratchpad byte 9, status save/restore
H (HU:HL)          16      Scratchpad bytes 10:11, big-endian high:low
K (KU:KL)          16      Scratchpad bytes 12:13, high:low
Q (QU:QL)          16      Scratchpad bytes 14:15, high:low
PC0                16      Program counter (memory support)
PC1                16      Single return-address register, not RAM stack
DC0                16      Data counter 0 (memory support)
DC1                16      Alternate data counter (where implemented)
================== ======= ==============================================

``F8CoreRegisters`` stores just bare 3850 state.
``F8AddressRegisters`` stores the memory-support address counters.
``F8Registers`` composes both for a complete emulated machine without
confusing which original IC held each register.

Implemented helpers
-------------------

* W and ISAR values are masked to five and six bits respectively.
* ``LISU``/``LISL`` field helpers preserve the unaffected 3-bit octal.
* Direct scratchpad operand nibble 0..B reaches bytes 0..11; nibble
  C reads ISAR, D uses ISAR then increments the **low three bits only**,
  E uses ISAR then decrements those low bits.  F is rejected as an
  undefined scratch-register encoding.  Indirect modes can also access
  scratchpad bytes 0..15.
* H/K/Q are *aliases*, not extra register storage.
* Helpers support LR W,J / LR J,W and LR A,IS / LR IS,A data transfers.

No hardware power-up/reset contents are assumed.  The function
``f8_regs_init_for_test`` supplies deterministic zeroed state solely
for software tests.  A real 3850/MK3870 reset implementation must
implement documented behavior for each peripheral and register.

Tests and integration boundaries
--------------------------------

``tests/unit/test-f8-regs.c`` exercises register widths, flags, ISAR
block wrap, direct/indirect scratchpad operations, J/W and H/K/Q
aliases, invalid operand rejection and independent PC/DC storage.
Run ``meson test test-f8-regs`` in a configured full QEMU build.

The register module is linked only into its **unit test** for now.
There is **no** CPU execution loop, TCG target, 3870 ROM mapping,
board-level pins, interrupt/timer device, or firmware boot.  The
Zenith VP2000's actual controller markings and ROM remain a
separate evidence question from the validated Fairchild F8 ISA.
