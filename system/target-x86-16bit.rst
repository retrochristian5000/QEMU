Original 16-bit x86 System emulator
-----------------------------------

QEMU provides a dedicated ``qemu-system-x86`` executable for original
16-bit Intel x86 software.  It is intentionally separate from the i386 and
x86_64 system emulators: only the ``8086`` and ``8088`` CPU models are
available, and only TCG acceleration is supported.

Machines and CPU models
~~~~~~~~~~~~~~~~~~~~~~~

``x86-8086``
  The default machine.  It uses the ``8086`` CPU model and records a 16-bit
  external data bus.

``x86-8088``
  Uses the ``8088`` CPU model and records an 8-bit external data bus.

The CPU exposes the read-only QOM property
``external-data-bus-width``.  A machine rejects the other CPU model rather
than silently changing its bus profile.

Both machines provide one CPU, up to 640 KiB of RAM at physical address
zero, a generic ISA I/O bus, and COM1.  They are small execution platforms,
not models of the IBM PC or IBM PC/XT.  In particular, they do not include a
PIC, PIT, DMA controller, keyboard controller, display adapter, disk
controller, or PC-compatible firmware interfaces.

Firmware
~~~~~~~~

An explicit raw firmware image is required.  The image may be at most 64 KiB
and is right-aligned in the ROM window at ``0xf0000``::

  qemu-system-x86 -machine x86-8086 -bios firmware.bin \
      -display none -serial stdio

The reset vector is fetched from physical address ``0xffff0`` using the
original ``F000:FFF0`` reset state.  A20 is disabled at reset.

Compatibility scope
~~~~~~~~~~~~~~~~~~~

The target implements the architectural differences needed by original
8086/8088 code, including the decremented value stored by ``PUSH SP`` and
opcode ``0x0f`` as ``POP CS``.  Encodings introduced with the 80186 or 80386,
including opcodes ``0x60`` through ``0x6f``, ``0xc0``, ``0xc1``, ``0xc8``,
``0xc9``, and the FS, GS, operand-size, and address-size prefixes, raise the
invalid-opcode exception.  This is a deterministic compatibility policy; it
does not claim to reproduce every undocumented result of original silicon.

The implementation is instruction-accurate rather than cycle-accurate.  It
does not model the prefetch queue, bus-cycle timing, 8087 timing, or complete
undocumented instruction behavior.  The 8086 and 8088 therefore differ in
their declared external bus profile, not in instruction timing.
