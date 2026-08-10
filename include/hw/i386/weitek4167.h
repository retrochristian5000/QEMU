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

/* Conventional 80486 system mapping used by 4167-aware PC platforms. */
#define WEITEK4167_MMIO_BASE 0xc0000000ULL
#define WEITEK4167_MMIO_SIZE 0x01000000ULL

#endif /* HW_I386_WEITEK4167_H */
