/*
 * Toshiba MeP CPU QOM definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_MEP_CPU_QOM_H
#define QEMU_MEP_CPU_QOM_H

#include "hw/core/cpu.h"

#define TYPE_MEP_CPU "mep-cpu"
#define MEP_CPU_TYPE_SUFFIX "-" TYPE_MEP_CPU
#define MEP_CPU_TYPE_NAME(model) model MEP_CPU_TYPE_SUFFIX

#define TYPE_MEP_DEFAULT_CPU MEP_CPU_TYPE_NAME("default")

OBJECT_DECLARE_CPU_TYPE(MEPCPU, MEPCPUClass, MEP_CPU)

#endif /* QEMU_MEP_CPU_QOM_H */
