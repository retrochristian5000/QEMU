AT&T 2Wire 2701HG-B: voltage domains and wiring evidence
===========================================================

Purpose and scope
-----------------

This ledger complements ``docs/devel/twowire-led-panel.rst`` and
``docs/devel/twowire-ares-identity.rst``. The
2701HG-B is not yet a bootable QEMU machine. This is a board-level
electrical evidence ledger, NOT a claim that the Ares SoC has known
GPIO/MMIO mappings or that Clang/LLVM emits working modem firmware.

Do not substitute data from a 2700HG-B, 2701HG-D, 3600HGV, 3800HGV,
Marvell 88E6060, or a generic Atheros reference PCB for measurements
on the AT&T 2701HG-B. The 2701HG-B is documented as FCC PGR2W2701.

Evidence ledger: rails and peripherals
--------------------------------------

.. list-table::
   :header-rows: 1
   :widths: 24 22 16 38

   * - Element
     - Voltage
     - Classification
     - Implementation significance
   * - External adapter
     - 5.1 V DC; 2 A nameplate
     - MODEL INVENTORY
     - Input domain, not a CPU/LED GPIO domain. The capacity is
       10.2 W (5.1 V times 2 A), not a measurement of device load.
   * - Samsung K4H561638J-LCCC DDR SDRAM (32 MiB)
     - VDD and VDDQ 2.5 V +/- 0.2 V (DDR266/333);
       2.6 V +/- 0.1 V (DDR400)
     - PART DATASHEET
     - Do not choose the 2.6 V DDR400 rail without independent
       evidence of board memory speed/grade operation.
   * - ST NAND128W3A28N6 NAND (16 MiB)
     - VDD 2.7 to 3.6 V for the 3 V 'W' device family
     - PART-FAMILY DATASHEET
     - Do not assign the 5.1 V input to NAND bus pins; recover
       VDD, I/O voltage and chip-enable/reset sequencing.
   * - Atheros AR2413A WLAN
     - 3.3 V and 1.8 V supply networks
     - REFERENCE SCHEMATIC
     - Different core/analogue and I/O power domains are plausible,
       but the exact modem-board net assignments remain UNKNOWN.
   * - 2Wire Ares SoC (TM32/TM3260-related)
     - Core and I/O rails UNKNOWN
     - UNKNOWN
     - No GPIO electrical thresholds, reset regulator, or pin
       assignment may be transferred from Philips/NXP PNX15xx/TM3260.
   * - Marvell 88E6061 Ethernet switch
     - Exact rail(s) UNKNOWN
     - UNKNOWN
     - A separate 88E6060 datasheet lists 3.3, 2.5 and 1.5 V rails
       and hardware-driven LED pins; do NOT transfer its pinout,
       sequencing or absolute maxima to the 88E6061 without evidence.
   * - ADSL analogue front end and RJ-11 line
     - UNKNOWN for this board
     - UNKNOWN
     - Telephone-line and analogue domains must not be conflated
       with the 5.1 V adapter and logic rail. Do not probe a live
       telephone/DSL pair while tracing board low-voltage nets.
   * - POWER/ETHERNET/WIRELESS/DSL/INTERNET LEDs
     - Physical drive rails, LED forward voltages, resistor values,
       polarity, and source pins UNKNOWN
     - UNKNOWN
     - Existing QEMU panel receives abstract 0/1 emission signals
       only. It is not a voltage source or regulator model.

Provenance and gaps
-------------------

MODEL INVENTORY: former WikiDevi listing for 2Wire 2701HG-B, including
its 5.1 V/2 A input, FCC identity, RAM, flash, AR2413A, and 88E6061:

* https://deviwiki.com/wiki/2Wire_2701HG-B

PART DATASHEET: Samsung K4H561638J DDR operating conditions:

* https://dtsheet.com/doc/345267/samsung-k4h560438j
* https://www.alldatasheet.com/html-pdf/347879/SAMSUNG/K4H561638J/903/3/K4H561638J.html

PART-FAMILY DATASHEET: ST NAND128W3A 3.0 V variant range:

* https://www.alldatasheet.com/datasheet-pdf/pdf/94116/STMICROELECTRONICS/NAND128W3A.html

REFERENCE SCHEMATIC: Atheros AR2413A MB51 power/ground reference
shows distinct 3.3 V and 1.8 V nets; *not* the modem PCB schematic:

* https://fcc.report/FCC-ID/MK8CPX-05-WLM54G/597012.pdf

MODEL PHOTOGRAPHS: original 2006 FCC internal photos, application
PGR2W2701, exhibit 711620. These show PCB structure and connectors,
but do not disclose enough readable net labels to reconstruct supply
rail topology, regulator outputs, or front-panel LED GPIO positions:

* https://fccid.io/PGR2W2701/Internal-Photos/int-photos-711620.pdf

COMPARATIVE-ONLY: 88E6060 (NOT 88E6061) documents 3.3/2.5/1.5 V
and switch-controlled LED signals. This is a hypothesis generator, not
an allowable 88E6061 pinout or rail assignment:

* https://www.insidegadgets.com/wp-content/uploads/2014/07/88E6060.pdf

The 2701HG-D community report about adapter center polarity and an
under-voltage event is NOT a 2701HG-B measurement. The 2701HG-B DC
barrel *polarity* is therefore not marked verified by this ledger.

Connection admissibility rules
------------------------------

1. Recover the exact *board revision*, origin pin, destination pin,
   voltage source and return before an electrical net is asserted.
   Record both the source device and the source document/measurement.
2. Model a proposed path as UNKNOWN until power-rail assignment and
   signal type agree: POWER, DIGITAL-OUTPUT, DIGITAL-INPUT,
   OPEN-DRAIN, ANALOGUE, or LOGICAL-STATUS are not interchangeable.
3. For digital paths across unlike I/O rails, determine VIH, VIL,
   VOH, VOL, tolerance, pulls and whether level translation exists.
   Do not infer CMOS tolerance merely from nominal supply voltage.
4. For physical LEDs, recover anode, cathode, polarity, series resistor,
   drive/sink capability and the responsible block (Ares GPIO, Ethernet
   switch, power supervisor, DSL front end, etc.). The emitted LED
   intensity is not a voltage value and its graphical rendering cannot
   repair an electrical mismatch.
5. Record power-good and reset sequencing only when hardware evidence
   establishes it. No magic 5.1 V threshold, power-on blink schedule,
   brownout timer, or regulator startup waveform is invented.
6. Keep device physics, firmware policy and frontend separated:
   verified firmware register writes -> board GPIO/control signal ->
   TYPE_LED -> logical emission input -> QEMU front-panel console.
   An Ethernet LED may turn out to be switch-driven rather than
   firmware-driven; preserve this as an open alternative.
7. Tests should prove invalid cross-domain connections are rejected
   once a board-level voltage/pin schema exists, and verify GPIO
   active-low/active-high reset separately from any firmware timer.
8. The compiler (LLVM) needs correct ISA, ABI, object layout, and
   eventually MMIO register headers. Supply voltages and electrical
   level shifting belong to QEMU's board/device model, not a
   fabricated new TriMedia compiler ABI.

Open datapoints / verification priorities
-----------------------------------------

* Inspect an identified 2701HG-B adapter label for DC polarity.
* Identify actual voltage regulators and their pins on the 2701HG-B
  PCB; use safe bench documentation or high-resolution PCB evidence.
* Trace Ares power/IO rail connections, and identify separate ground
  domains and board-level reset controls.
* Validate Marvell 88E6061 (not 88E6060) electrical specifications
  and determine whether Ethernet front-panel LED is switch-driven.
* Determine whether each LED is GPIO-driven, PHY-driven or powered
  by a dedicated control circuit; determine active polarity.
* Preserve the distinction between no measured value, inferred value,
  and an actual measured board voltage. Missing is not zero.
