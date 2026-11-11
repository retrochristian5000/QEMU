.. _guest-software-probes:

Guest software compatibility and hardware probes
================================================

Guest software is useful for more than a simple "works" or "does not work"
compatibility list.  Operating systems, drivers, utilities, games, and
applications often probe hardware directly or depend on firmware and device
behaviour that is otherwise easy to overlook.  Those probes can expose gaps in
QEMU's machine and device models.

This documentation records those relationships.  It is inspired by software
and compatibility catalogues maintained by projects such as DOSBox, Wine, and
ScummVM, but adds a hardware-oriented layer appropriate for full-system
emulation.

An entry should distinguish the following evidence states rather than treating
them as interchangeable:

``documented dependency``
  Vendor or contemporary technical documentation explicitly describes the
  hardware, interface, switch, driver, or firmware behaviour.

``observed probe``
  The guest software has been observed accessing or testing a particular
  hardware interface under QEMU or on real hardware.

``inferred hardware path``
  The software behaviour points toward a device or interface, but the complete
  dependency has not yet been established from primary documentation or a
  trace.

``runtime verified``
  The specified software version has been exercised against the specified QEMU
  machine/device configuration and the relevant path completed successfully.

Entries should record, where practical:

* the exact software and version;
* the guest operating environment and QEMU machine type;
* the command, driver option, API, instruction, I/O port, MMIO range, firmware
  service, or other probe involved;
* the historical hardware or firmware path exposed by that probe;
* the QEMU device or machine model responsible for that path;
* source provenance and any uncertainty in the hardware identification;
* the current runtime-validation state and known gaps; and
* a reproducible test procedure when redistributable test media or a user's own
  licensed copy can be used.

A successful entry is not proof that every function of the software or device
is emulated.  Likewise, a software failure is not by itself proof that QEMU is
missing hardware: configuration, timing, firmware, operating-system bugs, and
software defects must be separated before assigning the cause.

QEMU does not distribute proprietary guest software as part of this catalogue.
The entries describe compatibility and diagnostic behaviour only.

x86 and DOS software
--------------------

.. toctree::
   :maxdepth: 1

   msdos-6.22
