/*
 * AT&T PC 6300 Model 301 keyboard profile
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Hardware reference: AT&T PC 6300 Service Manual, System Overview,
 * Input/Output Peripheral Interfaces and Keyboard sections.
 * https://bitsavers.org/pdf/att/6300/ATT_PC_6300_Service_Manual.pdf
 *
 * The original keyboard is connected through the 8041/8741 controller.
 * It is not an AT/PS/2 keyboard. Reuse an explicit controller or own
 * a private controller independently of machine defaults. Do not claim guest I/O
 * ports, IRQs or host input until the native board interface is ready.
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "hw/core/qdev-properties.h"
#include "hw/input/att-kbd301.h"
#include "hw/input/intel-8741-device.h"
#include "qemu/error-report.h"
#include "qemu/module.h"

#define TYPE_ATT_KBD301 "att-kbd301"
OBJECT_DECLARE_SIMPLE_TYPE(AttKbd301State, ATT_KBD301)

struct AttKbd301State {
    DeviceState parent_obj;
    AttKbd301Core core;
    Intel8741State *controller;
    char *controller_id;
};

static bool att_kbd301_read_byte(void *opaque, uint8_t *value)
{
    AttKbd301State *s = opaque;

    return att_kbd301_core_read(&s->core, value);
}

static char *att_kbd301_active_controller(Object *obj, Error **errp)
{
    AttKbd301State *s = ATT_KBD301(obj);

    return s->controller ? object_get_canonical_path(OBJECT(s->controller))
                         : g_strdup("");
}

static void att_kbd301_reset(DeviceState *dev)
{
    AttKbd301State *s = ATT_KBD301(dev);

    att_kbd301_core_reset(&s->core);
    if (s->controller) {
        device_cold_reset(DEVICE(s->controller));
    }
}

static void att_kbd301_realize(DeviceState *dev, Error **errp)
{
    AttKbd301State *s = ATT_KBD301(dev);

    s->controller = intel_8741_attach_keyboard(dev, s->controller_id,
                                               att_kbd301_read_byte,
                                               s, errp);
    if (!s->controller) {
        return;
    }

    att_kbd301_reset(dev);
    warn_report("AT&T 301 keyboard and Intel 8741 are connected, but "
                "guest I/O and keyboard input are not yet implemented");
}

static void att_kbd301_unrealize(DeviceState *dev)
{
    AttKbd301State *s = ATT_KBD301(dev);

    intel_8741_detach_keyboard(dev, s->controller, s);
    s->controller = NULL;
}

static const Property att_kbd301_properties[] = {
    DEFINE_PROP_STRING("controller-id", AttKbd301State, controller_id),
};

static void att_kbd301_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "AT&T 301 keyboard (Intel 8741 included; guest I/O pending)";
    dc->realize = att_kbd301_realize;
    dc->unrealize = att_kbd301_unrealize;
    device_class_set_legacy_reset(dc, att_kbd301_reset);
    dc->hotpluggable = false;
    device_class_set_props(dc, att_kbd301_properties);
    object_class_property_add_str(klass, "active-controller",
                                  att_kbd301_active_controller, NULL);
    set_bit(DEVICE_CATEGORY_INPUT, dc->categories);
}

static const TypeInfo att_kbd301_info = {
    .name = TYPE_ATT_KBD301,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(AttKbd301State),
    .class_init = att_kbd301_class_init,
};

static void att_kbd301_register_types(void)
{
    type_register_static(&att_kbd301_info);
}

type_init(att_kbd301_register_types)
