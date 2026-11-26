/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Link the ROM image at segment-relative offset zero, not an ELF image base. */
OUTPUT_FORMAT(elf32-i386)
OUTPUT_ARCH(i386)
ENTRY(_start)

PHDRS
{
    rom PT_LOAD FLAGS(5);
}

SECTIONS
{
    .text 0 : AT(0) {
        KEEP(*(.text))
    } :rom

    /* The current ROM stores all resident bytes in .text. Do not silently
     * omit new code or data when objcopy extracts that single section. */
    .unexpected : {
        *(.text.* .rodata .rodata.* .data .data.* .bss .bss.* COMMON)
    } :NONE

    /DISCARD/ : { *(.comment .note.GNU-stack) }

    ASSERT(_start == 0, "IDE ROM header must start at offset zero")
    ASSERT(SIZEOF(.text) > 0 && SIZEOF(.text) <= 2048, "IDE ROM exceeds first-stage size limit")
    ASSERT((SIZEOF(.text) % 512) == 0, "IDE ROM must be sector aligned")
    ASSERT(SIZEOF(.unexpected) == 0, "IDE ROM contains unexpected allocated sections")
}
