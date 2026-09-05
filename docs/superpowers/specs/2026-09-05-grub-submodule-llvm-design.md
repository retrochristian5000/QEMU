# GRUB Submodule and LLVM Integration Design

## Goal
Make the WHP GRUB fork a pinned QEMU submodule and move LLVM/LLD target-tool knowledge into GRUB itself while preserving the existing SeaBIOS IA32 EFI consumer ABI.

## Architecture
QEMU owns the dependency pin through a `toolchains/grub` gitlink. Its SeaBIOS bootstrap consumes an immutable local archive of that exact gitlink by default, while retaining `GRUB_I386_SOURCE_ARCHIVE` only as an explicit offline/reproducer override. GRUB owns compiler/tool selection through its tracked `build-aux/whp-configure-toolchain` frontend. The frontend accepts `--with-target-toolchain=auto|gnu|llvm`; LLVM mode selects Clang, LLD, and LLVM binutils while retaining explicit caller overrides. GRUB's existing compiler capability probes remain authoritative.

## ABI
- QEMU submodule path: `toolchains/grub`
- GRUB repository: `https://github.com/retrochristian5000/grub.git`
- GRUB target: `i386-none-elf`
- GRUB platform: `i386-efi`
- Compiler: Clang in LLVM mode
- Linker: LLD through Clang with `-fuse-ld=lld`
- Target utilities: `llvm-objcopy`, `llvm-strip`, `llvm-nm`, `llvm-ranlib`
- Build objects: ELF32 i386
- Final image: PE/COFF IA32 EFI
- SeaBIOS consumer: `i386-efi-grub-mkimage` and the `i386-efi` module directory

## Compatibility rules
GCC remains supported and is the control path. LLVM mode must not silence unknown or semantically incompatible GCC options. Existing compiler feature probes remain authoritative; fixes for stricter Clang diagnostics are narrow and evidence-driven. The default QEMU gitlink lane uses the GRUB-owned frontend; the explicit archive override retains a compatibility handoff for older source archives.

## Verification
Verify the QEMU gitlink/repository identity, no independent default GRUB clone, archive override compatibility, the GRUB LLVM/GNU frontend contract, Clang/LLD i386 build, LLVM object utilities, `grub-mkimage` image generation, PE/COFF IA32 output, SeaBIOS consumption, cache reuse, and a GCC control lane. Do not claim runtime configure/build verification for the GRUB fork until an actual runner executes it.
