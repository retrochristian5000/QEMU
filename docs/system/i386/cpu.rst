.. include:: ../cpu-models-x86.rst.inc

Legacy Pentium profiles
-----------------------

The fork distinguishes the non-MMX Pentium (P54C) from Pentium with MMX
Technology (P55C). Both include an integrated x87 FPU.

* ``-cpu pentium`` or ``-cpu pentium-v2``: family 5, model 2, stepping 5,
  with MMX disabled.
* ``-cpu pentium_mmx`` or ``-cpu pentium-v1``: family 5, model 4,
  stepping 3, with MMX enabled; preserves the previous Pentium definition.

The unversioned Pentium alias has intentionally changed. Use the original
versioned definition for existing saved-state or migration configurations
that previously used the MMX-capable Pentium. CPU identification is not
cycle-accurate emulation of a particular silicon stepping. Change CPU
profiles only on a powered-off guest, not during saved-state restoration.

