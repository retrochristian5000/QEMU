PCMCIA, PC Card and CardBus controller families
================================================

Portable computers used several generations of removable-card interfaces that
are often grouped together under the name ``PCMCIA``.  They should not be
collapsed into one QEMU bus model.  The early 16-bit PC Card interface and the
later 32-bit CardBus interface share a connector and some software-visible
compatibility registers, but their host-bus semantics are different.

This page records the controller families and the QEMU implementation boundary
so that laptop machine models can select a historically appropriate socket
controller instead of attaching a generic card slot.

Terminology and generations
---------------------------

The first useful split is::

    PC Card removable-card ecosystem
    |
    +-- 16-bit PC Card / PCMCIA Release 2.x
    |   |
    |   +-- ISA-like I/O and memory transactions
    |   +-- attribute memory containing CIS tuples
    |   +-- common memory
    |   +-- card I/O space
    |   `-- ExCA / Intel 82365-compatible socket-controller register model
    |
    `-- 32-bit CardBus
        |
        +-- PCI-like 32-bit card bus
        +-- PCI-to-CardBus bridge configuration space
        +-- CardBus bus-master transactions
        `-- legacy ExCA-compatible register window for 16-bit cards

``PCMCIA`` is commonly used for the 16-bit generation.  Later specifications
call both 16-bit and 32-bit devices PC Cards, with the 32-bit form called
CardBus.  A controller that accepts both kinds of card therefore needs both a
16-bit PC Card path and a CardBus/PCI path rather than a widened version of the
same callbacks.

16-bit ExCA controller family
-----------------------------

The Intel 82365SL PC Card Interface Controller is the most useful baseline for
an x86 laptop implementation.  Its register interface became the compatibility
model used by a large group of later PC Card controllers.

The Intel identities distinguish at least three useful profiles:

* 82365SL Revision 0, identification value ``0x82``;
* 82365SL Revision 1, identification value ``0x83``; and
* 82365SL-DF, identification value ``0x84``.

The DF member extends the original controller generation, notably for later
card-voltage requirements.  It should be represented as a profile of a common
82365 core rather than by duplicating the socket/window implementation.

The surrounding compatibility ecosystem includes controllers that operating
systems intentionally drive through an 82365-style register interface.  Useful
families to research as follow-on profiles include:

* Cirrus Logic CL-PD6710 and CL-PD6720.  CL-PD6722 is another closely related
  part seen by 82365-compatible operating-system drivers;
* Vadem VG-365, VG-465 and VG-468, with later VG-469-era extensions requiring
  separate verification;
* Fujitsu MB86301;
* Chips and Technologies F8680;
* Ricoh RF5C296/RF5C396-era controllers; and
* IBM PCIC-compatible controllers, which have their own identification values.

These devices should not automatically be declared register-identical.  The
common ExCA window is a reuse opportunity, while vendor-specific identification,
power switching, voltage control and extension registers remain per-family
behavior.

Intel 82365 register structure
------------------------------

The classic 82365SL interface occupies an index/data I/O-port pair.  A socket is
selected by the high bits of the indexed register number, after which a
per-socket register bank controls card state and host mappings.

Important software-visible groups include:

* identification and interface-status registers;
* socket power and reset control;
* card-status-change reporting;
* card-status-change interrupt routing;
* card IRQ routing and I/O-vs-memory card selection;
* two host I/O windows; and
* five host memory windows, each of which can map card common or attribute
  memory.

The controller therefore owns address translation.  A PC Card object should
not map itself directly into the machine's ISA memory or I/O address spaces.
The socket controller decides which enabled host windows reach which card
space.

The CIS belongs to the card
---------------------------

A 16-bit PC Card exposes Card Information Structure (CIS) tuples in attribute
memory.  This is card identity/configuration data and belongs to the emulated
card, not to the laptop socket controller.

A reusable card interface consequently needs at least:

* attribute-memory reads and writes;
* common-memory reads and writes;
* card-I/O reads and writes;
* card IRQ/READY signaling;
* insertion/ejection state; and
* CIS data owned by the card model.

This division lets the same modem, network, storage or memory card be inserted
into different historical socket controllers.

Former QEMU PCMCIA subsystem
----------------------------

Upstream QEMU previously contained a small generic PCMCIA subsystem.  Its
abstract ``pcmcia-card`` type exposed card attach/detach hooks, CIS data, and
callbacks for attribute, common-memory and I/O accesses.  The PXA2xx PC Card
controller used those callbacks and provided separate common, attribute and
I/O memory regions plus card IRQ and card-detect signaling.

Upstream removed that subsystem in October 2024 after removing the PXA2xx
machines that were its only active users.  The removal explicitly noted that
other surviving machine families still had unimplemented PCMCIA hardware and
that the subsystem could be resurrected when needed.

That history is useful for the WHP fork: the old abstraction is a starting
point, not a specification.  It should be restored only after correcting two
important limitations:

* its ``PCMCIA/Cardbus`` comment overstated the abstraction; the callbacks
  model a 16-bit PC Card, not a 32-bit CardBus secondary PCI bus; and
* socket-controller policy should be separated cleanly from the card object so
  ISA 82365-style controllers, embedded controllers and later CardBus bridges
  can share the card layer.

Current WHP QEMU status
-----------------------

The current fork has no generic PCMCIA/CardBus subsystem and no x86 PC Card
socket controller.

There are nevertheless useful surviving clues:

* ``hw/arm/strongarm.h`` still defines two PCMCIA chip-select apertures at
  ``0x20000000`` and ``0x30000000``;
* ``hw/arm/strongarm.c`` still lists ``PCMCIA handling`` as unimplemented;
* upstream's pre-removal subsystem gives us a known QOM/card-interface starting
  point; and
* QEMU's PCI bridge infrastructure can support a later true CardBus bridge
  rather than forcing CardBus through the 16-bit PCMCIA interface.

The StrongARM references are evidence that PC Card support is useful beyond x86
laptops.  They are not evidence that an Intel 82365SL should be attached to a
StrongARM machine; each board still needs its real controller identified.

CardBus generation
------------------

CardBus adds a 32-bit PCI-like card bus while retaining compatibility support
for 16-bit PC Cards.  A CardBus controller is therefore best represented as a
PCI bridge with a secondary CardBus bus plus an ExCA-compatible legacy path for
16-bit cards.

Texas Instruments provides a well-documented progression of PCI-to-CardBus
controllers useful for future profiles.  Representative parts include:

* PCI1211, single-socket CardBus;
* PCI1225, dual-socket CardBus;
* PCI1251B, dual-socket CardBus with additional multimedia support;
* PCI1410A and PCI1510, single-socket controllers;
* PCI1420 and PCI1520, dual-socket controllers; and
* later PCI145x/44xx families, some of which integrate additional functions
  such as IEEE 1394.

The PCI1510 documentation is a particularly useful architectural control: it
supports 5-V/3.3-V 16-bit PC Cards and 3.3-V CardBus cards, exposes
ExCA-compatible registers, and is register-compatible with the Intel 82365SL
and 82365SL-DF for the legacy card path.  The PCI1520 applies the same general
architecture to two independent sockets.

This backward compatibility does not make the TI parts members of the Intel
82365 silicon family.  It means that the 16-bit socket register core can be
shared where the documented semantics match while the PCI/CardBus bridge,
power-management and vendor-extension logic remains controller-specific.

Socket power is hardware too
----------------------------

PC Card power control should not be reduced to a boolean ``inserted`` flag.
Controllers select socket power and, on early PCMCIA systems, programming
voltage.  Real notebook designs frequently use companion analog power switches.

Period Analog Devices/Maxim documentation, for example, lists the MAX613/MAX614
as logic-compatible with Intel 82365SL/82365SL-DF, Vadem VG-365/VG-465/VG-468,
and Cirrus Logic CL-PD6710/CL-PD6720 controllers.  The MAX780 family similarly
lists Intel 82365SL-DF, Fujitsu MB86301, Chips and Technologies F8680 and
Cirrus CL-PD6720.

For QEMU this suggests a useful boundary:

* the socket controller owns guest-visible power-control registers;
* the card object observes whether appropriate VCC/VPP state is present; and
* a board-specific companion power-switch model is only required when its
  behavior is independently software-visible or materially affects timing and
  fault behavior.

Do not invent a universal PCMCIA power-switch chip for all laptops.

Useful card models
------------------

Once the socket layer exists, card models can be added independently.  Good
historical categories are:

* SRAM/flash memory cards;
* ATA/CompactFlash storage and Microdrive-style cards;
* serial modem cards;
* Ethernet adapters;
* SCSI host adapters; and
* wireless-network cards for later CardBus-era machines.

The old QEMU tree included a PCMCIA Microdrive/CompactFlash-style storage card.
Resurrecting and adapting that model after the generic PC Card core would give
an early controller an immediately useful guest-visible card without requiring
network or modem emulation first.

Implementation roadmap
----------------------

A conservative implementation order is:

#. Restore a modernized 16-bit PC Card core from the former upstream QEMU
   subsystem.  Keep CIS, attribute/common/I/O callbacks and card IRQ state in
   the card layer, but do not label this core CardBus.
#. Add an Intel 82365SL family ISA socket controller.  Start with the documented
   Revision 1 identity, index/data registers, power/reset/status logic, IRQ
   routing and the two I/O/five memory windows.
#. Add explicit 82365SL Revision 0 and 82365SL-DF profiles once their differing
   identification and voltage/power semantics are represented.
#. Restore/adapt the former Microdrive/CompactFlash PC Card model as an initial
   inserted card and add controller/card qtests for CIS reads, window mapping,
   insertion/ejection and interrupt routing.
#. Add one well-documented ExCA-compatible clone family, preferably Cirrus
   CL-PD67xx, by sharing the 82365 core and implementing only verified
   extensions and power differences.
#. Only then introduce a CardBus/Yenta-style PCI bridge abstraction.  Model a
   real CardBus controller, such as an early TI PCI11xx/12xx part, with a true
   secondary PCI-like CardBus bus plus the shared legacy ExCA path.
#. Wire controllers into individual laptop machine profiles only after the
   controller, socket count, IRQ wiring, power hardware and card-detect wiring
   are established for that machine.

This sequence produces useful 16-bit laptop PC Card emulation early without
blocking on the substantially larger CardBus problem.

Machine-model opportunities
---------------------------

PCMCIA support is a prerequisite for meaningful emulation of many notebook and
palmtop systems because firmware and operating systems often detect and program
the socket controller even when no card is inserted.

For future x86 laptop work, the machine profile should therefore record:

* exact socket-controller part and revision;
* number of physical sockets;
* ISA, PCI or integrated host attachment;
* controller index/data or PCI configuration address;
* card IRQ and card-status-change routing;
* socket VCC/VPP power-switch hardware;
* BIOS/Card Services assumptions; and
* whether the slot is PC Card 16 only or CardBus-capable.

A generic ``laptop has PCMCIA`` flag is not enough to establish any of these
properties.

Reference set
-------------

Useful implementation references include:

* Intel *82365SL PC Card Interface Controller (PCIC)*, order 290423-002,
  January 1993; NetBSD's ``i82365reg.h`` records its register definitions and
  identifies this document as its source.
* The NetBSD ``i82365`` controller implementation, which distinguishes Intel
  82365SL Revision 0, Revision 1 and 82365SL-DF identities and probes several
  compatible controller families.
* Analog Devices/Maxim MAX613/MAX614 and MAX780-series data sheets, whose
  compatibility lists provide period evidence for the 82365-compatible
  controller ecosystem and companion socket-power hardware.
* Texas Instruments PCI CardBus controller documentation, especially PCI1510
  and PCI1520, for the relationship between CardBus bridging and the retained
  82365-compatible ExCA register path.
* QEMU commit ``de63376387bada2da5f5aee778bc07eb1d897c16`` (October 2024),
  which removed the unused generic PCMCIA subsystem and explicitly documented
  that it could be resurrected for future PCMCIA work.
