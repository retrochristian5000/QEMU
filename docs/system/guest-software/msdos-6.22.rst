.. _guest-software-msdos-622:

MS-DOS 6.22
============

This page records software-visible hardware paths exposed by Microsoft MS-DOS
6.22.  It is not a claim that every MS-DOS component has been runtime-verified
on every QEMU PC machine.

EMM386.EXE and Weitek support
-----------------------------

Software
~~~~~~~~

* Microsoft MS-DOS 6.22
* ``EMM386.EXE``

Probe or option
~~~~~~~~~~~~~~~

Microsoft Knowledge Base article Q78433 documents the ``W=ON`` and ``W=OFF``
EMM386 switches for MS-DOS versions including 6.22.  The documented target is
the Weitek 3167 math coprocessor.  The article also distinguishes the Weitek
interface from Intel x87 coprocessors by describing the Weitek path as
memory-mapped and discusses its interaction with the HMA.

Source:

* `Microsoft Knowledge Base Q78433: Detailed Explanation of EMM386.EXE
  Switches <https://jeffpar.github.io/kbarchive/kb/078/Q78433/>`__

Evidence state
~~~~~~~~~~~~~~

``documented dependency``
  EMM386 has an explicit Weitek-support switch, and the contemporary Microsoft
  documentation identifies the Weitek 3167 and its memory-mapped programming
  path.

``hardware-family bridge``
  The QEMU fork models the Weitek 4167.  Microsoft Q78433 names the 3167, not
  the 4167.  The 4167 model uses the object-code-compatible 3167 programming
  model, so the EMM386 documentation is evidence for the software-visible
  programming family rather than a claim that EMM386's documentation names the
  4167 specifically.

QEMU hardware path
~~~~~~~~~~~~~~~~~~

The fork provides a ``weitek4167`` device and machine configurations that wire
it as a 32-bit local-bus, memory-mapped coprocessor for an i486-class system.
The implementation currently models:

* the ``0xc0000000`` through ``0xc1ffffff`` physical decode aperture;
* the mirrored 64 KiB programming window used for operation decoding;
* the 3167/4167 register and address-decoded instruction programming model;
* Weitek floating-point exception state and IRQ13 routing; and
* firmware-visible presence through the machine/device integration path.

The generic ``isapc`` machine does not contain the coprocessor.  The
``isapc-weitek`` machine and the supported Dell 486 machine profiles instantiate
it and require an i486 CPU.

Current validation state
~~~~~~~~~~~~~~~~~~~~~~~~

``build verified``
  The i386 CI target compiles and smoke-tests the QEMU system emulator with the
  Weitek implementation present.

``guest-runtime verification pending``
  The CI smoke-test does not boot MS-DOS 6.22 or exercise ``EMM386.EXE W=ON``.
  A successful QEMU build therefore must not be reported as proof that the
  EMM386 Weitek path is complete.

Suggested runtime test
~~~~~~~~~~~~~~~~~~~~~~

Using a user's licensed MS-DOS 6.22 media, compare otherwise equivalent i486
configurations with and without the Weitek machine profile.  Record at least:

#. the exact ``CONFIG.SYS`` line used to load ``EMM386.EXE``;
#. behaviour with ``W=OFF`` and ``W=ON``;
#. whether EMM386 reports, reserves, or accesses the expected Weitek memory
   path;
#. any MMIO accesses in the Weitek aperture;
#. IRQ13 activity or exception behaviour if exercised; and
#. whether DOS high-memory configuration changes as documented by the EMM386
   Weitek option.

A failure should be classified before changing the device model.  In
particular, distinguish EMM386 configuration errors, firmware visibility,
physical-address decoding, instruction semantics, interrupt behaviour, and HMA
interaction instead of treating all failures as a generic Weitek error.

Why this entry matters
~~~~~~~~~~~~~~~~~~~~~~

The EMM386 path is an example of guest software revealing a hardware
requirement that may not be obvious from a generic PC machine description.
Following the driver's documented hardware switch led the fork to the Weitek
coprocessor programming interface and ultimately to the 4167 device model.  The
same method can be applied to other guest drivers and applications to discover
missing devices, firmware services, timing assumptions, and compatibility
quirks.

Legacy programmable interrupt controllers
-----------------------------------------

Controller families must be distinguished from acceleration backends.
The 8259-compatible PIC, local APIC, and I/O APIC are different guest-visible
hardware interfaces. The userspace 8259 and KVM in-kernel 8259 are alternative
implementations of the legacy interface, not different physical chip models.

Current machine wiring
~~~~~~~~~~~~~~~~~~~~~~

* The ISA-only 486 profiles, i440FX/PIIX, i440BX/PIIX4 and Q35/ICH9 use
  the shared legacy PC 8259 creation path when their PIC is enabled.
* The userspace model creates two cascaded eight-input controllers with
  master IRQ2 connected to the slave output. The master and slave expose
  the legacy command/data port pairs at 0x20/0x21 and 0xa0/0xa1.
* The shared model combines chip-wide ICW1 LTIM selection with the
  chipset edge/level control register (ELCR) extension at 0x4d0/0x4d1.
  This does not establish that every historical board provides both.
* The separate x86-8086 and x86-8088 machine profiles currently discard ISA
  IRQ inputs; they do not yet provide a functioning legacy PIC. A single
  eight-input, XT-style controller without the AT cascade is a distinct
  candidate for those profiles, not a replacement for the existing AT
  and later PC interrupt routing.

Intel 8259 versus 8259A
~~~~~~~~~~~~~~~~~~~~~~

The original Intel 8259 is an MCS-80/85 controller. Its successor, the
8259A, retains the earlier edge-triggered, non-buffered interface and
adds level-triggered and buffered operation as well as the 8086/8088
interrupt-vector protocol. The original part is therefore not the correct
controller for an IBM PC-compatible x86 interrupt-acknowledge path.

In the MCS-80/85 protocol the controller supplies a CALL instruction
and its two address bytes over three acknowledge cycles. In 8086 mode
the 8259A supplies an interrupt type number on the second acknowledge.
The current QEMU ``pic_read_irq()`` interface returns a vector number
directly; it does not model the MCS-80/85 instruction delivery protocol.

The internal QOM type ``isa-i8259`` is consequently an x86-oriented
8259A-compatible controller with optional-in-principle chipset ELCR
register mapping, not a faithful implementation of the original 8259.
The current PC constructor always assigns ELCR ports to the pair.
The common device class intentionally prevents direct user creation,
because machine code must establish the interrupt routing.

Model names and profile boundaries:

* ``i8259a``: registered internal QOM implementation of the x86-oriented
  8259A-compatible controller. Standalone board wiring without ELCR and
  single-controller topology remain future work.
* ``isa-i8259``: generic ISA 8259-compatible profile, currently a
  board-selected subtype of ``i8259a``. Use when a machine specifies the
  compatible interface rather than a particular Intel chip revision.
  Existing machine defaults and migration state are retained; the name
  does not identify original Intel 8259 silicon.
* ``i8259``: reserved exclusively for the original Intel 8259 model,
  which requires a verified MCS-80/85
  acknowledge interface, edge-only triggering and its own initialization
  semantics. Do not expose a nominal device until those behaviors exist.

Keep chipset ELCR selection separate from the 8259A silicon revision.
The original 8086/8088 machine profiles need a single 8259A-compatible
controller if modeled as XT-style PCs, not an original 8259 merely
because the CPU is an early model.

Primary references:

* Intel, `1978 Component Data Catalog, 8259/8259-5, pp. 12-111ff.
  <https://bitsavers.trailing-edge.com/components/intel/_dataBooks/1978_Intel_Component_Data_Catalog.pdf>`__.
* Intel, `8259A Programmable Interrupt Controller, December 1988,
  order 231468-003, pp. 1 and 4.
  <https://pdos.csail.mit.edu/6.828/2010/readings/hardware/8259A.pdf>`__.

Validation boundaries
~~~~~~~~~~~~~~~~~~~~~

Preserve existing machine defaults and migration state until a specific
board's interrupt-controller wiring and trigger capabilities are established.
Do not infer that ISA alone excludes ELCR or that PCI alone requires an APIC.
For DOS performance testing, distinguish IRQ delivery, interrupt acknowledgement,
end-of-interrupt commands, masked requests, and repeated host CPU wakeups.
In particular, retain IRQ14 and IRQ15 cascade tests for IDE/ATAPI drivers
on AT-compatible systems. The early 16-bit machine PIC gap is not evidence
that it causes a slowdown on the existing 486 or PCI PC profiles.

OAKCDROM.SYS and Oak ATAPI controllers
-------------------------------------

Software and hardware evidence
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The widely distributed Oak Technology real-mode driver identifies itself as
the OTI-91X ATAPI CD-ROM driver, revision D91XV352, copyright 1987-1997.
A recorded DOS 6.22 boot reports programmed I/O and passes the detected
unit to MSCDEX. Microsoft KB Q293185 describes OAKCDROM.SYS as a generic
ATAPI driver distributed with Windows 98.

The OTI-91X banner is evidence of a controller-family association, not
proof that the driver requires an Oak chip or that all versions behave
identically. Dataquest's October 14, 1996 controller comparison identifies
the Oak OTI-910 (9.5x) and OTI-911 (20x) as ATAPI CD-ROM controller chips
with integrated decoders. These are controller ratings, not guaranteed
speeds for complete drives. The earlier OTI-011 is a separate generation:
the NEC CDR-260 used it with pre-standard ATAPI firmware and exhibited
different reset status and identification behavior. Do not transfer those
quirks to the OTI-91X without evidence.

Driver revisions and distribution provenance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Keep the binary revision, filename, package timestamp and distribution
separate. The following are evidence records, not a verified sequence
of binary releases.

* OTI-011: D011V200.SYS, internal revision D011V200, copyright
  1993-1995, package file date 1995-04-28. A third-party archive lists
  MSCDEX.EXE and SETUP.BAT alongside it. A separate OTI011.zip listing
  names revision V110T07 and copyright 1995-1996; the relationship
  between these revisions is unverified.
* OTI-91X: D91XV340.SYS, listed for an Oak 401d entry and a Lite-On
  LTN-244 entry; a Funai 16x driver archive search result also names
  D91XV340. These are OEM provenance leads, not proof of the actual
  controller chip inside those drives. Binary date and banner unverified.
* OTI-91X: D91XV352, confirmed by a recorded MS-DOS 6.22 startup
  (copyright 1987-1997). The log reports programmed I/O, one drive
  and MSCDEX 2.23 on the first boot. Later boots in that report show
  duplicate units in DOSBox-X; this is not a demonstrated QEMU defect.
* Windows 98 First Edition: OAKCDROM.SYS, 41,302 bytes, file timestamp
  1998-05-11, confirmed by Microsoft KB Q185645.
* Windows 98 Second Edition: OAKCDROM.SYS, 41,302 bytes, file timestamp
  1999-04-23, listed by AllBootDisks.
* Windows Me: OAKCDROM.SYS, 41,302 bytes, file timestamp 2000-06-08,
  confirmed by Microsoft KB Q262502.
* Windows 95: Microsoft's Q142943 original startup disk inventory
  omits OAKCDROM.SYS. OEM and later modified boot disks must be treated
  separately rather than attributed to the original distribution.

Equal file sizes do not establish identical bytes. None of the above
distribution copies has been hashed or compared in this audit. Dates
are recorded file timestamps or copyright ranges, not necessarily
driver release dates.

Recovery and comparison procedure:

#. Extract the SYS file from lawfully held OEM or Windows startup media
   into a separate read-only analysis collection, not the VM directory.
#. Record the originating package, filename, file size, timestamp, SHA-256,
   internal revision string and copyright text. Keep one binary per
   verified hash and separate distribution provenance for identical copies.
#. Compare older and later driver revisions with identical QEMU machine,
   optical image, channel, unit and MSCDEX version. Change only one
   factor at a time, and record driver initialization separately from MSCDEX.
#. Capture reset and detection results, PIO mode, number of units,
   packet requests, interrupt completion and warm reboot enumeration
   with the generic and experimental OTI-910 profiles.
#. Keep proprietary binaries outside the source repository. Record
   provenance and reproducible test observations in documentation.

Additional references:

* `OTI-011 D011V200 package listing
  <https://www.driverguide.com/driver/detail.php?driverid=23233>`__.
* `OTI-011 V110T07 archive listing
  <https://www.cdrom-drivers.com/drivers/4/4199.htm>`__.
* `Oak D91XV340 archive listing
  <https://www.cdrom-drivers.com/drivers/13/13257.htm>`__.
* `Lite-On driver archive index
  <https://www.cdrom-drivers.com/companies/600.htm>`__.
* `Microsoft KB Q185645 (Windows 98 startup disk)
  <https://www.betaarchive.com/wiki/index.php?title=Microsoft_KB_Archive/185645>`__.
* `Windows 98 and 98 SE startup disk inventories
  <https://www.allbootdisks.com/disk_contents/98.html>`__.
* `Microsoft KB Q262502 (Windows Me startup disk)
  <https://www.betaarchive.com/wiki/index.php?title=Microsoft_KB_Archive/262502>`__.
* `Microsoft KB Q142943 (Windows 95 startup disk)
  <https://www.betaarchive.com/wiki/index.php?title=Microsoft_KB_Archive/142943>`__.

QEMU audit and validation targets
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The current ``ide-cd`` model uses the generic ``QEMU DVD-ROM`` identity.
In ``hw/ide/atapi.c``, IDENTIFY PACKET DEVICE advertises ATA/ATAPI-4
support and 12-byte packets, while standard INQUIRY returns response
format byte 0x21 and a fixed DVD-ROM product string. These are audit
targets, not established Oak incompatibilities.

Capture the exact driver revision and compare the following on a licensed
DOS image, without modifying the user's VM files:

* ATA device detection, reset status and ATAPI signature;
* IDENTIFY PACKET DEVICE and INQUIRY response fields;
* programmed-I/O packet request and data phases, byte counts and IRQ
  completion, on both primary and secondary IDE channels;
* TEST UNIT READY, REQUEST SENSE, READ CAPACITY and READ TOC with media
  present and absent, and the number of units passed to MSCDEX;
* elapsed time separately for driver initialization and MSCDEX startup.

The experimental ``oti-910`` device now derives from ``ide-cd`` and
shares its ATAPI transport. It advertises CD-ROM only in GET CONFIGURATION,
does not claim DVD or unverified recordable-media capabilities, and rejects
READ DVD STRUCTURE. Cooked image capacity is used as an imperfect CD/DVD
distinction, as in the existing generic model. Its default identification
strings are QEMU-defined, not recovered OEM firmware strings. Existing
``ide-cd`` defaults are unchanged.

Example for an otherwise unoccupied secondary IDE channel::

    -drive if=none,id=oakcd,media=cdrom,format=raw,file=disc.iso
    -device oti-910,drive=oakcd,bus=ide.1,unit=0

The profile is not a complete OTI-910 silicon or firmware emulation.
Exact command support, DMA/PIO modes, reset timing and optical-drive
mechanics remain unverified. No physical speed cap has been introduced.
The driver binary used by the user has not been inspected or run.
The qtest ``/ide/oti-910/profile`` exercises the CD-only profile response
through PIO; build and guest-runtime verification are pending.

References:

* `Microsoft KB Q293185 (archived)
  <https://www.betaarchive.com/wiki/index.php/Microsoft_KB_Archive/293185>`__.
* `Dataquest, Semiconductor Directions in PCs and PC Multimedia Worldwide,
  October 14, 1996, Table 1, p. 6
  <https://archive.computerhistory.org/resources/access/text/2013/04/102723333-05-01-acc.pdf>`__.
* `OS/2 Museum, The Secret History of ATAPI
  <https://www.os2museum.com/wp/the-secret-history-of-atapi/>`__.
* `DOSBox-X issue 1980, recorded OTI-91X driver startup (2020)
  <https://github.com/joncampbell123/dosbox-x/issues/1980>`__.
