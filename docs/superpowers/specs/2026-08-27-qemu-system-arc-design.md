# Basic qemu-system-arc Recovery Design

## Goal

Recover a basic 32-bit ARC system-emulation target from the historical QEMU ARC patch work so the fork builds a working `qemu-system-arc` binary before any Leapster-specific hardware is added.

The first milestone intentionally matches the proven boundary of the 2016 RFC series: the target builds, exposes ARC CPU models, runs a tiny bare-metal ARC program, and can be single-stepped with GDB. Interrupt completeness, MMU work, Linux boot, and Leapster peripherals are outside this first change.

## Why this route

QEMU-devel received a 29-patch ARC RFC in September 2016 that targeted ARCtangent-A5, ARC600, and ARC700. The series implemented essentially the instruction set except ASLS, demonstrated correct recursive Fibonacci execution, and was independently reported to build and single-step a small ARC program under GDB. The authors also documented that reset-vector handling was provisional and interrupt support was incomplete.

This makes the RFC a better starting point for the first bring-up than inventing a new ARC translator. Later Synopsys ARC QEMU work is useful as a modernization reference for current QEMU APIs, but the first recovery stays focused on the older ARC Classic/ARCompact path needed for eventual Leapster work.

Primary historical reference:

- https://lists.gnu.org/archive/html/qemu-devel/2016-09/msg04232.html

Modern ARC QEMU reference:

- https://foss-for-synopsys-dwc-arc-processors.github.io/documentation/2025.06/baremetal/simulators/qemu/

## Scope

The first recovery includes:

- a new `arc-softmmu` target that builds `qemu-system-arc`;
- a `target/arc/` CPU implementation recovered from the historical ARC work and adapted to the fork's current QEMU APIs;
- ARCtangent-A5, ARC600, and ARC700 CPU profiles where the recovered code already supports them;
- the RFC's minimal/sample ARC machine, modernized enough to provide RAM, load a small ELF/kernel payload, and start execution;
- GDB register exposure sufficient to reproduce the historical single-step smoke test;
- Meson/Kconfig/config target integration following the fork's existing custom-target pattern;
- focused build and smoke tests for the new target.

The first recovery does not include:

- Leapster machine emulation;
- Leapster LCD, touchscreen, cartridge, audio, or GPIO devices;
- ARCv2 EM/HS or ARC64 support;
- Linux boot support;
- a complete MMU/MPU model;
- full interrupt-controller behavior;
- speculative fixes to the RFC instruction semantics beyond what is required to compile and execute the known smoke test;
- unrelated refactors in existing QEMU targets.

## Integration with the current fork

The fork already carries custom CPU targets such as S2650 and TriMedia. ARC should follow the same repository-level integration shape rather than introducing another build convention.

Required top-level integration points are expected to include:

- `target/Kconfig` — add `source arc/Kconfig`;
- `target/meson.build` — add `subdir('arc')`;
- `configs/targets/arc-softmmu.mak` — declare the ARC target architecture and 32-bit target width;
- `configs/devices/arc-softmmu/default.mak` — enable the minimal ARC machine configuration;
- `target/arc/` — recovered CPU state, QOM type, translator, helpers, and GDB support;
- `hw/arc/` — minimal sample machine and its Kconfig/Meson glue.

No new Git branch is required for this work.

## CPU model boundary

The recovered target should preserve the three CPU identities from the RFC where practical:

- `arc-a5` / ARCtangent-A5;
- `arc600`;
- `arc700`.

Exact public QEMU CPU type strings should follow the recovered patch naming unless current QEMU naming rules require a mechanical adjustment. The CPU family distinction must live in CPU/profile data rather than scattered machine-specific checks.

ARCtangent-A5 is the priority validation CPU because it is the architecture needed by the original Leapster family. ARC600 and ARC700 should remain available if they fall out naturally from the recovered patch series, but they must not delay the first working A5 binary.

## Translator and instruction handling

The first pass should recover the existing RFC translator and decoder rather than rewrite the ISA into a new decoder framework immediately. A decoder rewrite would increase the number of simultaneous unknowns during bring-up.

Modernization is limited to mechanical or API-required changes such as:

- current TCG helper APIs;
- current CPU/QOM declarations;
- current translator-loop interfaces;
- current memory access helpers;
- current Meson/Kconfig organization;
- current GDB stub registration;
- compiler-warning fixes required by the fork's present build flags.

Behavioral rewrites are deferred until the recovered implementation is running and can be regression-tested.

## Minimal machine

The historical sample board should be restored as the first machine because it removes Leapster-specific variables from CPU validation.

The machine should provide only what is required for a bare-metal smoke test:

- one ARC CPU;
- a contiguous RAM region;
- a deterministic reset/start address;
- loading of a raw/ELF kernel payload through normal QEMU loader infrastructure;
- no invented chipset devices.

If the RFC sample board used a hard-coded reset address, the initial recovery may preserve that behavior behind the sample-machine profile, clearly documented as provisional. The CPU model itself should not permanently encode a Leapster or sample-board reset address.

A simple machine name such as the recovered RFC name should be retained for the first import. Renaming it to `arc-sim` is only appropriate if doing so is a mechanical compatibility improvement and does not obscure the provenance of the recovered machine.

## Interrupts, exceptions, and reset

The 2016 RFC explicitly identified interrupt support and reset-vector handling as incomplete. The first milestone therefore treats those as known limitations rather than silently claiming full ARC platform support.

Requirements for this first pass:

- synchronous exceptions needed by already-implemented instructions must not regress during modernization;
- reset must place the CPU at the sample machine's documented start address;
- the target must not advertise complete interrupt support unless it has been verified;
- unsupported interrupt paths should fail visibly through QEMU logging/assertion/error handling rather than corrupt CPU state silently.

Full interrupt-controller work belongs to a later ARC-core milestone before Leapster boot fidelity is considered complete.

## GDB and observability

The historical RFC was validated by single-stepping a program equivalent to:

```asm
.global _start
_start:
        mov     r0, 1
        mov     r1, 2
        mov     r1, r0
```

The recovered target should reproduce that class of test.

At minimum, GDB must be able to:

- connect to `qemu-system-arc`;
- read the program counter;
- read/write the general register file needed by the test;
- single-step one ARC instruction at a time;
- observe `r0 == 1`, then `r1 == 2`, then `r1 == 1` for the sequence above.

## Build configuration

The target is 32-bit and system-emulation-only for the first milestone.

The expected target configuration is conceptually:

```make
TARGET_ARCH=arc
TARGET_LONG_BITS=32
TARGET_NOT_USING_LEGACY_LDST_PHYS_API=y
TARGET_NOT_USING_LEGACY_NATIVE_ENDIAN_API=y
```

The exact legacy-API flags must match what the recovered code actually uses after modernization; flags must not be copied blindly from S2650 if ARC still depends on an API that the flag promises not to use.

The important externally visible result is:

```sh
./configure --target-list=arc-softmmu
ninja -C build qemu-system-arc
```

or the fork's equivalent configured build flow.

## Tests and acceptance criteria

The recovery is complete only when all of the following hold:

1. `arc-softmmu` configures successfully on the fork's supported build host.
2. `qemu-system-arc` links successfully without disabling the fork's normal warning policy solely for ARC.
3. `qemu-system-arc -cpu help` exposes the recovered ARC CPU model(s).
4. `qemu-system-arc -M help` exposes the minimal ARC sample machine.
5. A tiny ARC bare-metal image can be loaded and begins execution at the expected entry/reset address.
6. The three-instruction GDB smoke test can be single-stepped with the expected register results.
7. Existing non-ARC target configuration/build files continue to parse normally.
8. No Leapster-specific device code is introduced in this milestone.

If an ARC cross-compiler is not available in the ordinary CI environment, the build/configuration checks remain mandatory and the executable smoke-test fixture should be kept small enough to store as a generated test artifact or reproducible assembly source without adding a toolchain dependency to every QEMU build.

## Compatibility and migration

This is a new target in the fork, so there is no existing ARC migration ABI to preserve. Even so, CPU state fields should be structured cleanly so later VMState support does not require needless renaming or flattening.

The first sample machine is a bring-up machine, not a promise of stable PC-style machine-version compatibility. Any future machine-version guarantees should begin only after the target is usable enough to justify them.

## Future milestones

After the basic `qemu-system-arc` recovery is stable, work can proceed independently in this order:

1. verify/fix ARCtangent-A5 exception and interrupt behavior;
2. add focused ARC TCG instruction tests;
3. reconcile useful fixes from later Synopsys ARC QEMU work without importing unrelated ARCv2/ARC64 scope;
4. add the Leapster machine around the validated A5 CPU;
5. add Leapster memory map and cartridge loading;
6. add display, input/touchscreen, audio, and remaining ASIC peripherals.

The basic ARC target must remain usable as a CPU validation platform even after Leapster support is added.