/*
 * Zilog Z80 CPU parameters
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef Z80_CPU_PARAM_H
#define Z80_CPU_PARAM_H

/*
 * The classic Z80 exposes a 16-bit (64 KiB) memory address space.
 * QEMU system emulation requires at least 9 target page bits, so use
 * 512-byte translation pages while retaining the architectural limit.
 */
#define TARGET_PAGE_BITS 9
#define TARGET_VIRT_ADDR_SPACE_BITS 16

#endif /* Z80_CPU_PARAM_H */
