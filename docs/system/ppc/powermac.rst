PowerMac family boards (``g3beige``, ``mac99``, ``powermac3_1``)
==================================================================

Use the executable ``qemu-system-ppc`` to simulate a complete PowerMac
PowerPC system.

QEMU exposes several PowerMac machine types with different goals:

- ``g3beige`` models a Heathrow-based OldWorld Power Mac G3.
- ``mac99`` is the generic Core99/NewWorld compatibility machine.  It is useful
  for guests that expect NewWorld Macintosh hardware, but it is not intended to
  describe one exact retail Macintosh configuration.
- ``powermac3_1`` is the historical profile for the 1999 Power Mac G4 AGP
  (Sawtooth).  It specializes ``mac99`` with a narrower CPU, I/O, PCI and AGP
  topology.

Choosing a machine
------------------

Use ``g3beige`` for OldWorld Power Mac software and ``mac99`` when broad
Core99 compatibility is more important than reproducing one particular logic
board.  Use ``powermac3_1`` when the guest, firmware, or hardware investigation
benefits from a machine shaped specifically like the PowerMac3,1 Sawtooth.

The historical profiles are intended to make hardware differences visible
rather than silently flattening several generations of Macintosh hardware into
one generic machine.

Emulation status terminology
----------------------------

The hardware tables below use the following terms.  They describe the current
QEMU model, not a promise of cycle-accurate hardware timing.

``Modeled``
  QEMU has a dedicated model for the component or function and the machine
  connects it in the intended topology.

``Partial``
  The component is present, but some registers, sub-devices, timing, power
  behavior, DMA behavior, or other hardware functions are not implemented.

``Substitute``
  QEMU supplies a functional replacement rather than the historical device.
  This is usually sufficient for firmware or guest compatibility but should not
  be mistaken for the original hardware.

``Missing``
  The historical function is not currently represented by the machine.

``Under validation``
  QEMU has an implementation or topology hypothesis, but the exact historical
  identity, location, wiring, or firmware-visible behavior still needs to be
  checked against primary hardware evidence or a real-machine device tree.

Power Mac G3 Beige (``g3beige``)
================================

The ``g3beige`` machine models the Heathrow-based OldWorld Power Mac G3.  It is
kept separate from the NewWorld/Core99 machines because its platform firmware,
I/O controller and PCI organization belong to the earlier Macintosh hardware
family.

A detailed component-by-component historical status table has not yet been
added for this machine.

Generic Core99 PowerMac (``mac99``)
===================================

The ``mac99`` machine is QEMU's general NewWorld PowerMac implementation.  It
provides the common Core99 building blocks used by several later Macintosh
configurations and is also the implementation parent of ``powermac3_1``.

The 32-bit machine defaults to a PowerPC 7400 CPU, standard VGA display,
Sungem Ethernet, two PMAC IDE interfaces and a CUDA configuration.  The
``via`` machine property can select ``cuda``, ``pmu`` or ``pmu-adb`` where a
guest needs a different Core99 I/O-controller arrangement.

Because ``mac99`` is a compatibility machine rather than one exact Macintosh,
its device layout should not be used by itself as evidence for the hardware
layout of a specific Apple model.

Power Mac G4 AGP / Sawtooth (``powermac3_1``)
==============================================

The ``powermac3_1`` machine is a historical profile built on the ``mac99``
device implementation.  It selects a PowerPC 7400 processor, 128 MiB of
default RAM, a KeyLargo PMU without ADB, USB keyboard and mouse input, and a
Sawtooth-specific PCI/AGP layout.

A typical Mac OS 9 test command is::

  qemu-system-ppc -machine powermac3_1 -m 128M \
    -bios pc-bios/openbios-ppc -boot d -cdrom macos9.iso

Hardware status
---------------

.. list-table:: PowerMac3,1 hardware and QEMU implementation status
   :header-rows: 1
   :widths: 18 25 36 16

   * - Subsystem
     - Historical target
     - Current QEMU model
     - Status
   * - Processor
     - PowerPC G4 7400 family
     - ``7400_v2.9`` is the default and only accepted CPU type for the
       historical profile.
     - Modeled
   * - Main memory
     - SDRAM attached through the UniNorth memory controller
     - Generic QEMU RAM with a 128 MiB historical-profile default.  DIMM
       population and memory timing are not modeled as physical modules.
     - Partial
   * - UniNorth
     - Memory controller and system bus bridge
     - UniNorth host logic with separate main PCI, internal PCI and AGP-facing
       buses plus a subset of Core99 power, arbitration and initialization
       registers.
     - Partial
   * - AGP
     - 32-bit, 66 MHz AGP-2X graphics slot
     - A separate UniNorth AGP PCI bus, fixed AGP-facing address apertures and
       the automatic display device at slot ``0x10``.  AGP protocol behavior
       and the UniNorth GART are not yet implemented.
     - Partial
   * - Graphics card
     - AGP graphics card supplied with the machine
     - QEMU's selected PCI VGA-compatible device is placed on the AGP bus.
       Native Sawtooth graphics hardware is not emulated.
     - Substitute
   * - Secondary PCI bridge
     - Bridge feeding the secondary PCI expansion/I/O side of the machine
     - QEMU currently creates a DEC 21154 PCI-to-PCI bridge at device ``0x0d``
       and places the south-side devices behind it.  Apple documentation
       confirms a secondary PCI bus and bridge, but the exact DEC identity,
       revision, interrupt routing and firmware programming are still being
       validated.
     - Under validation
   * - KeyLargo / MacIO
     - KeyLargo I/O controller
     - NewWorld MacIO on the secondary PCI side with PMU, MPIC, IDE, SCC,
       GPIO/DB-DMA infrastructure and a modeled subset of the KeyLargo feature
       control registers.
     - Partial
   * - Interrupt controller
     - KeyLargo MPIC
     - QEMU OpenPIC configured for the KeyLargo model and connected to the
       UniNorth PCI interrupt outputs.
     - Modeled
   * - USB
     - Two independent KeyLargo USB root hubs
     - Two PCI OHCI controllers, each configured for two ports.  USB keyboard
       and mouse are supplied when ADB is not selected.
     - Modeled
   * - Ethernet
     - Built-in UniNorth/GEM-family Ethernet function
     - QEMU ``sungem`` model, whose implementation covers the GEM controller
       family used in Apple ASICs, placed on the UniNorth internal PCI bus.
       Exact Sawtooth firmware-visible placement is still being checked.
     - Under validation
   * - IDE / ATA
     - KeyLargo hard-disk and removable-media ATA channels
     - Two PMAC IDE interfaces are currently exposed.  The additional
       UltraDMA/ATA path present in the hardware family is not yet modeled.
     - Partial
   * - Internal modem path
     - Modem connected through the KeyLargo serial/communications path
     - The default Sawtooth configuration attaches a modem chardev to SCC
       channel A; it does not emulate the physical modem chipset.
     - Substitute
   * - NVRAM
     - NewWorld non-volatile parameter memory
     - QEMU MacIO NVRAM device with persistent storage available through the
       usual MTD/NVRAM drive configuration.
     - Modeled
   * - FireWire
     - Built-in IEEE 1394 controller and external ports
     - No Sawtooth FireWire controller is currently present.
     - Missing
   * - AirPort
     - Optional wireless LAN hardware
     - Not modeled by this machine.
     - Missing
   * - Audio
     - KeyLargo-connected sound subsystem
     - No hardware-exact Sawtooth audio implementation is currently provided.
     - Missing
   * - Power management
     - PMU, UniNorth and KeyLargo sleep/wake behavior
     - PMU selection plus a subset of UniNorth and KeyLargo control registers.
       Most clock gating, bus power removal and sleep/wake side effects are not
       yet connected to the affected devices.
     - Partial

Current QEMU topology
---------------------

At a high level, the current machine is arranged as follows::

  PowerPC 7400
       |
    UniNorth
       |
       +-- AGP bus -------------------- VGA-compatible substitute
       |
       +-- internal PCI --------------- Sungem Ethernet
       |
       +-- main PCI
             |
             +-- DEC 21154 (under validation)
                    |
                    +-- KeyLargo / MacIO
                    +-- OHCI USB controller 0
                    +-- OHCI USB controller 1
                    +-- PCI expansion devices

This diagram describes the current QEMU implementation.  In particular, the
DEC 21154 label should not yet be read as a settled historical identification
of the physical Sawtooth bridge.

Accuracy notes and open work
----------------------------

The largest remaining accuracy questions are no longer basic machine
registration.  They are the hardware details visible to firmware and operating
systems:

* confirm the exact identity, revision, bus numbering, windows and interrupt
  routing of the secondary PCI bridge;
* compare QEMU PCI device/function numbers with a real PowerMac3,1 Open
  Firmware device tree;
* implement the UniNorth GART and additional AGP behavior rather than treating
  the AGP side only as a PCI-compatible bus with fixed apertures;
* model the missing ATA/UltraDMA channel and its KeyLargo feature-control side
  effects;
* connect KeyLargo and UniNorth power-control bits to actual USB, IDE, PCI and
  sleep/wake behavior;
* add FireWire, audio and other missing built-in devices where QEMU has or can
  gain suitable reusable device models; and
* replace the generic VGA substitute with native graphics hardware when an
  appropriate model becomes available.

This status section is intentionally conservative.  A device being in the
correct general hardware family does not by itself prove its PCI slot,
interrupt line, register defaults, Open Firmware node, or power-management
behavior.

Firmware
--------

Since version 0.9.1, QEMU uses OpenBIOS https://www.openbios.org/ for the
``g3beige`` and ``mac99`` PowerMac machines.  The ``powermac3_1`` profile uses
the same OpenBIOS firmware path while presenting the more specific Sawtooth
machine topology to firmware and the guest.

The historical profile does not embed or require an Apple ROM.  The firmware
loader accepts a compatible PowerPC ELF image or a raw PROM image.  A
firmware-specific reset entry may be selected with::

  qemu-system-ppc -machine powermac3_1,firmware-entry=0xfff00200 ...

For historical Power Mac G4 systems, Open Firmware is part of the hardware
contract: it configures platform controllers, probes PCI devices, constructs
the device tree, and exposes boot devices.  Therefore a successful CPU boot is
not by itself sufficient validation of ``powermac3_1``; the firmware-visible
bus and device tree topology also needs to match the target machine closely.

Historical references
---------------------

The principal hardware reference for the Sawtooth profile is Apple's original
Power Mac G4 developer documentation.  Archived copies document the 33 MHz
secondary PCI expansion bus and its power-managed bridge, the 32-bit 66 MHz
AGP-2X slot, and the role of Open Firmware in configuring UniNorth and
KeyLargo and constructing the device tree:

* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/G4Rev2-77.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/G4Rev2-89.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/PowerMac_G4_16Feb00/G4Rev3-21.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/PowerMac_G4_16Feb00/G4Rev3-84.html

These references describe the hardware family and are useful controls, but
later Power Mac G4 revisions must not be silently treated as evidence for the
1999 PowerMac3,1 when their logic-board design changed.
