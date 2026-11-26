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
 * It is not an AT/PS/2 keyboard. Reuse an explicit controller or own
 * a private controller independently of machine defaults. The experimental
 * board register interface is opt-in and never overlays occupied I/O ports.
 * Controller ROM execution and serial timing are not yet implemented.
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "hw/core/irq.h"
#include "hw/input/att-kbd302-io.h"
#include "migration/blocker.h"
#include "qapi/error.h"
#include "system/address-spaces.h"
#include "system/memory.h"
#include "ui/input.h"
#include "hw/core/qdev-properties.h"
#include "hw/input/att-kbd302.h"
#include "hw/input/intel-8741-device.h"
#include "qemu/error-report.h"
#include "qemu/module.h"

#define TYPE_ATT_KBD302 "att-kbd302"
OBJECT_DECLARE_SIMPLE_TYPE(AttKbd302State, ATT_KBD302)

struct AttKbd302State {
    DeviceState parent_obj;
    AttKbd302Core core;
    Intel8741State *controller;
    char *controller_id;
    bool io_enabled;
    MemoryRegion data_io;
    MemoryRegion command_io;
    qemu_irq irq;
    QemuInputHandlerState *input;
    Error *migration_blocker;
};

static bool att_kbd302_read_byte(void *opaque, uint8_t *value)
{
    AttKbd302State *s = opaque;

    return att_kbd302_core_read(&s->core, value);
}

/*
 * Provisional byte-level receive path: never remove a keyboard byte
 * until the shared UPI-41 data buffer is free. Host commands are latched
 * but not executed; do not invent 8042 acknowledgements or consume IBF.
 */
static void att_kbd302_pump(AttKbd302State *s)
{
    Intel8741Core *core = &s->controller->core;
    uint8_t value;

    if (!(intel_8741_status(core) & (INTEL_8741_IBF | INTEL_8741_OBF)) &&
        intel_8741_read_keyboard(s->controller, &value)) {
        bool accepted = intel_8741_mcu_write(core, value);

        assert(accepted);
        qemu_irq_raise(s->irq);
    }
}

static void att_kbd302_input(DeviceState *dev, QemuConsole *src,
                             QemuInputEvent *evt)
{
    AttKbd302State *s = ATT_KBD302(dev);

    if (evt->type == INPUT_EVENT_KIND_KEY &&
        att_kbd302_core_linux_key(&s->core, evt->key.key, evt->key.down)) {
        att_kbd302_pump(s);
    }
}

static const QemuInputHandler att_kbd302_input_handler = {
    .name = "AT&T 302 experimental keyboard",
    .mask = INPUT_EVENT_MASK_KEY,
    .event = att_kbd302_input,
};

static uint64_t att_kbd302_read_port(AttKbd302State *s, unsigned int port)
{
    uint8_t value = 0xff;

    if (att_kbd302_io_read(&s->controller->core, port, &value) &&
        port == ATT_KBD302_DATA_PORT) {
        /* End this IRQ before raising another for a queued byte. */
        qemu_irq_lower(s->irq);
        att_kbd302_pump(s);
    }
    return value;
}

static uint64_t att_kbd302_data_read(void *opaque, hwaddr addr, unsigned size)
{
    return att_kbd302_read_port(opaque, ATT_KBD302_DATA_PORT);
}

static uint64_t att_kbd302_status_read(void *opaque, hwaddr addr, unsigned size)
{
    return att_kbd302_read_port(opaque, ATT_KBD302_COMMAND_PORT);
}

static void att_kbd302_data_write(void *opaque, hwaddr addr,
                                  uint64_t value, unsigned size)
{
    AttKbd302State *s = opaque;

    att_kbd302_io_write(&s->controller->core, ATT_KBD302_DATA_PORT, value);
}

static void att_kbd302_command_write(void *opaque, hwaddr addr,
                                     uint64_t value, unsigned size)
{
    AttKbd302State *s = opaque;

    att_kbd302_io_write(&s->controller->core, ATT_KBD302_COMMAND_PORT, value);
}

static const MemoryRegionOps att_kbd302_data_ops = {
    .read = att_kbd302_data_read,
    .write = att_kbd302_data_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
    .impl = { .min_access_size = 1, .max_access_size = 1 },
};

static const MemoryRegionOps att_kbd302_command_ops = {
    .read = att_kbd302_status_read,
    .write = att_kbd302_command_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
    .impl = { .min_access_size = 1, .max_access_size = 1 },
};

static bool att_kbd302_port_available(unsigned int port, Error **errp)
{
    MemoryRegionSection section = memory_region_find(get_system_io(), port, 1);

    if (!section.mr) {
        return true;
    }
    error_setg(errp, "AT&T 302 I/O port 0x%02x is already in use by %s",
               port, memory_region_name(section.mr));
    memory_region_unref(section.mr);
    return false;
}

static char *att_kbd302_active_controller(Object *obj, Error **errp)
{
    AttKbd302State *s = ATT_KBD302(obj);

    return s->controller ? object_get_canonical_path(OBJECT(s->controller))
                         : g_strdup("");
}

static void att_kbd302_reset(DeviceState *dev)
{
    AttKbd302State *s = ATT_KBD302(dev);

    att_kbd302_core_reset(&s->core);
    qemu_irq_lower(s->irq);
    if (s->controller) {
        device_cold_reset(DEVICE(s->controller));
    }
}

static void att_kbd302_realize(DeviceState *dev, Error **errp)
{
    AttKbd302State *s = ATT_KBD302(dev);

    if (s->io_enabled &&
        (!att_kbd302_port_available(ATT_KBD302_DATA_PORT, errp) ||
         !att_kbd302_port_available(ATT_KBD302_COMMAND_PORT, errp))) {
        return;
    }

    s->controller = intel_8741_attach_keyboard(dev, s->controller_id,
                                               att_kbd302_read_byte,
                                               s, errp);
    if (!s->controller) {
        return;
    }

    att_kbd302_reset(dev);
    if (!s->io_enabled) {
        warn_report("AT&T 302 keyboard is connected to UPI-41; "
                    "experimental guest I/O is disabled");
        return;
    }

    error_setg(&s->migration_blocker,
               "AT&T 302 experimental I/O state cannot be migrated");
    if (migrate_add_blocker(&s->migration_blocker, errp) < 0) {
        intel_8741_detach_keyboard(dev, s->controller, s);
        s->controller = NULL;
        return;
    }
    memory_region_init_io(&s->data_io, OBJECT(dev), &att_kbd302_data_ops,
                          s, "att-kbd302-data", 1);
    memory_region_init_io(&s->command_io, OBJECT(dev), &att_kbd302_command_ops,
                          s, "att-kbd302-command", 1);
    memory_region_add_subregion(get_system_io(), ATT_KBD302_DATA_PORT,
                                &s->data_io);
    memory_region_add_subregion(get_system_io(), ATT_KBD302_COMMAND_PORT,
                                &s->command_io);
    s->input = qemu_input_handler_register(dev, &att_kbd302_input_handler);
    warn_report("AT&T 302 experimental I/O enabled: controller command "
                "execution and motherboard IRQ1 wiring are incomplete");
}

static void att_kbd302_unrealize(DeviceState *dev)
{
    AttKbd302State *s = ATT_KBD302(dev);

    if (s->io_enabled) {
        g_clear_pointer(&s->input, qemu_input_handler_unregister);
        qemu_irq_lower(s->irq);
        memory_region_del_subregion(get_system_io(), &s->command_io);
        memory_region_del_subregion(get_system_io(), &s->data_io);
        migrate_del_blocker(&s->migration_blocker);
    }
    intel_8741_detach_keyboard(dev, s->controller, s);
    s->controller = NULL;
}

static void att_kbd302_init(Object *obj)
{
    AttKbd302State *s = ATT_KBD302(obj);

    qdev_init_gpio_out_named(DEVICE(obj), &s->irq, "irq1", 1);
}

static const Property att_kbd302_properties[] = {
    DEFINE_PROP_STRING("controller-id", AttKbd302State, controller_id),
    DEFINE_PROP_BOOL("io", AttKbd302State, io_enabled, false),
};

static void att_kbd302_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "AT&T 302 keyboard (Intel UPI-41; experimental I/O optional)";
    dc->realize = att_kbd302_realize;
    dc->unrealize = att_kbd302_unrealize;
    device_class_set_legacy_reset(dc, att_kbd302_reset);
    dc->hotpluggable = false;
    device_class_set_props(dc, att_kbd302_properties);
    object_class_property_add_str(klass, "active-controller",
                                  att_kbd302_active_controller, NULL);
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
