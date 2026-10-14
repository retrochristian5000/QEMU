Mostek MK3870 / Fairchild F8 ISA in the RCA SFT100 and Zenith VP2000
=======================================================================

Status: ISA FAMILY VERIFIED; QEMU CPU BACKEND NOT IMPLEMENTED
-------------------------------------------------------------

**Instruction-set architecture (ISA): Fairchild F8**, as implemented by the
Mostek **MK3870** single-chip microcomputer.  This is an embedded 8-bit
controller, **not** the IBM PC *ISA expansion bus*.

Evidence ledger
---------------

1. RCA SFT100 original Service Data, PW500 System Control board, lists
   **U502** as "Microprocessor (computer)", drawing **1421729-7**,
   stock number **149015** (as printed/indexed on the service-manual page).
   U503 is the separate DAXI buffer, drawing **1421751-1**.
   https://www.manualslib.com/manual/3552449/Rca-Selectavision-Videodisc-Sft-100.html?page=39

2. CED Magic's model and IC cross-reference identifies RCA drawing
   **1421729-007** as **Mostek 3870**, 40-pin DIP.  It gives replacement
   stock number **149249** instead of **149015**.  Preserve both stock
   numbers; their relationship is **unresolved**, not an ISA ambiguity.
   https://cedmagic.com/tech-info/rca-to-nte.html
   https://cedmagic.com/tech-info/rca-ic-numbers.html

3. RCA Engineer, Nov./Dec. 1981, V. W. Fisher and C. M. Dieterich,
   "The VideoDisc player's digital control system": directly identifies
   the SFT100 microcomputer as a **3870**, with **2 KB on-chip ROM**,
   **64-byte scratchpad RAM**, **32 I/O pins** and an **8-bit timer**.
   The article reports over 2,000 bytes of final object code and a
   program listing of approximately 4,200 lines.  It describes the
   five controller modes LOAD, SPIN UP, PAUSE, PLAY, RAPID ACCESS, and
   DAXI synchronization per video field.
   https://www.worldradiohistory.com/ARCHIVE-RCA/RCA-Engineer/1981-11-12.pdf
   Source is indexed, but verify against a scanned original before
   transcribing exact firmware timings into executable tests.

4. CED Magic identifies the Zenith VP2000 as an electrical and
   mechanical RCA SFT100 clone; comparison of **Zenith actual PW500
   board and chip markings** is still required before recording its
   identical mask-programmed ROM as confirmed.
   https://cedatum.com/newbie/
   https://groups.google.com/g/alt.video.laserdisc/c/bNTFVGVW34k

5. Contemporary Mostek chip literature documents F8 ISA compatibility.
   The MK3870 family offers different ROM/RAM variants; the SFT100's
   particular 2 KB configuration comes from the 1981 RCA paper, **not**
   a presumption that every MK3870 was 2 KB.
   https://manuals.plus/m/20fcf4b89aa14abe3135641e8a20c05a5cb2259fee88a0ebe64901a8a1a3c96a
   https://tobiasvl.github.io/optable/f8/

ISA / emulation requirements
----------------------------

* F8 8-bit accumulator **A** and status word **W** (sign, carry,
  zero, overflow, interrupt control), **6-bit ISAR**, and **64-byte
  scratchpad**; scratchpad registers include H, K, Q paired pointers.
* Program counter **PC0**, return/program stack register **PC1**, data
  counter **DC0**, and alternate data counter **DC1**.  Do **not**
  replace these with x86-style PC/SP semantics.
* Decode the complete documented F8 opcode map, including the unusual
  accumulator/scratchpad operations, ISAR addressing, branching and
  ROMC/PC/DC transfer semantics.  Illegal/unused opcode behavior must
  be verified before selecting deterministic handling.
* MK3870 integrated mask-ROM / scratchpad layout, actual timer and
  interrupt semantics, four 8-bit external ports 0/1/4/5, internal
  control/timer ports 6/7, and processor clock and reset wiring.
* Map U502 pins to U503 DAXI buffer, LED display, optical/stylus servo
  controls, PAUSE/SEARCH buttons, lift/kicker and other PW500 hardware
  using schematics.  No addresses, IRQ lines or oscillator frequency
  may be invented.
* A **ROM image from the SFT100/VP2000 chip** (or independently
  reconstructed, legally usable behavior) is required to execute
  authentic control firmware.  The F8 ISA alone does not reveal
  the ROM's actual program bytes.
* Keep the existing synthetic ``WHP-CED1`` transport descriptor as a
  separate test fixture, not firmware, and not an authentic groove dump.

Available independent test references
-------------------------------------

MAME implements an F8 core with a disassembler, including special
ROMC handling and 64-byte scratchpad state; use it as a behavioral
**cross-check**, not a drop-in QEMU TCG device or evidence of ROM dumps:
https://github.com/mamedev/mame/blob/master/src/devices/cpu/f8/f8.cpp

The F8 family has differences between its multi-chip 3850/3851 system
and the integrated 3870; verify microcontroller timer and on-chip
memory details separately from generic F3850 instruction execution.

The QEMU fork's ``master`` target inventory on 2026-10-14 contains
**no** ``target/f8``.  The existing ``hw/block/ced-sft100*.c`` uses
high-level mechanics and virtual-field timing, **not** firmware execution.

Next implementation gates
-------------------------

1. Build instruction/mnemonic/operand/cycle tables from Mostek primary
   data, with disassembler and known-opcode tests **before** CPU wiring.
2. Implement QEMU ``target/f8`` instruction execution + reset, scratchpad,
   flags, PC/DC/ISAR, and masked ROM loads.  Reuse TCG patterns but
   never alias F8 to x86, Z80 or COSMAC.
3. Implement MK3870 timer, external interrupt pins and GPIO behavior
   independent of PC-style I/O buses.
4. Recover and verify SFT100/Zenith firmware mask-ROM variant and
   pin mappings.  Run firmware against hardware traces and independent
   reference behavior, while preserving uncertainty for unidentified
   ROM contents.
5. Integrate real firmware control with the CED transport using a
   **single owner** of state transitions, then replace any duplicated
   high-level shortcuts only after tests prove equivalence.
6. Add migration state serialization, console/media frontend, and
   analog video/audio decoder after CPU and timing semantics are stable.

Important chronology/timing caution: the 1981 RCA Engineer paper
describes a six-second SPIN UP routine after LOAD, whereas the existing
``ced-sft100-control`` high-level model uses an approximately eight-second
picture-appearance delay. These are different observables; neither
should be silently overwritten until start-up and set-down events are
separated in the hardware model.
