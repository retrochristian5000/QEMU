/*
 * Intel 8741 UPI-41 peripheral controller profile.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/input/intel-8741-device.h"
#include "qapi/error.h"
#include "qemu/module.h"

void intel_8741_connect_keyboard(Intel8741State *s,
                                 Intel8741KeyboardRead read_byte,
                                 void *opaque)
{
    assert(!DEVICE(s)->realized && !s->keyboard_read);
    assert(read_byte);
    s->keyboard_read = read_byte;
    s->keyboard_opaque = opaque;
}

bool intel_8741_read_keyboard(Intel8741State *s, uint8_t *value)
{
    return DEVICE(s)->realized && s->keyboard_read &&
           s->keyboard_read(s->keyboard_opaque, value);
}

static bool intel_8741_keyboard_attached(Object *obj, Error **errp)
{
    return INTEL_8741(obj)->keyboard_read != NULL;
}

static void intel_8741_reset(DeviceState *dev)
{
    Intel8741State *s = INTEL_8741(dev);

    intel_8741_core_reset(&s->core);
    intel_8741_program_reset(&s->program);
}

static void intel_8741_realize(DeviceState *dev, Error **errp)
{
    Intel8741State *s = INTEL_8741(dev);

    if (!s->keyboard_read) {
        error_setg(errp, "Intel 8741 requires a connected peripheral; "
                   "use att-kbd302 to create the experimental keyboard pair");
        return;
    }

    intel_8741_reset(dev);
}

static void intel_8741_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Intel 8741 UPI-41 controller (keyboard link; guest I/O pending)";
    object_class_property_add_bool(klass, "keyboard-attached",
                                   intel_8741_keyboard_attached, NULL);
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
