/* Motorola MC6809/MC6809E QOM definitions.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_M6809_CPU_QOM_H
#define QEMU_M6809_CPU_QOM_H
#include "hw/core/cpu.h"

#define TYPE_M6809_CPU "m6809-cpu"
#define M6809_CPU_TYPE_NAME(model) model "-" TYPE_M6809_CPU
#define TYPE_M6809_6809_CPU M6809_CPU_TYPE_NAME("6809")
#define TYPE_M6809_6809E_CPU M6809_CPU_TYPE_NAME("6809e")

OBJECT_DECLARE_CPU_TYPE(M6809CPU, M6809CPUClass, M6809_CPU)
#endif
