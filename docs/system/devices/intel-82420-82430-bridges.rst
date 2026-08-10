Intel 82420/82430 PCIset bridge family
=======================================

The Intel 82420/82430 PCIset generation used a related group of bridge and
system-I/O components to connect PCI systems to ISA or EISA expansion buses.
This page records the hardware relationships separately from QEMU's software
composition so that similarly named devices are not mistaken for the same
piece of silicon.

The family is useful as an implementation roadmap because several members can
share QEMU infrastructure even though their guest-visible identities and
hardware roles differ.

Hardware family map
-------------------

The bridge components divide into an ISA path and an EISA path::

    Intel 82420/82430 PCIset bridge components
    |
    +-- ISA path
    |   +-- 82378IB  System I/O (SIO)
    |   +-- 82378ZB  System I/O (SIO)
    |   `-- 82379AB  System I/O APIC (SIO.A)
    |
    `-- EISA path
        +-- 82374EB  EISA System Component (ESC) --+
        |                                            +-- used as a pair
        +-- 82375EB  PCI-EISA Bridge (PCEB) --------+
        |
        +-- 82374SB  EISA System Component (ESC) --+
        |                                            +-- used as a pair
        `-- 82375SB  PCI-EISA Bridge (PCEB) --------+

The 82374 ESC and 82375 PCEB are complementary chips.  The PCEB supplies the
PCI-to-EISA data path, protocol translation, buffering, address decoding and
PCI arbitration.  The ESC supplies the EISA/ISA system-control side, including
DMA, interrupt and timer functions, EISA arbitration, PIRQ steering and other
legacy-system support.

The 82378/82379 devices are PCI-to-ISA alternatives from the same bridge
component generation.  They are not a physical 82375-plus-82374 stack.

Part inventory and QEMU status
------------------------------

.. list-table::
   :header-rows: 1
   :widths: 16 27 25 32

   * - Part
     - Hardware role
     - Important distinction
     - WHP QEMU status
   * - 82374EB
     - EISA System Component (ESC)
     - Baseline EISA system-control member paired with 82375EB
     - ``hw/dma/i82374.c`` exists, but models only a small enhanced-DMA slice
       rather than a complete ESC
   * - 82374SB
     - EISA System Component (ESC)
     - SB variant; notably includes Intel SMM/system-power-management behavior
     - No distinct model
   * - 82375EB
     - PCI-EISA Bridge (PCEB)
     - PCI/EISA master/slave bridge paired with 82374EB
     - Missing
   * - 82375SB
     - PCI-EISA Bridge (PCEB)
     - SB companion for the 82374SB; EB and SB behavior must not be assumed
       register-identical
     - Missing
   * - 82378IB
     - PCI-to-ISA System I/O (SIO)
     - Earlier SIO revision; does not implement the later PIRQ steering
     - No distinct model
   * - 82378ZB
     - PCI-to-ISA System I/O (SIO)
     - Later SIO revision with PIRQ steering
     - ``hw/isa/i82378.c`` is a partial model and advertises PCI revision
       ``0x03``, which is in the ZB-class revision range
   * - 82379AB
     - PCI-to-ISA System I/O APIC (SIO.A)
     - Multiprocessor-oriented variant with an I/O APIC and different DMA
       capabilities from 82378ZB
     - Missing

QEMU composition is not hardware genealogy
-------------------------------------------

The current ``i82378`` model creates an ISA bus, two 82C59-compatible PICs, an
82C54-compatible PIT and a PC speaker, then instantiates QEMU's ``i82374``
object to provide DMA support.

That composition is an implementation reuse decision.  A real 82378 does not
contain a separate 82374 chip.  On real systems the 82378/82379 ISA path and
the 82374-plus-82375 EISA path are alternative members of the broader bridge
family.  Future refactoring should preserve this distinction in device names
and documentation even if internal helper code is shared.

Current 82374 coverage
----------------------

``hw/dma/i82374.c`` currently:

* creates the ISA DMA core through the existing i8257/82C37-compatible helper;
* exposes an I/O window at a configurable base, defaulting to ``0x400``;
* provides placeholders for scatter/gather interrupt, command, status and
  descriptor registers; and
* leaves most of those enhanced-DMA register semantics unimplemented.

The physical 82374 ESC is substantially larger.  Intel documents EISA/ISA bus
control, enhanced DMA and scatter/gather, interrupt controllers, timer
functions, EISA arbitration, four PCI interrupt inputs with programmable
routing, APIC support, X-bus peripheral support, NMI/error handling and BIOS
interface logic.  The 82374SB adds system-power-management/SMM facilities.

Consequently the existing ``i82374`` type should be treated as a partial DMA
building block, not evidence that QEMU already has a complete 82374EB ESC.

Current 82378 coverage
----------------------

``hw/isa/i82378.c`` identifies itself as Intel PCI device ``0x0484`` with
revision ``0x03`` and creates the basic ISA compatibility devices described
above.  Revision values whose low nibble is at least 3 correspond to the
82378ZB/82379AB generation rather than the earlier 82378IB.

The model does not yet provide the full configuration-register and system-I/O
behavior of the real ZB part.  In particular, the real 82378ZB implements four
PIRQ route-control registers.  This makes PIRQ steering a small, high-value
coherency fix for the existing model before adding more variants.

Existing reusable infrastructure
--------------------------------

Several prerequisites already exist in the WHP fork:

* ``hw/isa/eisa-bus.c`` provides an EISA bus type and the standardized
  slot-identification/control layer;
* the 82C37/i8257 DMA, 82C59 PIC and 82C54/i8254 timer cores already exist;
* QEMU already has I/O APIC infrastructure for a future 82379AB model; and
* later Intel PIIX/ICH devices use closely related PIRQ routing semantics,
  providing an implementation reference without making those later chips
  members of this family.

The EISA bus model intentionally does not synthesize enhanced EISA DMA,
arbitration or burst timing.  Those functions belong in the bridge/system
components rather than in the generic bus layer.

Implementation roadmap
----------------------

A useful order is:

#. Make the existing ``i82378`` model coherent with its advertised ZB-class
   revision by implementing the 82378ZB PIRQ route registers and other small
   software-visible configuration gaps.
#. Add an ``82378IB`` profile from the same core with a pre-ZB revision and no
   PIRQ steering.  This is a relatively small variant once the common SIO
   state is separated from revision-specific behavior.
#. Add an ``82379AB`` profile using the SIO core plus QEMU's existing I/O APIC
   facilities, while preserving its documented DMA differences.
#. Implement an ``82375EB`` PCEB that owns the PCI-facing bridge function and
   creates or attaches the existing EISA bus.  This unlocks a historically
   correct PCI-to-EISA topology.
#. Expand ``i82374`` from its DMA-only role into an actual 82374EB ESC model,
   reusing the existing DMA/PIC/timer helpers and sharing PIRQ code where the
   hardware semantics match.
#. Add the 82374SB/82375SB pair as explicit variants after the EB baseline is
   stable, rather than hiding SB-specific power-management behavior behind
   the EB identity.

This order gives useful intermediate devices and avoids having the difficult
parts of full EISA timing block easier identity and routing improvements.

Machine-model opportunities
---------------------------

An 82375 model has value beyond early Intel x86 systems.  QEMU's Alpha
``dp264`` source already records that some PCI-based Alpha systems shipped
with an Intel 82375 PCI-EISA bridge, while the current generic Alpha machine
uses an 82378 for simplicity.  A PCEB/ESC implementation therefore creates a
path toward more accurate Alpha EISA configurations as well as Intel
82420/82430-era x86 machines.

The WHP fork also has generic EISA-capable 486 machine work in ``hw/i386/isapc.c``.
That generic EISA bus must not by itself be taken as evidence that a particular
486 machine used Intel's 82374/82375 pair; chipset selection still requires
machine-specific evidence.

Primary reference set
---------------------

The following Intel documents define the family and should be preferred when
implementing guest-visible behavior:

* *82374EB/82374SB EISA System Component (ESC)*, Intel order 290476-004,
  March 1996.
* *82375EB/82375SB PCI-EISA Bridge (PCEB)*, Intel order 290477-004,
  March 1996.
* *82378 System I/O (SIO)*, Intel order 290473-004, December 1994.  Earlier
  82378IB material appears as order 290473-002, April 1993.
* *82378ZB System I/O (SIO) and 82379AB System I/O APIC (SIO.A)*, Intel order
  290571-001, March 1996.
* *Intel 82374/5 EB/SB EISA Bridge PCIset Specification Update*, Intel order
  297735, April 1997 revision set.
* *82420/82430 PCIset ISA and EISA Bridge*, Intel bridge-component literature
  describing the ISA and EISA branches together.

When secondary operating-system sources are useful, the Linux x86 PIRQ-router
work is a valuable cross-check because it distinguishes 82378IB from
82378ZB/82379AB by PCI revision and records the shared PIRQ routing semantics
used by later PIIX/ICH devices.
