/*
 * QEMU TriMedia CPU QOM definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_TRIMEDIA_CPU_QOM_H
#define QEMU_TRIMEDIA_CPU_QOM_H

#include "hw/core/cpu.h"

#define TYPE_TRIMEDIA_CPU "trimedia-cpu"
#define TRIMEDIA_CPU_TYPE_SUFFIX "-" TYPE_TRIMEDIA_CPU
#define TRIMEDIA_CPU_TYPE_NAME(model) model TRIMEDIA_CPU_TYPE_SUFFIX

#define TYPE_TM3260_CPU TRIMEDIA_CPU_TYPE_NAME("tm3260")

OBJECT_DECLARE_CPU_TYPE(TrimediaCPU, TrimediaCPUClass, TRIMEDIA_CPU)

#endif
