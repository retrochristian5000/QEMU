/*
 * Signetics 2650 CPU QOM definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_S2650_CPU_QOM_H
#define QEMU_S2650_CPU_QOM_H

#include "hw/core/cpu.h"

#define TYPE_S2650_CPU "s2650-cpu"
#define TYPE_S2650_2650_CPU S2650_CPU_TYPE_NAME("2650")
#define TYPE_S2650_2650A_CPU S2650_CPU_TYPE_NAME("2650a")

OBJECT_DECLARE_CPU_TYPE(S2650CPU, S2650CPUClass, S2650_CPU)

#define S2650_CPU_TYPE_SUFFIX "-" TYPE_S2650_CPU
#define S2650_CPU_TYPE_NAME(model) model S2650_CPU_TYPE_SUFFIX

#endif /* QEMU_S2650_CPU_QOM_H */
