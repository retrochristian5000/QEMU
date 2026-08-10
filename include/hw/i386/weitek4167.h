/*
 * Weitek 4167 floating-point coprocessor
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_I386_WEITEK4167_H
#define HW_I386_WEITEK4167_H

#include "hw/core/sysbus.h"

#define TYPE_WEITEK4167 "weitek4167"
OBJECT_DECLARE_SIMPLE_TYPE(Weitek4167State, WEITEK4167)

/*
 * The 4167 is selected in the 0xc0000000-0xc1ffffff physical range.
 * A24..A16 are not part of the coprocessor's operation address input, so
 * the 64 KiB programming window is mirrored throughout that decode range.
 */
#define WEITEK4167_MMIO_BASE        0xc0000000ULL
#define WEITEK4167_MMIO_SIZE        0x02000000ULL
#define WEITEK4167_PROGRAM_SIZE     0x00010000ULL
#define WEITEK4167_PROGRAM_MASK     (WEITEK4167_PROGRAM_SIZE - 1)

/* AT-compatible systems route the coprocessor interrupt output to IRQ13. */
#define WEITEK4167_IRQ              13

#endif /* HW_I386_WEITEK4167_H */
