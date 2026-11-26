.. include:: ../cpu-models-x86.rst.inc

Legacy Pentium profiles
-----------------------

The fork distinguishes the non-MMX Pentium (P54C) from Pentium with MMX
Technology (P55C). Both include an integrated x87 FPU.

* ``-cpu pentium`` or ``-cpu pentium-v2``: family 5, model 2, stepping 5,
  with MMX disabled.
* ``-cpu pentium_mmx`` or ``-cpu pentium_mmx-v1``: independent P55C
  definition, family 5, model 4, stepping 3, with MMX enabled.
* ``-cpu pentium-v1``: historical QEMU P55C compatibility definition,
  retained with the same signature and feature defaults.

The unversioned Pentium alias has intentionally changed. Use the original
versioned definition for existing saved-state or migration configurations
that previously used the MMX-capable Pentium. The independent
``pentium_mmx`` name now resolves to ``pentium_mmx-v1`` instead of
``pentium-v1`` in CPU model discovery; management tools should preserve
the requested versioned name for existing migration configurations.
The CPU profile does not select a chipset or change the machine's RAM,
PCI, ISA or firmware topology.

The original P54C has separate 8 KiB L1 instruction and data caches;
P55C has separate 16 KiB L1 instruction and data caches. These models
still share QEMU's legacy cache metadata and expose CPUID level 1 by
default. The separation does not claim accurate cache timing or
cache geometry reporting. CPU identification is not cycle-accurate
emulation of a particular silicon stepping. Change CPU
profiles only on a powered-off guest, not during saved-state restoration.

