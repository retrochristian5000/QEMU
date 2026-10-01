/*
 * Zilog Z80 CPU QOM definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_Z80_CPU_QOM_H
#define QEMU_Z80_CPU_QOM_H

#include "hw/core/cpu.h"

#define TYPE_Z80_CPU "z80-cpu"
#define Z80_CPU_TYPE_SUFFIX "-" TYPE_Z80_CPU
#define Z80_CPU_TYPE_NAME(model) model Z80_CPU_TYPE_SUFFIX

#define TYPE_Z80_Z80_CPU Z80_CPU_TYPE_NAME("z80")
#define TYPE_Z80_Z80A_CPU Z80_CPU_TYPE_NAME("z80a")

OBJECT_DECLARE_CPU_TYPE(Z80CPU, Z80CPUClass, Z80_CPU)

#endif /* QEMU_Z80_CPU_QOM_H */
