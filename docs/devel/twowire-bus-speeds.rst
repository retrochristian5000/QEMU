AT&T 2Wire 2701HG-B bus-speed evidence
======================================

Scope and primary finding
-------------------------

The 2701HG-B has a 2Wire Ares SoC related to TM32/TM3260, but
the actual motherboard CPU, RAM, NAND, MMIO, PCI and MII clock tree
has not been recovered. Do NOT substitute a Philips/NXP PNX15xx
clock table for 2Wire's custom Ares SoC. All actual_hz fields
are null in ``docs/devel/twowire-bus-speeds.json``: null is UNKNOWN,
not an assumption of 0 Hz. See the Ares-identity and voltage ledgers.

Recovered speeds and bus types
------------------------------

* PNX15xx reference TM3260 CPU: up to 300 MHz by speed grade.
  PNX15xx DDR: up to 200 MHz. Its *distinct* DCS/MMIO bus has
  54/102/108/115/123/133/144/157 MHz choices. These values
  are comparisons only, not readings from an Ares motherboard.
* Samsung K4H561638J-LCCC is a 256-Mbit x16 DDR400 (CC)
  chip rated to 200 MHz. Double-data-rate transfer gives
  400 million transfers/s, times two bytes => an ideal
  SINGLE-CHIP maximum of 800 MB/s. Controller overhead,
  refresh, row activity, and contention reduce actual rate.
  The part rating alone cannot establish the motherboard clock.
* ST NAND128W3A is x8 asynchronous NAND with 512+16-byte
  pages. 50 ns **minimum sequential access cycle** implies an
  ideal 20 MB/s interface ceiling; it is not a 20 MHz
  synchronous chip clock. Separately, page read may take
  12 us (maximum); page program averages about 200 us,
  and block erase about 2 ms typically. Do not apply
  these different max/typ bounds as identical wait states.
* Marvell's manufacturer selector specifically documents
  88E6061/B as a six-port Fast Ethernet switch, five PHYs,
  with one or two possible MII interfaces. The related 88E6060
  documentation has 2.5 MHz MII for 10 Mbps, and 25 MHz
  MII for 100 Mbps (four bits/clock). These are reference
  interface values, NOT a 2701HG-B strap or pinout.
* The AR2413A is an 802.11g chip with up to 54 Mb/s PHY
  signaling; PCI-capable host interfaces exist, but its
  2701HG-B host clock, DMA, and radio throughput are unknown.
* DSL rate and Ares-to-DSL interface clocks remain unknown.

Observed QEMU implementation blockers
-------------------------------------

1. ``target/trimedia/translate.c`` implements
   ``trimedia_decode_packet()`` as an unconditional false
   return. Actual firmware cannot execute until packet decoding
   is implemented; clock modeling alone does not fix that.
2. ``target/trimedia/cpu.h`` stores ``cccount`` and four
   timer-state structures. Inspected CPU/translator sources do
   not implement a clock source ticking those state variables.
   Do not infer CPU cycles from host CPU speed or wall clock.
3. The general TriMedia CPU header contains PNX15xx timer/VIC
   identifiers. A PNX-specific peripheral enumeration must not
   silently become an Ares interrupt or MMIO assignment.
4. There is no evidence-based 2701HG-B machine, clock-divider
   implementation, DDR controller, NAND controller, or
   verified Ares-to-Marvell/AR2413 connection yet.
5. No NAND R/B busy timing, PHY negotiation/clock crossing,
   DMA contention, CPU/peripheral domain ratios, or power-on
   oscillator sequencing can yet be verified from firmware.

Priority for implementation
---------------------------

Recover authentic Ares firmware boot logs and PLL/divider writes;
identify motherboard revision and clock sources; implement TriMedia
packet decoding; then realize *separate QEMU virtual Clock domains*
for individually verified CPU, memory and peripheral blocks.
NAND busy/program latency must be separate from its byte transfer
cycle. Test via QTests and guest-observed timers, not wall-clock
host performance. LLVM's TriMedia target names are unrelated to
electrical bus timing.

Provenance (component or comparison only)
-----------------------------------------

* NXP PNX15xx/952x, Chapter 5 clock table:
  https://www.nxp.com/docs/en/data-sheet/PNX15XX_PNX952X_SER_N.pdf
* Samsung K4H561638J-LCCC DDR datasheet:
  https://datasheet.ciiva.com/26786/k4h561638j-lccc-26786739.pdf
* ST NAND128W3A product table:
  https://www.alldatasheet.com/html-pdf/94116/STMICROELECTRONICS/NAND128W3A/13027/8/NAND128W3A.html
* Marvell 2016 88E6061/B selector (device-specific):
  https://pf05.ickimg.com/datasheet/7a/4b/bcd9/7a/121618cacf2e3e091a08745f5cbc1b59.pdf
* Marvell **88E6060** MII (comparison only):
  https://www.insidegadgets.com/wp-content/uploads/2014/07/88E6060.pdf
* AR2413A product brief:
  https://deviwiki.com/files/Atheros/specsheets/AR5005G_%28AR2413%29.pdf

Validation::

   python3 scripts/tests/test-twowire-bus-speeds.py

That checks source scope and arithmetic, not real hardware or
QEMU timing behavior.
