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

The hardware tables below keep historical evidence confidence separate from
QEMU implementation status.  A component can be very well documented and
still be completely absent from QEMU; conversely, a useful QEMU compatibility
device is not by itself evidence that the historical machine contained that
exact device.

Evidence confidence uses these terms:

``High``
  The target component or topology is stated by Apple documentation, visible
  in a contemporary system description, or corroborated by real-machine
  hardware enumeration.

``Medium``
  The general component is well supported but one or more details, such as a
  chip revision, GPIO assignment, interrupt route or firmware node, are based
  on indirect or later-family evidence.

``Low``
  The current target is still a working hypothesis and must not be treated as
  settled hardware identity.

QEMU implementation status uses these terms.  They describe the current model,
not a promise of cycle-accurate hardware timing.

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

Apple's original 1999 developer note describes 350, 400 and 450 MHz processor
configurations.  The QEMU profile deliberately fixes a 450 MHz reference
configuration rather than pretending that one machine definition reproduces
every PowerMac3,1 retail or later board variant.

A typical Mac OS 9 test command is::

  qemu-system-ppc -machine powermac3_1 -m 128M \
    -bios pc-bios/openbios-ppc -boot d -cdrom macos9.iso

Hardware status
---------------

.. list-table:: PowerMac3,1 hardware and QEMU implementation status
   :header-rows: 1
   :widths: 16 23 34 12 13

   * - Subsystem
     - Historical target
     - Current QEMU model
     - Evidence
     - QEMU status
   * - Processor
     - PowerPC G4 7400 family; 350, 400 or 450 MHz in the original 1999
       configurations
     - ``7400_v2.9`` is the default and only accepted CPU type.  The profile
       publishes a 450 MHz processor frequency and 100 MHz system-bus
       frequency.
     - High
     - Modeled
   * - Backside L2 cache
     - 1 MiB backside SRAM cache on the processor module, clocked at half the
       processor frequency
     - The 7400 CPU exposes cache-related architectural state such as ``L2CR``,
       but QEMU does not model a physical 1 MiB backside cache, cache storage or
       cache timing.
     - High
     - Partial
   * - Main memory
     - Up to four PC100 SDRAM DIMMs on a 100 MHz, 64-bit memory bus; up to
       2 GiB supported by the memory controller
     - Generic QEMU RAM with a 128 MiB historical-profile default and a 2 GiB
       maximum address-space allowance.  DIMM population, SPD contents and
       memory timing are not modeled as physical modules.
     - High
     - Partial
   * - UniNorth
     - Memory controller and system-bus bridge
     - UniNorth host logic with separate main PCI, internal PCI and AGP-facing
       buses plus a subset of Core99 power, arbitration and initialization
       registers.
     - High
     - Partial
   * - AGP
     - 32-bit AGP-2X graphics slot on the UniNorth AGP path
     - A separate UniNorth AGP PCI bus, fixed AGP-facing address apertures and
       the automatic display device at slot ``0x10``.  AGP protocol behavior
       and the UniNorth GART are not yet implemented.
     - High
     - Partial
   * - Graphics card
     - ATI RAGE 128 PRO with 16 MiB SDRAM in the AGP slot
     - QEMU ``ati-vga`` with ``model=rage128p`` and 16 MiB VRAM is installed at
       AGP device ``0x10`` by default.  The ATI model is intentionally partial:
       it implements enough register/framebuffer behavior for basic display and
       some 2D use, but not the complete accelerator or 3D engine.
     - High
     - Partial
   * - Secondary PCI bridge
     - PCI-to-PCI bridge between the 32-bit 66 MHz UniNorth bus and the 64-bit
       33 MHz KeyLargo/expansion bus.  Later Apple documentation identifies the
       family bridge as DEC 21154-66, and real PowerMac3,1 enumeration reports a
       DEC 21154 revision 0x05 at device ``0x0d``.
     - QEMU creates a DEC 21154 at device ``0x0d`` with device ID ``0x0026``
       and revision ``0x05``.  The current model is a generic PCI bridge core:
       the DEC-specific two-tier arbiter, buffering/transaction optimizations,
       detailed interrupt routing, power behavior and firmware programming are
       not implemented.
     - High
     - Partial
   * - KeyLargo / MacIO
     - KeyLargo I/O and disk controller on the 33 MHz secondary PCI side
     - NewWorld MacIO at device ``0x07`` with PMU, MPIC, IDE, SCC, GPIO/DB-DMA
       infrastructure and a modeled subset of the KeyLargo feature-control
       registers.
     - High
     - Partial
   * - KeyLargo GPIO
     - KeyLargo GPIO and external-interrupt registers used by board-level
       devices and power/interrupt glue
     - QEMU exposes the KeyLargo GPIO level area plus 18 external-interrupt and
       17 ordinary GPIO registers.  Only a small set of external GPIO interrupt
       semantics is currently hard-wired; general pin functions, polarity and
       board wiring are not modeled.
     - Medium
     - Partial
   * - Interrupt controller
     - KeyLargo MPIC
     - QEMU OpenPIC configured for the KeyLargo model and connected to the
       UniNorth PCI interrupt outputs.
     - High
     - Modeled
   * - USB
     - Two independent KeyLargo USB/OHCI root hubs.  Each supplies one rear
       connector; the second port of one path reaches the AGP slot and the
       second port of the other reaches the internal modem slot.
     - Two Apple PCI OHCI controllers, each configured for two ports, are
       placed at devices ``0x08`` and ``0x09`` behind the secondary bridge.
       Real-machine PCI enumeration corroborates those two function locations.
       Internal routing, suspend/power and exact Open Firmware node behavior
       remain incomplete.
     - High
     - Partial
   * - Ethernet
     - Built-in UniNorth Ethernet MAC and external PHY, supporting 10Base-T and
       100Base-TX
     - QEMU ``sungem`` uses the Apple UniNorth GMAC PCI identity, revision
       ``0x01``, and is placed at device ``0x0f`` on the UniNorth internal PCI
       bus, matching real PowerMac3,1 enumeration.  PHY details, power behavior
       and timing are not hardware-exact.
     - High
     - Partial
   * - IDE / ATA
     - One KeyLargo Ultra DMA/66 interface for hard disks and one EIDE
       interface for DVD/optional Zip removable media
     - Two PMAC IDE interfaces are exposed.  The historical existence of two
       distinct Sawtooth interfaces is clear, but their QEMU transfer-mode,
       address, DMA and firmware-node correspondence still needs direct
       validation; the generic Core99 comment about a third controller is not
       evidence that PowerMac3,1 itself requires a third channel.
     - High
     - Under validation
   * - Internal modem path
     - Separate modem module attached to the KeyLargo communication slot; the
       module contains a modem controller, datapump and telephone-line DAA
     - The default Sawtooth configuration attaches a modem chardev to SCC
       channel A.  It represents the serial communications path, not the
       physical modem module.
     - High
     - Substitute
   * - NVRAM
     - NewWorld non-volatile parameter storage used by Open Firmware
     - QEMU MacIO NVRAM device with persistent storage available through the
       usual MTD/NVRAM drive configuration.  Correct boot-policy persistence
       also depends on the firmware not resetting stored variables at startup.
     - High
     - Modeled
   * - Boot ROM / flash
     - 1 MiB on-board flash EPROM attached to the 66 MHz PCI side, containing
       hardware-specific startup code and tables
     - QEMU loads OpenBIOS or another compatible firmware image into a PROM
       memory window.  It does not model the Sawtooth flash device as a PCI-side
       programmable component and does not contain Apple's historical ROM
       contents.
     - High
     - Substitute
   * - FireWire
     - IEEE 1394a/FireWire 400 controller and PHY with two external ports and
       one internal port.  Real-machine PCI enumeration identifies a Texas
       Instruments TSB12LV23 at secondary-bus device ``0x0a``.
     - A dedicated ``tsb12lv23`` device is installed at secondary-bus device
       ``0x0a`` with PCI identity ``104c:8019``, revision ``0x00``, OHCI
       programming interface ``0x10``, a 2 KiB OHCI BAR, a 16 KiB TI extension
       BAR and PCI power-management capability.  Probe/reset-oriented OHCI
       control, interrupt, CSR, filter and migration state is present.  The
       separate PHY, three-port topology, bus reset/self-ID process, packet
       transport and asynchronous/isochronous DMA engines remain unimplemented.
     - High
     - Partial
   * - AirPort
     - Optional internal 11 Mbps wireless LAN module in the wireless LAN slot
     - Not modeled by this machine.
     - High
     - Missing
   * - Audio
     - Screamer 16-bit audio codec connected to KeyLargo's DAV path with
       DB-DMA support
     - No Screamer-compatible Sawtooth audio device is currently provided.
     - High
     - Missing
   * - Power management
     - PMU99 plus UniNorth/KeyLargo clock, bus and device power control; USB and
       the secondary PCI side participate in sleep/power transitions
     - PMU selection plus a subset of UniNorth and KeyLargo control registers.
       Most clock gating, bus power removal, FireWire PHY continuity and
       sleep/wake side effects are not connected to the affected devices.
     - High
     - Partial

Current QEMU topology
---------------------

At a high level, the current machine and its partial FireWire controller are
arranged as follows::

  PowerPC 7400 (450 MHz reference profile)
       |
    UniNorth
       |
       +-- AGP bus -------------------- ATI Rage 128 Pro (partial) @ 0x10
       |
       +-- internal PCI --------------- Sungem/UniNorth GMAC @ 0x0f
       |
       +-- main PCI
             |
             +-- DEC 21154 rev 0x05 @ 0x0d
                    |
                    +-- KeyLargo / MacIO @ 0x07
                    +-- OHCI USB controller 0 @ 0x08
                    +-- OHCI USB controller 1 @ 0x09
                    +-- TI TSB12LV23 FireWire (partial) @ 0x0a
                    +-- PCI expansion devices

The DEC identity/revision and the ``0x07``/``0x08``/``0x09``/``0x0a`` south-bus
layout are no longer treated as an undifferentiated hypothesis: Apple family
documentation and real PowerMac3,1 PCI enumeration corroborate the bridge and
built-in-device arrangement.  The remaining uncertainty is primarily detailed
register, interrupt, firmware-node and power behavior rather than those basic
PCI identities.

Physical address map
--------------------

The CPU-visible PCI apertures follow the ``ranges`` properties captured from
a PowerMac3,1 Open Firmware device tree.  Main memory may extend up to 2 GiB;
at that maximum size it ends at ``0x7fffffff``, immediately below the first
PCI aperture.

.. list-table:: PowerMac3,1 principal memory ranges
   :header-rows: 1
   :widths: 24 20 56

   * - CPU address range
     - Size
     - Use
   * - ``0x00000000`` through RAM end
     - Up to 2 GiB
     - Main memory
   * - ``0x80000000-0x8fffffff``
     - 256 MiB
     - Main PCI coarse memory window
   * - ``0x90000000-0x9fffffff``
     - 256 MiB
     - AGP coarse memory window
   * - ``0xf0000000-0xf07fffff``
     - 8 MiB
     - AGP PCI I/O window
   * - ``0xf0800000`` and ``0xf0c00000``
     - 4 KiB each
     - AGP configuration index and data windows
   * - ``0xf1000000-0xf1ffffff``
     - 16 MiB
     - AGP fine memory window
   * - ``0xf2000000-0xf27fffff``
     - 8 MiB
     - Main PCI I/O window
   * - ``0xf2800000`` and ``0xf2c00000``
     - 4 KiB each
     - Main PCI configuration index and data windows
   * - ``0xf3000000-0xf3ffffff``
     - 16 MiB
     - Main PCI fine memory window
   * - ``0xf4000000-0xf47fffff``
     - 8 MiB
     - Internal PCI I/O window
   * - ``0xf4800000`` and ``0xf4c00000``
     - 4 KiB each
     - Internal PCI configuration index and data windows
   * - ``0xf5000000-0xf5ffffff``
     - 16 MiB
     - Internal PCI memory window

QEMU's synthetic ``fw_cfg`` interface remains at ``0xf0000510`` (control)
and ``0xf0000512`` (data), as required by the PowerPC OpenBIOS firmware ABI.
For ``powermac3_1`` these registers occupy PCI I/O ports ``0x510-0x512``
inside the AGP I/O window.  They are not independent mappings overlapping the
UniNorth aperture at the root of the CPU address space.

Accuracy notes and open work
----------------------------

The largest remaining accuracy questions are no longer basic machine
registration or the identity of every visible PCI function.  They are the
hardware behaviors that firmware and operating systems can observe:

* implement the UniNorth GART and additional AGP protocol behavior rather than
  treating the AGP side only as a PCI-compatible bus with fixed apertures;
* extend the Rage 128 Pro model beyond its current basic framebuffer/2D subset
  and verify the Apple firmware/driver-visible register defaults;
* implement DEC 21154-66-specific arbitration, buffering, interrupt and power
  behavior instead of relying only on the generic PCI-bridge core;
* map QEMU's two PMAC IDE interfaces to the Sawtooth Ultra DMA/66 and EIDE
  channels at the transfer-mode, DMA and Open Firmware-node levels;
* identify and connect the remaining KeyLargo GPIO pins, interrupt polarity and
  board-level functions instead of treating most GPIOs as storage only;
* connect KeyLargo and UniNorth power-control bits to actual USB, IDE, PCI and
  sleep/wake behavior;
* represent the physical boot-flash relationship without confusing QEMU's
  OpenBIOS firmware image with Apple's historical 1 MiB ROM contents;
* complete the TSB12LV23 FireWire path with a real PHY, three-port topology,
  bus reset/self-ID behavior, packet transport and OHCI async/iso DMA rather
  than treating the controller-only implementation as a complete 1394 bus;
* add Screamer audio and AirPort only when suitable device models can represent
  real guest-visible behavior rather than placeholder hardware; and
* keep separate PowerMac3,1 retail/board variants separate when evidence shows
  a hardware distinction instead of silently flattening them into the 450 MHz
  reference profile.

This status section is intentionally conservative.  A device being in the
correct general hardware family does not by itself prove its interrupt line,
register defaults, Open Firmware node, power-management behavior or timing.

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
bus and device-tree topology also needs to match the target machine closely.

Historical references
---------------------

The principal hardware reference for the Sawtooth profile is Apple's original
1999 Power Mac G4 developer note.  It documents the CPU module, 1 MiB backside
L2 cache, PC100 memory system, UniNorth buses and GART, PCI bridge topology,
1 MiB boot flash, KeyLargo USB/ATA/communication paths, FireWire, Screamer
sound, PMU99 and the ATI RAGE 128 PRO graphics card:

* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/Original_G4.pdf

The original note is also available as individual archived HTML sections:

* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/G4Rev2-16.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/G4Rev2-77.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/G4Rev2-81.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/Original_PowerMac_G4/G4Rev2-89.html

A later UniNorth Power Mac G4 developer note is useful as a control for shared
hardware details that the original note leaves unnamed, including the explicit
DEC 21154-66 bridge identity and its two-tier arbiter.  Later Power Mac G4
revisions must not otherwise be silently treated as evidence for the 1999
PowerMac3,1 when their logic-board design changed:

* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/PowerMac_G4_16Feb00/PowerMacG4.pdf

A real PowerMac3,1 PCI enumeration published on the Debian PowerPC mailing list
corroborates DEC 21154 revision ``0x05``, KeyLargo at ``0x07``, the two USB
functions at ``0x08``/``0x09``, TI TSB12LV23 FireWire at ``0x0a`` and the
Rage 128 PF/PRO at AGP ``0x10``:

* https://lists.debian.org/debian-powerpc/2004/07/msg00216.html
