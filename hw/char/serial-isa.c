/*
 * QEMU 16550A UART emulation
 *
 * Copyright (c) 2003-2004 Fabrice Bellard
 * Copyright (c) 2008 Citrix Systems, Inc.
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "system/system.h"
#include "hw/acpi/acpi_aml_interface.h"
#include "hw/char/serial.h"
#include "chardev/modem.h"
#include "hw/char/serial-isa.h"
#include "hw/isa/isa.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "qom/object.h"

OBJECT_DECLARE_SIMPLE_TYPE(ISASerialState, ISA_SERIAL)

struct ISASerialState {
    ISADevice parent_obj;

    uint32_t index;
    uint32_t iobase;
    uint32_t isairq;
    SerialState state;
    Chardev *owned_modem;
};

static const int isa_serial_io[MAX_ISA_SERIAL_PORTS] = {
    0x3f8, 0x2f8, 0x3e8, 0x2e8
};
static const int isa_serial_irq[MAX_ISA_SERIAL_PORTS] = {
    4, 3, 4, 3
};

static int serial_isa_collect_indices(DeviceState *dev, void *opaque)
{
    uint32_t *used = opaque;

    if (qdev_is_realized(dev) &&
        object_dynamic_cast(OBJECT(dev), TYPE_ISA_SERIAL)) {
        ISASerialState *isa = ISA_SERIAL(dev);

        if (isa->index < MAX_ISA_SERIAL_PORTS) {
            *used |= 1U << isa->index;
        }
    }
    return 0;
}

static void serial_isa_realizefn(DeviceState *dev, Error **errp)
{
    uint32_t used = 0;
    ISADevice *isadev = ISA_DEVICE(dev);
    ISASerialState *isa = ISA_SERIAL(dev);
    SerialState *s = &isa->state;
    ISABus *bus = isa_bus_from_device(isadev);

    qbus_walk_children(BUS(bus), serial_isa_collect_indices,
                       NULL, NULL, NULL, &used);
    if (isa->index == UINT32_MAX) {
        for (isa->index = 0; isa->index < MAX_ISA_SERIAL_PORTS; isa->index++) {
            if (!(used & (1U << isa->index))) {
                break;
            }
        }
    }
    if (isa->index >= MAX_ISA_SERIAL_PORTS) {
        error_setg(errp, "Max. supported number of ISA serial ports is %d.",
                   MAX_ISA_SERIAL_PORTS);
        return;
    }
    if (used & (1U << isa->index)) {
        error_setg(errp, "isa-serial: COM%u is already assigned",
                   isa->index + 1);
        return;
    }
    if (isa->iobase == -1) {
        isa->iobase = isa_serial_io[isa->index];
    }
    if (isa->isairq == -1) {
        isa->isairq = isa_serial_irq[isa->index];
    }
    if (isa->isairq >= ISA_NUM_IRQS || !bus->irqs_in ||
        !bus->irqs_in[isa->isairq]) {
        error_setg(errp, "isa-serial: COM%u IRQ %u is not connected on this bus",
                   isa->index + 1, isa->isairq);
        return;
    }
    if (!isa_ioport_range_available(isadev, isa->iobase, 8, errp)) {
        return;
    }

    if (s->integrated_modem) {
        if (qemu_chr_fe_get_driver(&s->chr)) {
            error_setg(errp, "%s owns its modem backend; omit chardev",
                       object_get_typename(OBJECT(dev)));
            return;
        }
        isa->owned_modem = qemu_modem_new_offline(
            object_get_typename(OBJECT(dev)), errp);
        if (!isa->owned_modem) {
            return;
        }
        if (!qemu_chr_fe_init(&s->chr, isa->owned_modem, errp)) {
            object_unparent(OBJECT(isa->owned_modem));
            isa->owned_modem = NULL;
            return;
        }
    }

    s->irq = isa_bus_get_irq(bus, isa->isairq);
    if (!qdev_realize(DEVICE(s), NULL, errp)) {
        if (isa->owned_modem) {
            qemu_chr_fe_deinit(&s->chr, true);
            isa->owned_modem = NULL;
        }
        return;
    }
    qdev_set_legacy_instance_id(dev, isa->iobase, 3);

    memory_region_init_io(&s->io, OBJECT(isa), &serial_io_ops, s, "serial", 8);
    isa_register_ioport(isadev, &s->io, isa->iobase);
}

static void serial_isa_build_aml(AcpiDevAmlIf *adev, Aml *scope)
{
    ISASerialState *isa = ISA_SERIAL(adev);
    Aml *dev;
    Aml *crs;

    crs = aml_resource_template();
    aml_append(crs, aml_io(AML_DECODE16, isa->iobase, isa->iobase, 0x00, 0x08));
    aml_append(crs, aml_irq(isa->isairq, AML_LEVEL, AML_ACTIVE_LOW,
                            AML_SHARED));

    dev = aml_device("COM%d", isa->index + 1);
    aml_append(dev, aml_name_decl("_HID",
                                  aml_eisaid(isa->state.no_fifo ?
                                             "PNP0500" : "PNP0501")));
    aml_append(dev, aml_name_decl("_UID", aml_int(isa->index + 1)));
    aml_append(dev, aml_name_decl("_STA", aml_int(0xf)));
    aml_append(dev, aml_name_decl("_CRS", crs));

    aml_append(scope, dev);
}

static const VMStateDescription vmstate_isa_serial = {
    .name = "serial",
    .version_id = 3,
    .minimum_version_id = 2,
    .fields = (const VMStateField[]) {
        VMSTATE_STRUCT(state, ISASerialState, 0, vmstate_serial, SerialState),
        VMSTATE_END_OF_LIST()
    }
};

static const Property serial_isa_properties[] = {
    DEFINE_PROP_UINT32("index",  ISASerialState, index,   -1),
    DEFINE_PROP_UINT32("iobase",  ISASerialState, iobase,  -1),
    DEFINE_PROP_UINT32("irq",    ISASerialState, isairq,  -1),
};

static void serial_isa_class_initfn(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    AcpiDevAmlIfClass *adevc = ACPI_DEV_AML_IF_CLASS(klass);

    dc->realize = serial_isa_realizefn;
    dc->desc = "ISA 16550A-compatible UART serial port";
    dc->vmsd = &vmstate_isa_serial;
    adevc->build_dev_aml = serial_isa_build_aml;
    device_class_set_props(dc, serial_isa_properties);
    set_bit(DEVICE_CATEGORY_INPUT, dc->categories);
}

static void serial_isa_initfn(Object *o)
{
    ISASerialState *self = ISA_SERIAL(o);

    object_initialize_child(o, "serial", &self->state, TYPE_SERIAL);

    qdev_alias_all_properties(DEVICE(&self->state), o);
}

static const TypeInfo serial_isa_info = {
    .name          = TYPE_ISA_SERIAL,
    .parent        = TYPE_ISA_DEVICE,
    .instance_size = sizeof(ISASerialState),
    .instance_init = serial_isa_initfn,
    .class_init    = serial_isa_class_initfn,
    .interfaces = (const InterfaceInfo[]) {
        { TYPE_ACPI_DEV_AML_IF },
        { },
    },
};

/*
 * National Semiconductor AN-493: INS8250A and NS16450 share the
 * non-FIFO register set, including the scratch register. Their different
 * electrical bus timings are not modeled by the common UART engine.
 */
static void serial_nonfifo_init(Object *obj)
{
    ISA_SERIAL(obj)->state.no_fifo = true;
}

static void ins8250a_class_init(ObjectClass *klass, const void *data)
{
    DEVICE_CLASS(klass)->desc = "National Semiconductor INS8250A ISA UART";
}

static void ns16450_class_init(ObjectClass *klass, const void *data)
{
    DEVICE_CLASS(klass)->desc = "National Semiconductor NS16450 ISA UART";
}

static void ns16550a_class_init(ObjectClass *klass, const void *data)
{
    DEVICE_CLASS(klass)->desc = "National Semiconductor 16550A ISA UART";
}

static const TypeInfo ins8250a_info = {
    .name = "ins8250a",
    .parent = TYPE_ISA_SERIAL,
    .instance_init = serial_nonfifo_init,
    .class_init = ins8250a_class_init,
};

static const TypeInfo ns16450_info = {
    .name = "ns16450",
    .parent = TYPE_ISA_SERIAL,
    .instance_init = serial_nonfifo_init,
    .class_init = ns16450_class_init,
};

static const TypeInfo ns16550a_info = {
    .name = "ns16550a",
    .parent = TYPE_ISA_SERIAL,
    .class_init = ns16550a_class_init,
};

/* These devices are integrated ISA compatibility boards, not external
 * modems plugged into an already existing serial port.
 */
static void isa_modem_init(Object *obj)
{
    ISA_SERIAL(obj)->state.integrated_modem = true;
}

static void isa_modem_unrealize(DeviceState *dev)
{
    ISASerialState *isa = ISA_SERIAL(dev);

    memory_region_del_subregion(isa_address_space_io(ISA_DEVICE(dev)),
                                &isa->state.io);
    object_unparent(OBJECT(&isa->state.io));
    qdev_unrealize(DEVICE(&isa->state));
    if (isa->owned_modem) {
        object_unparent(OBJECT(isa->owned_modem));
        isa->owned_modem = NULL;
    }
}

/* The modem engine does not yet serialize AT state and pending bytes. */
static const VMStateDescription vmstate_isa_modem = {
    .name = "isa-modem",
    .unmigratable = true,
};

static void isa_modem_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = data;
    dc->hotpluggable = false;
    dc->unrealize = isa_modem_unrealize;
    dc->vmsd = &vmstate_isa_modem;
    set_bit(DEVICE_CATEGORY_NETWORK, dc->categories);
}

static const TypeInfo isa_modem_types[] = {
    {
        .name = "hayes-accura-2400",
        .parent = TYPE_ISA_SERIAL,
        .instance_init = isa_modem_init,
        .class_init = isa_modem_class_init,
        .class_data = "Hayes Accura 2400 ISA modem compatibility profile",
    }, {
        .name = "rockwell-voice-14400",
        .parent = TYPE_ISA_SERIAL,
        .instance_init = isa_modem_init,
        .class_init = isa_modem_class_init,
        .class_data = "Rockwell-compatible 14.4K voice modem ISA profile",
    }, {
        .name = "att-paradyne-dataport-3711",
        .parent = TYPE_ISA_SERIAL,
        .instance_init = isa_modem_init,
        .class_init = isa_modem_class_init,
        .class_data = "Paradyne DataPort Express 3711 ISA compatibility profile",
    }, {
        .name = "att-paradyne-dataport-3740",
        .parent = TYPE_ISA_SERIAL,
        .instance_init = isa_modem_init,
        .class_init = isa_modem_class_init,
        .class_data = "Paradyne DataPort Express 3740 ISA compatibility profile",
    },
};

static void serial_register_types(void)
{
    type_register_static(&serial_isa_info);
    type_register_static(&ins8250a_info);
    type_register_static(&ns16450_info);
    type_register_static(&ns16550a_info);
    type_register_static_array(isa_modem_types, ARRAY_SIZE(isa_modem_types));
}

type_init(serial_register_types)

static void serial_isa_init(ISABus *bus, int index, Chardev *chr)
{
    DeviceState *dev;
    ISADevice *isadev;

    isadev = isa_new(TYPE_ISA_SERIAL);
    dev = DEVICE(isadev);
    qdev_prop_set_uint32(dev, "index", index);
    qdev_prop_set_chr(dev, "chardev", chr);
    isa_realize_and_unref(isadev, bus, &error_fatal);
}

void serial_hds_isa_init(ISABus *bus, int from, int to)
{
    int i;

    assert(from >= 0);
    assert(to <= MAX_ISA_SERIAL_PORTS);

    for (i = from; i < to; ++i) {
        if (serial_hd(i)) {
            serial_isa_init(bus, i, serial_hd(i));
        }
    }
}

void isa_serial_set_iobase(ISADevice *serial, hwaddr iobase)
{
    ISASerialState *s = ISA_SERIAL(serial);

    serial->ioport_id = iobase;
    s->iobase = iobase;
    memory_region_set_address(&s->state.io, s->iobase);
}

void isa_serial_set_enabled(ISADevice *serial, bool enabled)
{
    memory_region_set_enabled(&ISA_SERIAL(serial)->state.io, enabled);
}
