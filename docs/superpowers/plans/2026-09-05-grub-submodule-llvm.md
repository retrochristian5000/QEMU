# GRUB Submodule and LLVM Integration Implementation Plan

**Goal:** Pin the WHP GRUB fork as a QEMU submodule and make LLVM/LLD a first-class GRUB target toolchain while preserving the SeaBIOS IA32 EFI ABI.

**Architecture:** QEMU uses `toolchains/grub` as the default GRUB source and builds from an immutable archive of the selected gitlink. GRUB owns LLVM/GNU target-tool selection through a tracked frontend; QEMU requests LLVM mode rather than duplicating normal-path target-tool policy.

**Tech Stack:** Git submodules, Bash, Autoconf/Automake, Clang, LLD, LLVM binutils, GRUB, SeaBIOS.

## Global Constraints
- No branches; commit directly to the project default branches as authorized.
- Preserve `i386-none-elf` / `i386-efi` / `i386-efi-grub-mkimage` consumer ABI.
- GCC remains supported; unknown GCC options must not be silently discarded for Clang.
- `GRUB_I386_SOURCE_ARCHIVE` remains an explicit offline/reproducer override.
- No completion claim without fresh verification.

### Task 1: QEMU GRUB submodule source
- [x] Add `toolchains/grub` gitlink and fork URL.
- [x] Make the gitlink the default source identity.
- [x] Build from `git archive` so bootstrap generation never dirties the submodule.
- [x] Preserve the archive override.
- [x] Add source-policy checks.

### Task 2: GRUB-owned LLVM target-toolchain support
- [x] Add tracked `build-aux/whp-configure-toolchain` frontend.
- [x] Accept `--with-target-toolchain=auto|gnu|llvm`.
- [x] LLVM mode defaults unset target tools to Clang/LLVM equivalents.
- [x] Preserve explicit `TARGET_*` overrides.
- [x] Add target triple and LLD selection only when absent.
- [x] Keep existing compiler capability probes untouched and add no unknown-warning suppression.
- [x] Add an executable frontend regression test.
- [ ] Run the GRUB test on hosted CI (GRUB fork Actions did not launch; local-equivalent frontend regression passed).

### Task 3: QEMU consumer integration
- [x] Advance QEMU gitlink to the GRUB LLVM-support commit.
- [x] Request `--with-target-toolchain=llvm` on the default gitlink lane.
- [x] Remove duplicated normal-path `TARGET_*` tool policy from QEMU.
- [x] Keep legacy explicit `TARGET_*` handoff only for older archive overrides.
- [x] Record LLVM mode in the bootstrap marker.
- [ ] Run source-policy/archive regression on hosted CI.
- [ ] Run the macOS Apple Silicon real GRUB build, mkimage, PE/COFF, modules, and cache-reuse gates.
- [ ] Use any stricter Clang warning failures from that run as the next one-failure/one-fix inputs.
