# SeaBIOS inline policy

SeaBIOS's `__always_inline` macro in src/types.h is a mandatory compiler
attribute, unlike the ordinary C `inline` hint. Do not replace it globally:
hardware helpers may rely on the caller's register, stack or segment context.

The 128 KiB isapc default remains CompactFlat. RequiredOnlyFlat is a
diagnostic profile using Clang's -fno-inline-functions on size-optimized
flat-mode C translation units only. Explicit always_inline and noinline
remain effective; 16-bit and segmented code are unchanged. Disabling
ordinary inlining can grow the ROM, so the strict default budget gate is
independent of this experiment.

Compare raw BIOS sizes with the same compiler, configuration, and linker:

    make -C roms build-seabios-config-seabios-128k \
      SEABIOS_CLANG_INLINE_PROFILE=RequiredOnlyFlat

Use a separate SEABIOS_BUILD_ROOT for an independent comparison or let the
existing source stamp invalidate objects when changing profiles. CI also
lists forced-inline source matches from the exact pinned firmware tree.
The inventory includes macro definitions/comments and is not a count of
emitted inline expansions.
