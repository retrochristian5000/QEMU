/*
 * Signetics 2650 CPU parameters
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef S2650_CPU_PARAM_H
#define S2650_CPU_PARAM_H

/*
 * The CPU exposes a 15-bit (32 KiB) architectural address space.  QEMU system
 * emulation requires at least 9 target page bits, so use 512-byte translation
 * pages while retaining the real 15-bit address limit.
 */
#define TARGET_PAGE_BITS 9
#define TARGET_VIRT_ADDR_SPACE_BITS 15

#endif /* S2650_CPU_PARAM_H */
