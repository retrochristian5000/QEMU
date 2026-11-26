/*
 * AT&T PC 6300 Model 302 keyboard profile
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Hardware reference: AT&T PC 6300 Service Manual, System Overview,
 * Input/Output Peripheral Interfaces and Keyboard sections.
 * https://bitsavers.org/pdf/att/6300/ATT_PC_6300_Service_Manual.pdf
 *
 * The original keyboard is connected through the 8041/8741 controller.
 * It is not an AT/PS/2 keyboard. The experimental assembly owns its
 * controller independently of machine defaults. Do not claim guest I/O
 * ports, IRQs or host input until the native board interface is ready.
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "hw/input/att-kbd302.h"
#include "hw/input/intel-8741-device.h"
#include "qemu/error-report.h"
#include "qemu/module.h"

#define TYPE_ATT_KBD302 "att-kbd302"
OBJECT_DECLARE_SIMPLE_TYPE(AttKbd302State, ATT_KBD302)

struct AttKbd302State {
    DeviceState parent_obj;
    AttKbd302Core core;
    Intel8741State controller;
};

static bool att_kbd302_read_byte(void *opaque, uint8_t *value)
{
    AttKbd302State *s = opaque;

    return att_kbd302_core_read(&s->core, value);
}

static void att_kbd302_init(Object *obj)
{
    AttKbd302State *s = ATT_KBD302(obj);

    object_initialize_child(obj, "controller", &s->controller,
                            TYPE_INTEL_8741);
    intel_8741_connect_keyboard(&s->controller, att_kbd302_read_byte, s);
}

static void att_kbd302_reset(DeviceState *dev)
{
    AttKbd302State *s = ATT_KBD302(dev);

    att_kbd302_core_reset(&s->core);
    device_cold_reset(DEVICE(&s->controller));
}

static void att_kbd302_realize(DeviceState *dev, Error **errp)
{
    AttKbd302State *s = ATT_KBD302(dev);

    if (!qdev_realize(DEVICE(&s->controller), NULL, errp)) {
        return;
    }

    att_kbd302_reset(dev);
    warn_report("AT&T 302 keyboard and Intel 8741 are connected, but "
                "guest I/O and keyboard input are not yet implemented");
}

static void att_kbd302_unrealize(DeviceState *dev)
{
    AttKbd302State *s = ATT_KBD302(dev);

    qdev_unrealize(DEVICE(&s->controller));
}

static void att_kbd302_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "AT&T 302 keyboard (Intel 8741 included; guest I/O pending)";
    dc->realize = att_kbd302_realize;
    dc->unrealize = att_kbd302_unrealize;
    device_class_set_legacy_reset(dc, att_kbd302_reset);
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_INPUT, dc->categories);
}

static const TypeInfo att_kbd302_info = {
    .name = TYPE_ATT_KBD302,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(AttKbd302State),
    .instance_init = att_kbd302_init,
    .class_init = att_kbd302_class_init,
};

static void att_kbd302_register_types(void)
{
    type_register_static(&att_kbd302_info);
}

type_init(att_kbd302_register_types)
