# GRUB Submodule and LLVM Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the WHP GRUB fork as a QEMU submodule and make LLVM/LLD a first-class GRUB target toolchain while preserving the SeaBIOS IA32 EFI ABI.

**Architecture:** QEMU uses `toolchains/grub` as the default GRUB source and builds from an immutable archive of the selected gitlink. GRUB gains an explicit LLVM target-toolchain configure mode that fills unset `TARGET_*` tools with LLVM equivalents and relies on existing capability probes for compiler flags.

**Tech Stack:** Git submodules, Bash, Autoconf/Automake, Clang, LLD, LLVM binutils, GRUB, SeaBIOS.

**Spec:** `docs/superpowers/specs/2026-09-05-grub-submodule-llvm-design.md`

## Global Constraints
- No branches; commit directly to the project default branches as authorized.
- Preserve `i386-none-elf` / `i386-efi` / `i386-efi-grub-mkimage` consumer ABI.
- GCC remains supported; unknown GCC options must not be silently discarded for Clang.
- `GRUB_I386_SOURCE_ARCHIVE` remains an explicit offline/reproducer override.
- No completion claim without fresh verification.

---

### Task 1: QEMU GRUB submodule source

**Files:**
- Modify: `.gitmodules`
- Add gitlink: `toolchains/grub`
- Modify: `scripts/bootstrap-i386-efi-grub.bash`
- Modify: `scripts/tests/test-grub-fork-source.bash`
- Modify: `scripts/tests/test-i386-efi-grub-bootstrap.bash`
- Modify: `.github/workflows/grub-i386-efi.yml`

**Interfaces:**
- Consumes: WHP GRUB fork gitlink at `toolchains/grub`.
- Produces: exact local GRUB source snapshot for the existing IA32 EFI bootstrap.

- [ ] Add a source-policy regression requiring `toolchains/grub` and rejecting an independent default GRUB clone/fetch path.
- [ ] Add the submodule gitlink and `.gitmodules` entry.
- [ ] Change the bootstrap default source to the selected gitlink and validate the checked-out revision.
- [ ] Build from `git archive` so bootstrap generation never dirties the submodule.
- [ ] Preserve the archive override path unchanged.
- [ ] Run shell syntax and existing GRUB bootstrap/source-policy tests.
- [ ] Commit the QEMU dependency-layout change.

### Task 2: Native LLVM target-toolchain mode in GRUB

**Files:**
- Modify: `configure.ac`
- Create: `tests/whp_llvm_toolchain_config_test.sh`

**Interfaces:**
- Consumes: `--with-target-toolchain=llvm` plus optional caller-supplied `TARGET_*` overrides.
- Produces: Clang/LLD/LLVM-binutils target tool defaults without changing GCC defaults.

- [ ] Add a failing source/configure regression proving LLVM mode selects LLVM target tools while explicit `TARGET_*` overrides win.
- [ ] Add `--with-target-toolchain=llvm` parsing with accepted values `auto`, `gnu`, and `llvm`.
- [ ] In LLVM mode, default unset `TARGET_CC` to `clang`, `TARGET_OBJCOPY` to `llvm-objcopy`, `TARGET_STRIP` to `llvm-strip`, `TARGET_NM` to `llvm-nm`, and `TARGET_RANLIB` to `llvm-ranlib`; keep explicit values unchanged.
- [ ] Add the selected target triple and LLD driver selection only in LLVM mode.
- [ ] Retain the existing capability probes for compiler-specific flags.
- [ ] Run bootstrap/configure checks for LLVM mode and a GCC/default control.
- [ ] Commit the GRUB LLVM-support change.

### Task 3: Simplify QEMU GRUB consumer and integrate

**Files:**
- Modify: `scripts/bootstrap-i386-efi-grub.bash`
- Modify: `scripts/tests/test-i386-efi-grub-bootstrap.bash`
- Modify: `.github/workflows/grub-i386-efi.yml`
- Update gitlink: `toolchains/grub`

**Interfaces:**
- Consumes: GRUB LLVM mode from the submodule.
- Produces: the unchanged SeaBIOS-facing `i386-efi-grub-mkimage` plus module directory.

- [ ] Add regression assertions that QEMU invokes GRUB's LLVM mode and no longer duplicates target-tool defaults unnecessarily.
- [ ] Pass the WHP LLVM bin directory through `PATH`, request GRUB LLVM mode, and retain only target ABI values QEMU owns.
- [ ] Update the gitlink to the verified GRUB LLVM commit.
- [ ] Verify source marker records the gitlink commit.
- [ ] Run source-policy and bootstrap regression tests.
- [ ] Run the macOS Apple Silicon integration: real GRUB build, mkimage smoke image, PE/COFF IA32 check, modules, cache reuse.
- [ ] Run a GCC/default GRUB configure control.
- [ ] Commit the QEMU consumer integration.
