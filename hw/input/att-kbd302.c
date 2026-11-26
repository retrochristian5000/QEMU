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
 * It is not an AT/PS/2 keyboard. Reserve a discoverable device type
 * without registering input handlers, I/O ports or IRQs until the
 * original controller and keyboard protocol can be implemented.
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "hw/input/att-kbd302.h"
#include "qapi/error.h"
#include "qemu/module.h"

#define TYPE_ATT_KBD302 "att-kbd302"
OBJECT_DECLARE_SIMPLE_TYPE(AttKbd302State, ATT_KBD302)

struct AttKbd302State {
    DeviceState parent_obj;
    AttKbd302Core core;
};

static void att_kbd302_reset(DeviceState *dev)
{
    AttKbd302State *s = ATT_KBD302(dev);

    att_kbd302_core_reset(&s->core);
}

static void att_kbd302_realize(DeviceState *dev, Error **errp)
{
    error_setg(errp, "AT&T 302 keyboard requires an unimplemented "
               "8041/8741 controller; use the standard keyboard for now");
}

static void att_kbd302_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "AT&T 302 keyboard (reserved; controller not implemented)";
    dc->realize = att_kbd302_realize;
    device_class_set_legacy_reset(dc, att_kbd302_reset);
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_INPUT, dc->categories);
}

static const TypeInfo att_kbd302_info = {
    .name = TYPE_ATT_KBD302,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(AttKbd302State),
    .class_init = att_kbd302_class_init,
};

static void att_kbd302_register_types(void)
{
    type_register_static(&att_kbd302_info);
}

type_init(att_kbd302_register_types)
