/*
 * Apple Power Mac G4 AGP (PowerMac3,1 / Sawtooth) machine profile
 *
 * This profile specializes the generic mac99 implementation with defaults
 * matching the 1999 Power Mac G4 AGP family.  It intentionally inherits the
 * mac99 device model and firmware loading path so compatibility fixes remain
 * shared between the generic and historical machine types.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qapi/error.h"
#include "qom/object.h"
#include "hw/core/boards.h"
#include "hw/ppc/ppc.h"

#define TYPE_POWERMAC3_1_MACHINE MACHINE_TYPE_NAME("powermac3_1")
#define TYPE_CORE99_MACHINE MACHINE_TYPE_NAME("mac99")

static void powermac3_1_machine_class_init(ObjectClass *oc, const void *data)
{
    MachineClass *mc = MACHINE_CLASS(oc);
    static const char * const valid_cpu_types[] = {
        POWERPC_CPU_TYPE_NAME("7400_v2.9"),
        NULL,
    };

    mc->desc = "Apple Power Mac G4 AGP (PowerMac3,1 / Sawtooth)";
    mc->alias = "powermac3_1";
    mc->default_cpu_type = POWERPC_CPU_TYPE_NAME("7400_v2.9");
    mc->valid_cpu_types = valid_cpu_types;
    mc->default_ram_size = 128 * MiB;
}

static void powermac3_1_instance_init(Object *obj)
{
    /*
     * A real PowerMac3,1 uses the KeyLargo PMU and USB input rather than the
     * generic mac99 CUDA/ADB default.  The parent instance has already created
     * the via property, so selecting pmu also makes the inherited board omit
     * ADB and instantiate USB keyboard and mouse devices.
     */
    object_property_set_str(obj, "via", "pmu", &error_abort);
}

static const TypeInfo powermac3_1_machine_info = {
    .name          = TYPE_POWERMAC3_1_MACHINE,
    .parent        = TYPE_CORE99_MACHINE,
    .class_init    = powermac3_1_machine_class_init,
    .instance_init = powermac3_1_instance_init,
};

static void powermac3_1_machine_register_types(void)
{
    type_register_static(&powermac3_1_machine_info);
}

type_init(powermac3_1_machine_register_types)
