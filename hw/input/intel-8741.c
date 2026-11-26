/*
 * Intel 8741 UPI-41 peripheral controller profile.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "hw/input/intel-8741.h"
#include "qapi/error.h"
#include "qemu/module.h"

#define TYPE_INTEL_8741 "intel-8741"
OBJECT_DECLARE_SIMPLE_TYPE(Intel8741State, INTEL_8741)

struct Intel8741State {
    DeviceState parent_obj;
    Intel8741Core core;
};

static void intel_8741_reset(DeviceState *dev)
{
    Intel8741State *s = INTEL_8741(dev);

    intel_8741_core_reset(&s->core);
}

static void intel_8741_realize(DeviceState *dev, Error **errp)
{
    error_setg(errp, "Intel 8741 host interface is implemented, but "
               "controller firmware and board wiring are not yet available");
}

static void intel_8741_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Intel 8741 UPI-41 controller (host interface; firmware pending)";
    dc->realize = intel_8741_realize;
    device_class_set_legacy_reset(dc, intel_8741_reset);
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_BRIDGE, dc->categories);
}

static const TypeInfo intel_8741_info = {
    .name = TYPE_INTEL_8741,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(Intel8741State),
    .class_init = intel_8741_class_init,
};

static void intel_8741_register_types(void)
{
    type_register_static(&intel_8741_info);
}

type_init(intel_8741_register_types)
