# 16-bit x86 System Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a genuine `qemu-system-x86` target with constrained Intel 8086 and 8088 CPU models and minimal matching machines.

**Architecture:** Reuse the i386 TCG and system source sets through `TARGET_BASE_ARCH=i386`, while a new `TARGET_X86_16BIT` contract filters CPU registration and enables original-generation reset/decoder behavior. Add two small TCG-only boards with explicit ROMs and bus-width validation instead of inheriting the AT-era `isapc` machine.

**Tech Stack:** QEMU C/QOM, Meson/Kconfig target plumbing, TCG x86 decoder, qtest/GLib, hand-checked 8086 ROM bytes.

## Global Constraints

- The new executable is named exactly `qemu-system-x86`.
- The initial target includes both `8086` and `8088` CPU models.
- `qemu-system-i386` and `qemu-system-x86_64` behavior remains unchanged.
- No branch creation; publish only a verified guarded fast-forward to `master`.
- No claim of cycle accuracy or complete IBM PC/XT hardware compatibility.

---

### Task 1: Target and CPU-model contract

**Files:**
- Create: `configs/targets/x86-softmmu.mak`
- Create: `configs/devices/x86-softmmu/default.mak`
- Create: `tests/qtest/x86-16bit-test.c`
- Modify: `tests/qtest/meson.build`
- Modify: `target/i386/cpu.h`
- Modify: `target/i386/cpu.c`

**Interfaces:**
- Consumes: QEMU target configuration and `X86CPUDefinition` registration.
- Produces: `TARGET_X86_16BIT`, CPU models `8086`/`8088`, and read-only `external-data-bus-width`.

- [ ] **Step 1: Write the failing CPU-model qtest**

Add a qtest that queries CPU definitions from `qemu-system-x86`, requires
`8086` and `8088`, rejects `486`, and reads literal bus-width values 16 and 8
from realized CPUs.

- [ ] **Step 2: Run the test to verify red**

Run: `meson test -C build-x86 qtest-x86/x86-16bit-test --print-errorlogs`

Expected: configuration or test failure because `x86-softmmu` and its CPU
models do not exist.

- [ ] **Step 3: Add the target and minimal CPU definitions**

Define `TARGET_ARCH=i386`, `TARGET_BASE_ARCH=i386`, `TARGET_LONG_BITS=32`, and
`TARGET_X86_16BIT=y`.  Extend `X86CPUDefinition` with original-generation and
external-bus metadata, register only 8086/8088 concrete models for this target,
and expose the bus width as a read-only QOM property.

- [ ] **Step 4: Run the focused model test**

Run: `meson test -C build-x86 qtest-x86/x86-16bit-test --print-errorlogs`

Expected: CPU-list and property cases pass; machine-dependent cases remain
skipped until Task 3.

### Task 2: Original-generation execution semantics

**Files:**
- Modify: `target/i386/cpu.c`
- Modify: `target/i386/tcg/translate.c`
- Modify: `target/i386/tcg/decode-new.c.inc`
- Modify: `target/i386/tcg/emit.c.inc`
- Modify: `tests/qtest/x86-16bit-test.c`

**Interfaces:**
- Consumes: per-model original-generation metadata in `CPUX86State`.
- Produces: correct reset/A20 state, `POP CS`, original `PUSH SP`, and
  generation-gated decoding.

- [ ] **Step 1: Add a failing executable-ROM test**

Use a literal 64 KiB ROM fixture containing only hand-checked 8086 bytes.  It
must reach the reset vector, validate A20 wrap and `PUSH SP`, execute `POP CS`,
install vector 6, execute opcode `0x60`, and print `T` through COM1 only if all
checks succeed.

- [ ] **Step 2: Verify the ROM test fails for missing/wrong semantics**

Run the focused qtest under TCG and confirm it fails before decoder/reset
changes, with the failure attributable to the absent 8086 behavior.

- [ ] **Step 3: Implement the smallest decoder/reset changes**

Preserve the generation across reset; use `f000:fff0` and A20-off for original
CPUs; treat `0x0f` as `POP CS`; reject post-8086 opcode/prefix families and
FS/GS segment encodings; implement decremented-value `PUSH SP`.

- [ ] **Step 4: Re-run the ROM test and existing i386 decoder tests**

Run the focused x86 qtest, then affected i386 qtests/TCG tests.  Both the new
behavior and the unchanged later-x86 behavior must pass.

### Task 3: Minimal 8086/8088 machines

**Files:**
- Create: `hw/i386/x86-16bit.c`
- Modify: `hw/i386/Kconfig`
- Modify: `hw/i386/meson.build`
- Modify: `tests/qtest/x86-16bit-test.c`

**Interfaces:**
- Consumes: CPU types and `external-data-bus-width` from Task 1.
- Produces: `x86-8086` and `x86-8088` machines with a 640 KiB RAM ceiling,
  right-aligned explicit ROM, ISA I/O bus, and COM1.

- [ ] **Step 1: Add failing machine contract cases**

Require both machine names, literal default CPU/bus pairings, successful boot
with an explicit 8086 ROM, clear rejection of mismatched CPU/bus pairs, and
clear rejection when `-bios` is omitted.

- [ ] **Step 2: Verify the machine cases fail before implementation**

Run the focused qtest and confirm the machine names are absent.

- [ ] **Step 3: Implement both machines**

Add one shared machine implementation with class data for expected bus width,
single-CPU TCG-only validation, RAM mapping, explicit 64 KiB ROM window, and an
ISA serial port.  Register `x86-8086` as the default and `x86-8088` as its
8-bit-bus sibling.

- [ ] **Step 4: Run all focused target tests**

Run all `qtest-x86` cases and direct `-machine help`, `-cpu help`, missing-ROM,
and mismatch smoke commands.

### Task 4: Documentation, broad verification, and publication

**Files:**
- Create: `docs/system/target-x86.rst`
- Modify: `docs/system/targets.rst`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: final executable, CPUs, machines, and test names.
- Produces: user-facing invocation limits and durable Linux CI coverage.

- [ ] **Step 1: Document exact supported and unsupported boundaries**

Document `-bios` requirements, machine/CPU pairing, bus-width meaning, covered
8086 semantics, and the explicit non-goals from the design.

- [ ] **Step 2: Add the x86-softmmu CI lane**

Extend the existing Linux target matrix with `x86`, build
`qemu-system-x86`, and run the focused target qtests.

- [ ] **Step 3: Run fresh verification**

Run configure/build, focused qtests, affected i386 regression tests,
`scripts/checkpatch.pl`, `git diff --check`, workflow parsing, and a complete
diff review.  Record any unavailable layer as partial rather than confirmed.

- [ ] **Step 4: Commit and publish**

Commit coherent verified slices, fetch the current remote `master`, verify the
parent has not changed, push without force, and confirm GitHub's remote tree and
CI result match the local verified tree.
