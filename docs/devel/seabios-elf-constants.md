# Experimental i386 ELF constant section splitting

The ROM budget workflow on 2026-11-26 measured 107520 bytes for GCC,
133408 for Clang -Os, and 131504 for segmented -Oz/flat -Os on
the same isapc configuration and GNU binutils. The final boundary
padding was zero for the segmented build. Do not assume linker padding
is the source of the overflow.

The pinned LLVM fork provides an opt-in backend flag
`-mllvm -x86-elf-separate-constants`. It separates eligible local
unnamed-address mergeable globals into uniquely named read-only
sections when data sections are enabled for 32-bit bare-metal x86
ELF or CODE16. Section-based reachability can then discard individual
unused constants instead of retaining the complete string pool.
Machine constant pools and explicitly named sections are unchanged.

Use a rebuilt compiler from the pinned fork (not distribution Clang)
and an independent build root:

```sh
make -C roms build-seabios-config-seabios-128k \
  SEABIOS_CLANG_ELF_SPLIT=1 \
  SEABIOS_CROSS_PREFIX=/path/to/toolchain/bin/i386-none-elf- \
  SEABIOS_BUILD_ROOT=/path/to/elf-split-comparison
```

Compare against the same compiler, configuration and binutils with
`SEABIOS_CLANG_ELF_SPLIT=0`. Enable WHP_ROM_SIZE_REPORT=1 to inspect
retained sections. The existing wrapper still removes ELF merge
semantics from any remaining pools. The option is off by default
and its setting participates in the firmware cache stamp.
No ROM-size improvement or boot compatibility is claimed until
the fork is rebuilt and measured.
