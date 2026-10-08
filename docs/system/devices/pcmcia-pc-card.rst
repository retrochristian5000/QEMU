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

The fork now contains a reusable 16-bit PC Card bus and abstract card class
(``hw/pcmcia/pcmcia.c``), an Intel 82092AA PCI-to-PCMCIA bridge
(``-device i82092aa``), and an initial card profile
(``-device usr-worldport-v34,bus=pcic.0`` with an 82092AA named
``id=pcic``).  The bridge provides the PCI identity/class, BAR0 ExCA
index/data interface, one-, two- and four-socket straps, per-socket
``0x40`` register banks, Intel's ``0x84`` identification value,
PCICON controls, and migration state.

The core forwards attribute, common-memory and I/O accesses through a card
model.  Its generic CIS reader places logical tuple bytes on even attribute
addresses; cards with their own layout can override attribute reads.  The
bridge translates host I/O and memory windows into card address spaces,
honors the ExCA I/O width bit for 8-bit versus 16-bit transactions, reports
insertion/removal through card-detect and CSC bits, and aggregates card and
enabled CSC interrupts onto PCI INTx.  Its windows and
card-generated interrupts now require socket output power, a selected Vcc and
a released reset.  Mechanical card detect remains visible without power;
READY is not asserted while the card is unpowered or held in reset.

QOM device and bus type names
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following QOM names are stable guest-configuration identifiers, not
interchangeable labels:

* ``pcmcia-bus`` is the concrete 16-bit PC Card bus type derived from
  QEMU's ``bus`` base class.  Each socket has capacity for **one** card.
* ``pcmcia-card`` is the **abstract** device type derived from ``device``;
  it cannot be instantiated directly by ``-device``.
* ``i82092aa`` is a PCI device type derived from ``pci-device``,
  representing the socket controller, not a PC Card.
* ``usr-worldport-v34`` is a concrete ``pcmcia-card`` subclass.

For example, ``-device i82092aa,id=pcic,sockets=2`` exposes socket buses
``pcic.0`` and ``pcic.1``.  A WorldPort card can be attached to either
bus using ``-device usr-worldport-v34,bus=pcic.1``, but a second card on
that occupied socket is rejected as a full bus.  The QOM type names are not
the same as these dynamically assigned bus *instance* names.

This remains **16-bit PC Card** support, not a 32-bit CardBus implementation.
The WorldPort CIS is explicitly reconstructed from product characteristics,
not claimed as a recovered retail CIS ROM.  Detailed socket power-switch
timing, complete voltage and IRQ routing, and additional card families still
need their own validation.

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

Intel 82092AA PCI profile
-------------------------

The Intel 82092AA PPEC is a PCI-to-PCMCIA controller for 16-bit PC Cards, not a
CardBus bridge.  QEMU models it as a conventional PCI function with Intel
vendor/device ID ``8086:1221`` and PCI class ``0x0605`` (PCMCIA bridge).

The ``sockets`` property selects the documented hardware strap profile:

* ``sockets=1`` maps PCICON bits 2:1 to ``01``;
* ``sockets=2`` is the default and maps them to ``00``; and
* ``sockets=4`` maps them to ``10``.

BAR0 is a four-byte PCI I/O aperture.  Only offsets ``BASE+0`` and ``BASE+1``
are implemented as the ExCA index/data pair; the remaining two bytes are not
invented as registers.  Each socket occupies a ``0x40``-byte indexed bank.

The 82092AA implementation now connects its socket buses to the reusable
16-bit PC Card layer and supports host-window forwarding.  ExCA POWER and
INTCTL control card READY and access, while CSCINT gates card-status-change
PCI interrupts; reading CSC acknowledges pending changes.  This is a
functional baseline rather than a claim of cycle-accurate power sequencing
or complete 82365-compatible register behavior.

The current ``i82092aa`` device represents PPEC PCI function 0 only.  The same
physical 82092AA also exposes PCI function 1 as an Enhanced IDE controller
with device ID ``8086:1222`` and its own IDE BAR/configuration register set.
That function remains unimplemented and must not be approximated by silently
attaching an unrelated generic IDE controller to the PCMCIA function.

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

#. **Implemented baseline:** reusable 16-bit PC Card core, the 82092AA PCI
   controller, a reconstructed WorldPort serial modem card, and QTests for
   socket profiles, CIS/attribute access, window translation, 8/16-bit I/O
   transfers, reset/power gating and CSC reporting.
#. **Outstanding:** add an Intel 82365SL family ISA controller, beginning with
   its documented Revision 1 identification, ExCA control/IRQ behavior and
   two I/O/five memory windows.
#. **Outstanding:** add separate 82365SL Revision 0 and 82365SL-DF profiles
   after verifying their differing identification and voltage/power semantics.
#. **Outstanding:** adapt a historical Microdrive/CompactFlash PC Card model
   and add storage-specific window, register, interrupt and migration tests.
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
* Intel *82092AA PCI-to-PCMCIA Enhanced IDE Controller (PPEC)*,
  order 290511-001, December 1993, for the PCI identity, BAR0 index/data
  aperture, PCICON socket straps and ExCA-compatible register behavior.
* The Linux ``i82092`` driver as an independent software control for socket
  probing, ExCA register use and PCI interrupt routing.
* Texas Instruments PCI CardBus controller documentation, especially PCI1510
  and PCI1520, for the relationship between CardBus bridging and the retained
  82365-compatible ExCA register path.
* QEMU commit ``de63376387bada2da5f5aee778bc07eb1d897c16`` (October 2024),
  which removed the unused generic PCMCIA subsystem and explicitly documented
  that it could be resurrected for future PCMCIA work.
