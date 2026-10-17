AT&T 2Wire 2701HG-B Ares ASIC identity ledger
=============================================

Evidence recovery
-----------------

The 2701HG-B is catalogued as using a 2Wire-branded **Ares**
processor/ASIC. It has 16 MiB ST NAND128W3A28N6, 32 MiB
Samsung K4H561638J-LCCC DDR, an Atheros AR2413A WLAN chip,
and a Marvell 88E6061 switch. These are third-party inventory
claims, not measurements made in this project.
Source: https://deviwiki.com/wiki/2Wire_2701HG-B

Independent source triangulation:

* A former 2Wire engineer lists "Ares ASIC - TM32" and
  distinguishes Perseus/Denali/Octopus ASIC designs.
  This is a professional account, not a register-level datasheet.
  https://www.linkedin.com/in/roycehays
* An IHS January 2007 teardown calls the core of the DIFFERENT
  3800HGV-B a "2Wire Branded ASIC - Ares" and separately describes
  its TriMedia/NXP processor component. Corroborates the family,
  not identity of the 2701HG-B silicon or peripherals.
  https://electronics360.globalspec.com/article/3694/2wire-homeportal-3800hgv-b-vdsl-residential-gateway-teardown
* SourceForge's 2wiglet project provides an original-era JTAG
  tool for TriMedia-based 2Wire routers (first posted 2011).
  The binary/source tarball has NOT been independently audited.
  https://sourceforge.net/projects/jtag2w/

Recorded JTAG family
--------------------

An archived UrJTAG transcription reports a one-device chain,
IR length 5 and the following identity records:

.. list-table::
   :header-rows: 1

   * - SoC label
     - JTAG IDCODE
     - Reported part
   * - Medusa
     - 0x1269B4C1
     - TM3260 / 0x269B
   * - Perseus
     - 0x2269B4C1
     - TM3260 / 0x269B
   * - **Ares**
     - **0x3269B4C1**
     - **TM3260 / 0x269B**
   * - Denali
     - 0x126AC4C1
     - 0x26AC; archived bcm6091 label

Source: https://deviwiki.com/wiki/2Wire

The *standard* IDCODE-style decomposition of 0x3269B4C1:
top nibble [31:28] = 0x3; part [27:12] = 0x269B;
manufacturer field [11:1] = 0x260; bit 0 = 1.
The transcription prints manufacturer "2Wire (0x4C1)";
0x4C1 represents the low **12 raw bits**, not the standard
11-bit field. Do not conflate these values or silently
certify a manufacturer-code assignment. Nor is this IDCODE
yet confirmed on an actual AT&T 2701HG-B board in this work.

Provenance conflicts
--------------------

* The 2Wire engineer's career record associates some 3600/3800
  platforms with Perseus while the IHS 3800 teardown calls the
  processor Ares. Archived community discussion also questions
  SoC identifications in 3600/3800 photos. Different PCB
  revisions or wrong labels are possible; do NOT overwrite
  either record or force that disagreement onto the 2701HG-B.
  https://deviwiki.com/wiki/Talk:2Wire_3600HGV
* A 2701HG-G report paraphrased in DeviWiki says "Ares (Medusa)",
  but the archived IDCODE table differentiates them. Preserve
  the conflict rather than treating Medusa as a synonym.
* The NXP PNX15xx/952x manual documents a TM3260-equipped
  processor/system: 32-bit VLIW, 128 registers, dual endian.
  A common CPU family does not prove 2Wire adopted NXP's exact
  boot straps, GPIO addresses, reset system or voltage rails.
  https://www.nxp.com/docs/en/data-sheet/PNX15XX_PNX952X_SER_N.pdf
* Exact package marking, mask revision, 2701 board power
  networks, CPU operating frequency, JTAG pins, memory map,
  firmware endian setting, boot vectors and LED drive pins
  are all still **UNKNOWN**.
  FCC 2006 filing: https://fccid.io/PGR2W2701

Implications for QEMU / LLVM
----------------------------

* QEMU already has a partial ``target/trimedia`` processor
  and ``TYPE_TM3260_CPU``; it does not yet implement a
  verified 2701HG-B board or 2Wire Ares peripheral SoC.
* Ares is a **SoC identity around a TM32-compatible core**,
  not an independent ISA. No unsupported CPU emulation target
  should be invented from a marketing/codenamed label.
* Do not wire the logical front-panel QEMU LEDs directly
  to fake SoC GPIO/MMIO values. Recover the controlling device
  and board routing first (which may include Ethernet switch).
* Do not transfer PNX15xx MMIO/boot/reset tables to Ares
  or invent Ares voltage rails. See the companion voltage
  ledger. LLVM's trimedia and trimediaeb triples only identify
  ELF32 architecture/endian classes, not executable firmware.

Next admission conditions
-------------------------

1. Exact photographed AT&T 2701HG-B PCB and Ares chip marking.
2. Real, attributed device-specific JTAG scan compared to 0x3269B4C1.
3. Verified firmware format, bootloader and startup endianness.
4. Recovered memory controller, reset and switch/LED signal routes.
5. Authentic TM3260 instruction encoding cross-tested with QEMU.
