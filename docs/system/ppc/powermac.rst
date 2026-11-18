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

Mac OS X Tiger (10.4) hardware compatibility
--------------------------------------------

Tiger is the last Mac OS X release officially supported on the original
350--500 MHz PowerMac3,1 family. Apple's 2005 Tiger requirements specify
a G3, G4 or G5 Macintosh with built-in FireWire and at least 256 MiB RAM.
Apple's Leopard 10.5 requirements raise the supported G4 CPU floor to
867 MHz. This is a guest compatibility target, not a reason to change
Sawtooth's historically correct 128 MiB launch default.

For a Tiger installation experiment, supply at least 256 MiB explicitly::

  qemu-system-ppc -machine powermac3_1 -m 256M \
    -bios pc-bios/openbios-ppc -boot d -cdrom tiger-install.iso

The filename stands for the user's own installation image. This command
is **not** evidence that the Tiger installer currently boots or that all
Apple drivers initialize.

Apple's published PowerPC-era open-source components provide useful driver
contracts. They do not include every proprietary Tiger driver. The latest
published source revision must not be assumed identical to the Tiger 10.4.11
binary: pin a release-specific tag before importing register behavior.

* **AppleKeyLargo**: feature-control registers, GPIO routing, USB power
  and reset. Compare with QEMU's FCR/GPIO model. Missing behavior includes
  how those bits affect real device clocks and power states.
  Source: https://github.com/apple-oss-distributions/AppleKeyLargo
* **AppleMacRISC2PE**: G4/UniNorth platform startup, CPU and power-management
  integration. Compare Sawtooth PMU/UniNorth wiring; do not introduce later
  K2/G5 board assumptions into the original PowerMac3,1 profile.
  Source: https://github.com/apple-oss-distributions/AppleMacRISC2PE
* **IOFireWireFamily**: bus reset, node/self-ID and configuration-ROM behavior
  above the PCI/OHCI boundary. The TSB12LV23 models controller registers but
  lacks a separate PHY, real ports, packet transport and async/iso DMA. Do
  not advertise attached PHYs or successful FireWire device enumeration yet.
  Source: https://github.com/apple-oss-distributions/IOFireWireFamily
* **IOUSBFamily**: OHCI root-hub and port state transitions. Sawtooth has
  two KeyLargo USB functions, but board-level power, clock and reset effects
  require validation.
  Source: https://github.com/apple-oss-distributions/IOUSBFamily
* **AppleGMACEthernet**: GMAC/MII link and PHY setup. QEMU exposes a
  BCM5201-compatible PHY; KeyLargo PHY reset, clock gating and PHY interrupt
  or autopoll behavior are incomplete. Do not substitute later gigabit
  PowerMac board behavior for this 10/100 PHY.
  Source: https://github.com/apple-oss-distributions/AppleGMACEthernet

For each Tiger driver failure, record the Open Firmware node, PCI/OF driver
match and first failing MMIO/interrupt/power operation. Compare with the
correct Tiger-version source and a hardware reference before implementing a
narrow fix. The existing FireWire runtime test checks device and bridge
topology; it does not demonstrate a functional IEEE-1394 PHY.

Apple's system requirements:

* https://www.apple.com/newsroom/2005/04/12Apple-to-Ship-Mac-OS-X-Tiger-on-April-29/
* https://support.apple.com/zh-cn/HT2226

Tiger KeyLargo and blank-screen source audit
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The May 12, 2005 ``AppleKeyLargo-170.0.0`` sources distinguish KeyLargo
power/control services from AGP display initialization. ``KeyLargo::start``
requires the Open Firmware root ``clock-frequency``, the MacIO ``device-id``
and ``revision-id``; it also probes PMU and USB clock properties. Its FCR offsets
(0x38 through 0x48) match QEMU's KeyLargo register layout. The pinned
PPC-Firmware/OpenBIOS source already publishes the root clock, PCI device
and revision IDs, ``/uni-n`` with ``device-rev``, and Sawtooth USB clock IDs.
This is a source-level match, not proof of a successful Tiger boot.

Tiger BootX also exposes an **earlier** source-backed display discovery
fault: it searches for device type ``display``; the prior OpenBIOS PCI
database classified the Rage 128 as ``ATY``, while ``install-console``
also requires type ``display`` to create the ``screen`` alias.
The pinned firmware now advertises ``display`` for Rage 128 and QEMU
VGA, preserving vendor/model identity. This corrects firmware discovery,
but is not yet an observed successful boot or framebuffer initialization.

After OpenBIOS finds and opens a display, the firmware-to-Tiger
graphics-driver handoff remains a separate hypothesis: OpenBIOS uses
generic VGA/VBE FCode, while QEMU's ``ati-rage128p`` lacks complete
native Rage 128 register behavior.

After building both QEMU and its pinned OpenBIOS firmware, compare these
commands using the **same** Tiger image and firmware::

  qemu-system-ppc -machine powermac3_1 -m 256M -vga std \
    -bios openbios-ppc -boot d -cdrom tiger-install.iso

  qemu-system-ppc -machine powermac3_1 -m 256M -vga cirrus \
    -bios openbios-ppc -boot d -cdrom tiger-install.iso

Replace ``openbios-ppc`` with the path to the freshly built ROM and the ISO
name with the actual guest image. For this machine, ``-vga std`` **selects
the factory ATI Rage 128**, not QEMU's generic standard VGA controller.
``-vga cirrus`` is a diagnostic substitute, not Sawtooth's real card.
If only the ATI run blanks, inspect Rage 128 BAR/FCode, framebuffer mode,
and native driver initialization; if both blank, inspect firmware/boot
progress and platform initialization before changing KeyLargo registers.
Record whether video fails before OpenBIOS, during BootX, or only when the
Tiger driver takes control. Neither command is a confirmed successful boot.

Source baselines:

* https://github.com/apple-oss-distributions/AppleKeyLargo/tree/AppleKeyLargo-170.0.0
* https://github.com/retrochristian5000/PPC-Firmware/blob/5293b81833d9761fa300ca3b9a6f24e8b773d047/drivers/pci_database.c
* https://github.com/retrochristian5000/PPC-Firmware/blob/5293b81833d9761fa300ca3b9a6f24e8b773d047/drivers/vga.fs
* https://github.com/apple-oss-distributions/BootX/blob/BootX-74.1/bootx.tproj/sl.subproj/display.c
* https://github.com/apple-oss-distributions/BootX/blob/BootX-74.1/bootx.tproj/sl.subproj/main.c

Sawtooth boot flash and early firmware execution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Apple's February 2000 Power Mac G4 developer note describes a **1 MiB
on-board flash EPROM** on UniNorth's 66 MHz PCI lines. The ROM shares
the 32 multiplexed PCI address/data signals and four byte enables,
but has dedicated UniNorth chip-enable, output-enable and write-enable
signals. This is *not* a normal enumerable PCI card and its identity
must not be synthesized as a fake PCI vendor/device ID. Apple's
PowerMac3,1 device tree includes
``/rom@ff800000/boot-rom@fff00000``; the child package's mapped
address and length correspond to QEMU's existing ROM window.

OpenBIOS now advertises the ``boot-rom`` child of ``/rom`` for
``PowerMac3,1`` only. The firmware image itself is still loaded by
``hw/ppc/mac_newworld.c`` into ``0xfff00000``--``0xffffffff``,
and the CPU starts at the existing ``0xfff00100`` default reset
entry. NVRAM is separately mapped at ``0xfff04000`` within that
window, reflecting the legacy NewWorld writable configuration
region; QEMU does not emulate actual NOR-flash erase/program cycles,
flash wear or a firmware-updater transaction. The precise Apple
flash-chip manufacturer, package and command set are **unverified**,
so no generic CFI model or guessed flash device IDs are introduced.
A real firmware updater image is not interchangeable with the
OpenBIOS executable or the disk-loaded NewWorld Mac OS ROM.

This discovery narrows early boot checks: validate the reset-vector
bytes and whether OpenBIOS reaches initialization, then examine PCI
and display FCode only after firmware executes. A missing physical
flash command set cannot, by itself, explain a black display if the
PROM contents are loaded and executing correctly. Firmware nodes
and PROM geometry are source-verified, not runtime boot-verified.

Historical sources:

* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/PowerMac_G4_16Feb00/PowerMacG4.pdf
* https://leopard-adc.pepas.com/technotes/tn/tn2001.html

BootX startup and Open Firmware console contract
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Apple's Tiger ``BootX-74.1`` proceeds through Open Firmware version
detection, ``/options`` and ``/chosen`` discovery, MMU/memory handles,
memory claims, and then ``InitDisplays``. It accepts the
``OpenFirmware 3`` model provided by the pinned OpenBIOS
``/openprom`` node. ``FindDisplays`` searches the device tree for
``device_type`` = ``display``, falls back to the ``screen`` alias,
and opens the screen before reading ``address``, ``width``,
``height``, ``depth`` and ``linebytes``. Its drawing path requires
firmware framebuffer methods. The corrected PCI device type makes
OpenBIOS's earlier ``install-console`` path eligible to create the
``screen`` alias and lets BootX discover the same display.

Verify the freshly built ROM, PCI probe, ``/aliases/screen``, and
``/chosen/stdout`` before attributing a blank screen to Tiger.
The FCode BAR mapping and actual framebuffer scanout remain independent
runtime checks: this change has not been proved to display pixels.

Open Firmware display standards and native Rage 128 initialization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

IEEE 1275-1994 defines the ``display`` device package as a console output
interface. The Open Firmware Working Group's 8-bit Graphics Extension 1.2
(1995 draft) adds rectangle, palette and dimensions methods. The CHRP
Linear Frame Buffer Device Binding 1.0 (1996 draft) provides additional
framebuffer geometry conventions. These are separate documents: a draft
CHRP ``chrp,lfb`` compatible string should not be forced onto the
historical ATI Rage 128 without supporting that specific binding.

Apple's Power Macintosh PCI guidance requires framebuffer properties
``width``, ``height``, ``depth`` and ``linebytes``. BootX also reads
``address`` and opens the firmware display. Its own display.c defines
rectangle words through Open Firmware ``interpret`` before drawing the
boot graphics. The previous OpenBIOS ``device_type=display`` correction
allows both firmware console selection and BootX device discovery, but
does not prove that the physical display mode is active.

The original black-screen investigation confirmed a register-interface
mismatch: generic OpenBIOS FCode was programming **Bochs VBE** at
``BAR2 + 0x500 + 2 * index`` on the Sawtooth ``ati-rage128p``.
Its BAR2 is instead a native 16 KiB ATI MMIO aperture with CRTC control
at 0x50, timing from 0x200, and palette registers near 0xb0.
QEMU's ATI model does not emulate Bochs VBE there. The following
native FCode path addresses this specific mismatch; the earlier
diagnostic remains useful for detecting regressions.

The pinned OpenBIOS now contains a **separate Rage 128 firmware
initialization path**. It selects ATI vendor/device 1002:5046,
requires BAR0/BAR2, and writes the native ATI timing, CRTC, pitch,
framebuffer aperture and palette registers, enabling the display
controller last. The generic VGA path still uses Bochs VBE; the ATI
card is not given fictitious Bochs registers. Current timing uses
approximate VGA-style porches and the QEMU model's implemented CRTC
subset: monitor-specific PLL and DDA behavior remain unverified.
This is an initial firmware implementation, **not** a confirmed
visible firmware console or successful Mac OS boot.

QTest
``/ppc/display/sawtooth-rage128-firmware-mmio`` checks that
Bochs-VBE-offset writes leave native CRTC control unchanged and
confirms native ATI timing-register access. This is a diagnostic
test, **not** evidence that firmware pixels or Tiger graphics boot.

Diagnosis should distinguish firmware entry, PCI/AGP discovery,
``/aliases/screen``, ``/chosen/stdout``, firmware FCode mode
programming, visible scanout and the subsequent OS driver
handoff. Use an actual rebuilt ROM; a Cirrus test is a
nonhistorical comparison, not a replacement for Sawtooth's ATI card.

Primary sources:

* https://www.openfirmware.info/data/docs/of1275.pdf
* https://www.devicetree.org/open-firmware/practice/graphics/graphicsd1_2.pdf
* https://www.devicetree.org/open-firmware/bindings/devices/html/lfb.html
* https://leopard-adc.pepas.com/documentation/Hardware/DeviceManagers/pci_srvcs/pci_cards_drivers/PCI_BOOK.5c.html
* https://github.com/apple-oss-distributions/BootX/blob/BootX-74.1/bootx.tproj/sl.subproj/display.c

Classic Mac OS self-mounting images
-----------------------------------

Classic Mac OS Disk Copy self-mounting ``.smi`` files are applications that
contain NDIF disk data. Preservation of the resource fork is essential.
MacBinary archives (often ``.smi.bin``) retain both forks and are supported
read-only by this fork's ``smi`` block-image driver for zero, raw and
ADC-compressed NDIF chunks. Other compression types, segmented disks and
missing ``bcem`` metadata are rejected rather than treated as raw sectors.

Use a preserved MacBinary archive for conversion::

  qemu-img info -f smi "Installer.smi.bin"
  qemu-img convert -f smi -O raw "Installer.smi.bin" "Installer.img"

The extracted volume may be HFS rather than a bootable hard disk or ISO CD,
and the embedded Classic Macintosh program is not executed. A standalone
``.smi`` with its resource fork lost cannot be recovered by renaming it.

Classic Mac OS disk-driver updates
----------------------------------

Classic Mac OS 8.6/9.x installer options such as **Update Apple Hard Disk
Drivers** modify Apple driver partitions *on the guest disk*. Those partitions
may include ``Apple_Driver_ATA`` and are distinct from the MacIO/KeyLargo
controller model and QEMU's host-side image format. QEMU must not silently
replace or rewrite them.

The MacIO IDE controller's ATA DBDMA read completion path is now separated
from the ATAPI CD-ROM packet-command callback. Previously an ATA hard-disk DMA
read completed through ATAPI status and error handling; that could destabilize
disk-driver installation or subsequent boot. This repairs an emulator defect,
not every possible Apple installer or driver incompatibility.

For a new Mac OS 9 installation, initialize the disk with the matching
installer's Drive Setup utility, then disable **Update Apple Hard Disk
Drivers** in the Installer Options unless driver replacement is intentional.
Keep a backup of any image before enabling this operation. To investigate an
existing installation, run the test on a disposable image copy or under
``-snapshot``; do not assume that disabling the checkbox repairs driver
partitions already replaced by a previous installer run.

The Sawtooth-specific Mac OS 8.6 recovery-media driver version may differ
from later Drive Setup releases. The known historical workaround of restoring
the 8.6-era driver is a compatibility observation, not a substitute for
validating ``Apple_Driver_ATA`` partitions or a complete MacIO DMA test.

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
     - QEMU's fixed-identity ``ati-rage128p`` with 16 MiB VRAM is installed at
       AGP device ``0x10`` by default.  The ATI model is intentionally partial:
       it implements enough register/framebuffer behavior for basic display and
       some 2D use.  Rage128's 24-bpp packed 2D color fills are supported
       through a non-pixman fallback; source/destination blits use bounded
       visible rectangles and clipped VRAM dirty tracking.  This does not
       implement the complete accelerator, 3D commands, or AGP protocol.
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
       bus, matching real PowerMac3,1 enumeration.  Its MIF path exposes a
       BCM5201-compatible 10/100 PHY identity with stateful BMCR and ANAR
       programming, software reset, power-down/isolate handling, Broadcom
       auxiliary/multiphy controls, and auto-negotiation status resolved from
       the guest advertisement plus QEMU backend carrier state.  UniNorth GMAC
       clock gating, KeyLargo PHY-reset wiring, PHY interrupt/autopoll events
       and the exact physical Sawtooth PHY revision remain incomplete or under
       validation.
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
     - Optional Apple 56K K56flex/V.90 module (fax up to 14.4 Kbps) in a
       proprietary 70-pin slot with separate telephone-line filter. KeyLargo
       connects a serial port and alternative I2S signals to the slot with
       DB-DMA; an internal USB signal pair also reaches the connector.
     - Sawtooth's default configuration attaches QEMU's Hayes 2400-class
       substitute to SCC A. The KeyLargo modem-reset GPIO at offset ``0x6d``
       resets it. ``-machine powermac3_1,modem=off`` or ``-nodefaults``
       leaves the module absent. The Apple controller IC, V.90 datapump,
       telephone-line DAA/fax, I2S DB-DMA, call-progress audio, and optional
       USB-mode modem remain unimplemented; the generic Hayes personality
       must not be described as a hardware-accurate Apple 56K modem.
     - High for slot and reset wiring; unresolved modem silicon
     - Partial / substitute
   * - NVRAM
     - NewWorld non-volatile parameter storage used by Open Firmware
     - QEMU MacIO NVRAM device with persistent storage available through the
       usual MTD/NVRAM drive configuration.  Correct boot-policy persistence
       also depends on the firmware not resetting stored variables at startup.
     - High
     - Modeled
   * - Boot ROM / flash
     - 1 MiB on-board flash EPROM attached directly to UniNorth's 66 MHz PCI
       lines, with separate chip-enable, output-enable and write-enable pins.
       Apple Open Firmware names the device
       ``/rom@ff800000/boot-rom@fff00000``.
     - QEMU maps a 1 MiB OpenBIOS PROM at ``0xfff00000``, and its NewWorld
       NVRAM region overlays ``0xfff04000`` for writable configuration data.
       The pinned OpenBIOS now exposes a Sawtooth-specific ``boot-rom``
       child beneath ``/rom`` with a matching ``reg`` address/length.
       ROM storage and OF identity are modeled, but no manufacturer-specific
       flash program/erase command set or original Apple Boot ROM contents
       are present.
     - High
     - Partial / firmware substitute
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
     - The PowerMac3,1 profile exposes a Screamer-compatible DAV register
       block at MacIO offset ``0x14000`` and uses DB-DMA channels ``0x10``
       (playback) and ``0x12`` (capture). Playback supports the eight basic
       22 MHz-family sample rates, codec readback, output A/C attenuation
       and mute controls, and DAV byte swapping. KeyLargo FCR1 now gates
       the Screamer audio cell/clock path, so guest power-management writes
       stop and resume codec activity instead of being readback-only. Playback
       now buffers complete four-byte stereo frames across fragmented DB-DMA
       descriptors and circular-buffer boundaries, avoiding partial-frame
       writes to the host sound backend. Capture
       currently returns silence; detailed analog jack/speaker sensing and
       migration are not modeled. The shared KeyLargo DB-DMA controller
       accepts physical buffer address zero, exposes read-only channel
       status, and prevents descriptor-pointer changes while RUN is set
       (including a paused channel). These register/descriptor rules affect
       both Screamer audio and MacIO IDE transfers.
     - High
     - Partial
   * - Power management
     - PMU99 plus UniNorth/KeyLargo clock, bus and device power control; USB and
       the secondary PCI side participate in sleep/power transitions
     - PMU selection plus a subset of UniNorth and KeyLargo control registers.
       KeyLargo FCR1 audio cell/clock gating is connected to Screamer; most
       other clock gating, bus power removal, FireWire PHY continuity and
       sleep/wake side effects are not connected to the affected devices.
     - High
     - Partial

Tiger-era UniNorth register comparison
--------------------------------------

Apple's April 2005 ``AppleMacRISC2PE-170.2.1`` driver sources define
the Sawtooth UniNorth-1.0A revision as ``0x07``. During initialization,
``AppleUniN::start`` reads that version and updates the QAck arbitration
delay in register ``0x0040``. QEMU already models that register, including
read/modify/write access, and OpenBIOS advertises a corresponding
``/uni-n`` revision.

The Tiger driver also uses ``0x0100`` (AACK delay enable, bit zero) and
``0x0170`` (VSP soft-reset state saved/restored across UniNorth power
transitions). QEMU now preserves those two register values, resets them
on machine reset, and includes them in versioned migration state. AACK
only exposes its documented bit. VSP is a register-state compatibility
model: it does **not** emulate downstream soft-reset effects.

Tiger's later-revision Max/PCI memory-timeout register at ``0x2160``
is only programmed for UniNorth 1.5--2.0 and certain other Apple
northbridges. It must not be enabled solely to make a 1.0A Sawtooth
look more like a later machine. Similarly, Intrepid clock-stop status
registers are not evidence of an AGP clock fault on PowerMac3,1.

These fixes improve Tiger's UniNorth driver-visible contract but
do **not** establish the source of a blank screen. The AGP Rage 128
firmware/driver handoff and actual guest boot progression need separate
runtime checks. QTest ``/ppc/uninorth/sawtooth-registers`` exercises the
documented control-register programming without any guest ROM.

Apple sources, pinned to the 2005 release:

* https://github.com/apple-oss-distributions/AppleMacRISC2PE/blob/AppleMacRISC2PE-170.2.1/UniN.cpp
* https://github.com/apple-oss-distributions/AppleMacRISC2PE/blob/AppleMacRISC2PE-170.2.1/UniN.h

UniNorth CPU identification
---------------------------

The UniNorth register at offset ``0x0050`` is historically described as a
possible per-processor CPU-number indicator, used by firmware when deciding
whether the boot processor or a secondary processor should start.  The exact
hardware behavior is not fully established by that description.

The existing ``mac99`` machine and its ``powermac3_1`` subclass currently
limit QEMU to **one** CPU.  UniNorth therefore reads back bootstrap processor
number ``0`` without consulting QEMU's execution-thread-local
``current_cpu`` or internal ``CPUState.cpu_index``.  QTest MMIO reads may
run outside a guest CPU thread and must still return the same register value.

This is a single-CPU compatibility rule, **not** a validated SMP emulation.
If the Core99 machine gains secondary CPUs, their guest-visible hardware
identifiers, reset/firmware startup behavior and CPU_NUMBER reads need to be
modeled and tested before increasing the machine's CPU limit.

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
* implement the Apple 56K modem-controller datapump/DAA, K56flex/V.90
  modulation, fax, I2S DB-DMA and call-progress audio only after identifying
  the module's exact chipset and host interface; preserve the present Hayes
  substitute as a clearly named approximation;
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

Apple firmware releases and the OpenBIOS boundary
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Apple supplied boot-ROM firmware for the original PowerMac3,1/Sawtooth.
A historical Sawtooth version inventory reports Open Firmware ``3.2.4f1``
(February 2000), while Apple's Power Mac G4 Firmware Update ``4.2.8``
(October 2001, Boot ROM ``4.2.8f1``) specifically included AGP-graphics
Power Mac G4 machines. Contemporary release coverage documents fixes
for Mac OS X startup from local disks, FireWire target disk mode,
network boot and system stability. The update also resets PRAM.

Apple required Mac OS 9.1 or later on a *local writable disk* to run the
4.2.8 updater on a physical machine; running the installer in Mac OS X,
Classic mode or from a CD was not a supported firmware-installation path.
The original Apple download was historically named
``G4_FW_Update_4.2.8.smi.bin``. The present availability of that
historical Apple-hosted URL and whether the installer includes an intact
1 MiB raw ROM payload have **not** been verified. Do not mistake an
updater container, patch or flash programmer for a directly bootable ROM.

The actual Apple Boot ROM and the separate disk-loaded Mac OS ROM are
different boot stages. Apple Open Firmware initializes UniNorth/KeyLargo,
probes PCI, populates the device tree and provides platform FCode
drivers. Apple did not publish the complete Sawtooth firmware source
alongside the Tiger KeyLargo/UniNorth driver sources inspected here.
Neither Apple's updater nor an unverified ROM extraction is embedded
in this QEMU tree.

QEMU instead uses the pinned ``PPC-Firmware`` OpenBIOS fork. It maps a
1 MiB firmware region at ``0xfff00000``, accepts a compatible PowerPC
ELF or raw image, and by default resets execution to ``0xfff00100``.
The OpenBIOS build checks the ELF LOAD segments and whether the legacy
entry address is mapped; an image built for another entry needs an
explicit ``-machine powermac3_1,firmware-entry=...`` override.
Changing to a real Apple image without verifying its reset vector,
load addresses, and board/MMIO assumptions is **not** a display fix.

For a black screen **before OpenBIOS text appears**, first confirm that
the actual ROM passed to ``-bios`` was freshly built, that the QEMU
startup log reports no firmware-load errors, that the ELF covers the
configured reset entry and that OpenBIOS reaches the graphics-console
initialization. Then trace its AGP PCI scan, Rage 128 BAR assignment,
FCode and framebuffer. A screen that goes blank **after** OpenBIOS
or BootX requires a separate Tiger graphics handoff investigation.
Do not silently replace the historical Rage 128 or claim that the
Apple firmware updater was booted.

Historical references:

* https://www.macworld.com/article/163402/firmware.html
* https://leopard-adc.pepas.com/documentation/Hardware/Developer_Notes/Macintosh_CPUs-G4/PowerMac_G4_16Feb00/G4Rev3-84.html
* https://github.com/dingusdev/dingusppc/blob/master/zdocs/developers/openfirmware.md
* https://support.apple.com/en-us/docs/mac/7956

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
