Storage controller modularity
=============================

Storage controllers should be modeled as hardware families rather than copied
per board or per closely related chip.  The goal is the same as the reusable
AC'97 codec work: shared protocol/chip behavior belongs in one core, while bus
attachment, board wiring, and verified chip-generation differences remain
small wrappers or profiles.

Existing patterns
-----------------

Several storage paths already demonstrate the intended structure:

* IDE/ATA has a shared core and thin controller/front-end implementations.
* AHCI separates the reusable AHCI core from PCI and sysbus-style attachment.
* ESP SCSI separates the ESP core from ``esp-pci``.
* NCR53C710 separates the controller implementation from the LASI wrapper.
* MPT SAS already separates configuration-page and endian helpers.
* vhost SCSI has a shared common layer for the kernel and vhost-user variants.

These should be preferred as patterns over introducing a second generic SCSI
command layer.  QEMU's existing ``SCSIBus`` and SCSI device code already own
common target/request semantics.

Family boundary rule
--------------------

A controller family module should own register semantics, command engines,
request tracking, DMA state, reset behavior, and migration state that are truly
shared by the silicon family.  A wrapper should own attachment-specific details
such as PCI IDs/BARs, sysbus regions, board IRQ routing, or machine wiring.

Do not copy a controller merely to add another chip revision.  Add an explicit
variant/profile description and gate only differences supported by hardware
documentation.  Likewise, do not force unrelated controllers through a common
abstraction merely because they all transport SCSI commands.

LSI/NCR 53C8xx
--------------

The former ``lsi53c895a.c`` source already implemented both the 53C810 and the
53C895A.  It is therefore named ``lsi53c8xx.c`` as a family module.  The public
QOM names remain ``lsi53c810`` and ``lsi53c895a`` for compatibility.

This naming boundary is the first step toward explicit per-chip profiles.  The
current implementation still notes that the 53C810 accepts behavior from later
53C8xx evolutions.  Future accuracy work should correct those differences in
the common family core rather than creating a second copied SCRIPTS engine.

Migration and compatibility
---------------------------

Refactors must preserve QOM device names, PCI identity, migration layout, and
machine-visible behavior unless a separately reviewed compatibility change is
intended.  File/module boundaries are free to change; guest-visible hardware
contracts are not.
