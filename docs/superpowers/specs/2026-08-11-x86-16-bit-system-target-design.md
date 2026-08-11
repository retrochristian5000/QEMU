# 16-bit x86 system target design

## Goal

Add a distinct `qemu-system-x86` system emulator for the original 16-bit
x86 family.  Its first supported processors are the Intel 8086 and 8088.
The existing `qemu-system-i386` and `qemu-system-x86_64` programs retain
their current behavior and CPU-model lists.

## Target boundary

The new `x86-softmmu` build target reuses the mature i386 TCG translator and
system support through `TARGET_BASE_ARCH=i386`.  It also defines a dedicated
`TARGET_X86_16BIT` contract.  That contract is not an alias: it controls CPU
model registration, reset state, opcode decoding, default CPU selection, and
the machines exposed by the new executable.

`TARGET_LONG_BITS` remains 32.  This is an internal translator word size, not
a claim that the guest CPU has 32-bit registers.  Setting it to 16 would break
shared TCG assumptions without improving architectural fidelity.  The decoder
keeps the guest in 16-bit operand and address modes by rejecting later prefix
and opcode families.

## CPU models

The target exposes `8086` and `8088` CPU models.  Both implement the original
8086 instruction generation.  They differ through a read-only
`external-data-bus-width` property: 16 bits for the 8086 and 8 bits for the
8088.  QEMU is not cycle-accurate, so the bus-width distinction affects model
identity and machine compatibility, not instruction timing.

The models have no CPUID feature leaves and no later x86 feature bits.  Concrete
286, 386, 486, Pentium, and modern models are not registered in the 16-bit
target.  Conversely, the new 8086/8088 models are not added to the existing
i386 or x86_64 executables.

## Initial architectural semantics

The first implementation covers the boundaries most likely to turn a nominal
8086 into a disguised later CPU:

- Reset starts at physical `0xffff0` using the 8086 `f000:fff0` segment base.
- A20 is disabled at reset, preserving the 20-bit address wrap.
- `PUSH SP` stores the decremented SP value used by the original 8086/8088.
- Opcode `0x0f` implements the original `POP CS` instruction.
- 80186 additions (`0x60`-`0x6f`, `0xc0`, `0xc1`, `0xc8`, and `0xc9`) are
  rejected.
- Later FS/GS, operand-size, and address-size prefixes are rejected.
- FS/GS encodings in segment-register moves are rejected.

For deterministic containment, instructions introduced after the selected
generation raise QEMU's invalid-opcode exception.  Real 8086 behavior for
unassigned byte patterns was not uniformly specified; this policy prevents
later instructions from silently executing and is explicitly a compatibility
choice, not a claim about every undocumented silicon behavior.

This slice does not claim cycle accuracy, prefetch-queue timing, 8087
co-processor timing, or complete undocumented-opcode behavior.

## Machines

Two minimal machines are exposed:

- `x86-8086`: 8086 CPU with a 16-bit external data bus.
- `x86-8088`: 8088 CPU with an 8-bit external data bus.

Both are single-CPU, TCG-only boards with up to 640 KiB of RAM, a 64 KiB ROM
window at `0xf0000`, an ISA I/O bus, and one ISA serial port.  They deliberately
do not reuse `isapc`, because that machine contains AT-era RTC, keyboard, IDE,
and firmware assumptions.  They are generic original-x86 bring-up boards, not
claims of complete IBM PC 5150 or XT reproduction.

The machine requires `-bios FILE`.  The firmware may be up to 64 KiB and is
right-aligned in the ROM window so its reset vector ends at physical `0xfffff`.
Requiring explicit 8086-compatible firmware prevents the existing 386/486-era
SeaBIOS image from being selected silently.

## Testing

The build and tests must demonstrate behavior rather than inspect source text:

1. Configuring `--target-list=x86-softmmu` builds `qemu-system-x86`.
2. QMP reports the `8086` and `8088` models with bus widths 16 and 8, while a
   later concrete CPU such as `486` is absent.
3. Machine/CPU bus-width mismatches fail with a clear error.
4. A hand-checked 8086 ROM runs under TCG from the reset vector and validates
   A20 wrap, original `PUSH SP`, `POP CS`, and rejection of an 80186 opcode.
5. Existing i386 tests confirm that later CPU registration and opcode behavior
   remain unchanged.

## Compatibility and publication

No existing executable, machine alias, CPU model, migration stream, or default
target changes behavior.  The new target is additive.  Repository rules forbid
generated branches, so verified commits are published by a guarded
fast-forward to `master`.
