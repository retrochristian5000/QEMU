.. include:: ../cpu-models-x86.rst.inc

Legacy Pentium profiles
-----------------------

The fork distinguishes the non-MMX Pentium (P54C) from Pentium with MMX
Technology (P55C). Both include an integrated x87 FPU.

* ``-cpu pentium`` or ``-cpu pentium-v2``: family 5, model 2, stepping 5,
  with MMX disabled.
* ``-cpu pentium_mmx`` or ``-cpu pentium_mmx-v2``: independent P55C
  definition, family 5, model 4, stepping 3, with MMX enabled. Reserved
  CPUID leaf 1 EBX defaults to zero unless later CLFLUSH or HTT features
  are enabled explicitly.
* ``-cpu pentium_mmx-v1``: retains the previous independent P55C
  definition, including its historical CPUID leaf 1 EBX behavior.
* ``-cpu pentium-v1``: historical QEMU P55C compatibility definition,
  retained with the same signature and feature defaults.

The unversioned Pentium alias has intentionally changed. Use the original
versioned definition for existing saved-state or migration configurations
that previously used the MMX-capable Pentium. The independent
``pentium_mmx`` name now resolves to ``pentium_mmx-v2`` in CPU model
discovery. Use ``pentium_mmx-v1`` for configurations saved with the
previous independent profile. Management tools should preserve the
requested versioned name for existing migration configurations.
The CPU profile does not select a chipset or change the machine's RAM,
PCI, ISA or firmware topology.

The original P54C has separate 8 KiB L1 instruction and data caches;
P55C has separate 16 KiB L1 instruction and data caches. These models
still share QEMU's legacy cache metadata and expose CPUID level 1 by
default. The separation does not claim accurate cache timing or
cache geometry reporting. CPU identification is not cycle-accurate
emulation of a particular silicon stepping. Change CPU
profiles only on a powered-off guest, not during saved-state restoration.


The corrected reserved register behavior follows a physical P55C capture
(signature 00000543h, CPUID.1 EBX=0) archived at
https://instlatx64.github.io/InstLatx64/GenuineIntel/GenuineIntel0000543_P55C_CPUID.txt .
The hypervisor feature remains available, and the TSC rate is not changed
by this revision. These changes do not implement a physical cache or
cycle-accurate processor timing.
