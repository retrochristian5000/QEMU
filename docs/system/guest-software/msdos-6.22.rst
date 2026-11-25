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
