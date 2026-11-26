/*
 * Intel 8041 original UPI-41 controller variant.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Intel MCS-48 and UPI-41 Assembly Language Reference Manual, 9800255D,
 * December 1978, p. 1-1: 1 KiB mask ROM, 64 bytes RAM.
 * Program memory technology is descriptive; programming and firmware
 * loading are not implemented by this profile.
 */

#include "qemu/osdep.h"
#include "hw/input/intel-8741-device.h"

static char *intel_8041_memory_type(Object *obj, Error **errp)
{
    return g_strdup("mask-rom");
}

static void intel_8041_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Intel 8041 UPI-41 controller (keyboard link; guest I/O pending)";
    object_class_property_add_str(klass, "program-memory-type",
                                  intel_8041_memory_type, NULL);
}

const TypeInfo intel_8041_info = {
    .name = TYPE_INTEL_8041,
    .parent = TYPE_INTEL_UPI41,
    .class_init = intel_8041_class_init,
};
