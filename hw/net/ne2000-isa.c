/*
 * QEMU NE2000 emulation -- isa bus windup
 *
 * Copyright (c) 2003-2004 Fabrice Bellard
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
#include "hw/isa/isa.h"
#include "hw/net/ne2000-isa.h"
#include "migration/vmstate.h"
#include "ne2000.h"
#include "system/system.h"
#include "qapi/error.h"
#include "qapi/visitor.h"
#include "qemu/module.h"
#include "qemu/error-report.h"
#include "system/memory.h"
#include "qom/object.h"

OBJECT_DECLARE_SIMPLE_TYPE(ISANE2000State, ISA_NE2000)

#define NE2000_ISA_IO_SIZE 0x20
#define NE2000_ISA_RESET_CMD 0x21 /* Stop, abort remote DMA, page 0. */

struct ISANE2000State {
    ISADevice parent_obj;

    uint32_t iobase;
    uint32_t isairq;
    NE2000State ne2000;
};

static NetClientInfo net_ne2000_isa_info = {
    .type = NET_CLIENT_DRIVER_NIC,
    .size = sizeof(NICState),
    .receive = ne2000_receive,
};

static const VMStateDescription vmstate_isa_ne2000 = {
    .name = "ne2000",
    .version_id = 2,
    .minimum_version_id = 0,
    .fields = (const VMStateField[]) {
        VMSTATE_STRUCT(ne2000, ISANE2000State, 0, vmstate_ne2000, NE2000State),
        VMSTATE_END_OF_LIST()
    }
};

static void isa_ne2000_reset_hold(Object *obj, ResetType type)
{
    ISANE2000State *isa = ISA_NE2000(obj);
    NE2000State *s = &isa->ne2000;

    /* A bus reset leaves the controller stopped with interrupts masked. */
    s->cmd = NE2000_ISA_RESET_CMD;
    s->imr = 0;
    ne2000_reset(s);
}

static void isa_ne2000_realizefn(DeviceState *dev, Error **errp)
{
    ISADevice *isadev = ISA_DEVICE(dev);
    ISANE2000State *isa = ISA_NE2000(dev);
    NE2000State *s = &isa->ne2000;
    ISABus *bus = isa_bus_from_device(isadev);

    DeviceState *bridge = BUS(bus)->parent;
    bool piix = bridge && object_dynamic_cast(OBJECT(bridge), "pci-piix");

    /* PIIX SCI occupies IRQ9. The matching firmware reserves NIC IRQ10
     * from PCI steering via etc/isa-ne2000-irq-mask. */
    if (isa->isairq == UINT32_MAX) {
        isa->isairq = piix ? 10 : 9;
    }

    if (isa->iobase > UINT16_MAX - (NE2000_ISA_IO_SIZE - 1)) {
        error_setg(errp, "NE2000 ISA I/O base 0x%x exceeds the ISA port range",
                   isa->iobase);
        return;
    }
    if (isa->iobase & (NE2000_ISA_IO_SIZE - 1)) {
        error_setg(errp, "NE2000 ISA I/O base 0x%x must be aligned to 0x20",
                   isa->iobase);
        return;
    }
    /*
     * Generic NE2000-compatible ISA adapters support more IRQ choices
     * than the original Eagle board. IRQ2 on an AT is the cascade,
     * not an independent ISA interrupt input; use IRQ9 instead.
     */
    switch (isa->isairq) {
    case 3: case 4: case 5: case 9: case 10: case 11:
    case 12: case 14: case 15:
        break;
    default:
        error_setg(errp, "NE2000 ISA IRQ %u is unsupported; use "
                   "3, 4, 5, 9, 10, 11, 12, 14 or 15 (IRQ2 is IRQ9 on AT)",
                   isa->isairq);
        return;
    }
    if (!bus->irqs_in || !bus->irqs_in[isa->isairq]) {
        error_setg(errp, "NE2000 ISA IRQ %u is not connected on this bus",
                   isa->isairq);
        return;
    }

    /*
     * The system I/O root is itself a terminating fallback region for
     * unassigned ports. It is not a device conflict. Check every port
     * so an unassigned prefix cannot hide a later occupied subrange.
     * This checks current decoding, not future BAR or device mappings.
     */
    for (unsigned offset = 0; offset < NE2000_ISA_IO_SIZE; offset++) {
        MemoryRegionSection section = memory_region_find(
            bus->address_space_io, isa->iobase + offset, 1);

        if (!section.mr) {
            continue;
        }
        if (section.mr != bus->address_space_io) {
            error_setg(errp, "NE2000 ISA I/O range 0x%x-0x%x overlaps '%s' "
                       "at port 0x%x",
                       isa->iobase, isa->iobase + NE2000_ISA_IO_SIZE - 1,
                       memory_region_name(section.mr), isa->iobase + offset);
            memory_region_unref(section.mr);
            return;
        }
        memory_region_unref(section.mr);
    }

    /*
     * PIIX3/4 machines can have a PIIX4 PM function connected to IRQ9.
     * Keep the user's fixed ISA jumper setting, but report the conflict
     * rather than silently relocating the adapter.
     */
    if (isa->isairq == 9 && piix &&
        object_resolve_path_component(OBJECT(bridge), "pm")) {
        warn_report("NE2000 ISA IRQ9 shares the PIIX ACPI SCI line; "
                    "select an unused ISA IRQ and match the guest driver");
    }

    s->irq = isa_bus_get_irq(bus, isa->isairq);
    ne2000_setup_io(s, dev, NE2000_ISA_IO_SIZE);
    isa_register_ioport(isadev, &s->io, isa->iobase);

    qemu_macaddr_default_if_unset(&s->c.macaddr);
    ne2000_reset(s);

    s->nic = qemu_new_nic(&net_ne2000_isa_info, &s->c,
                          object_get_typename(OBJECT(dev)), dev->id,
                          &dev->mem_reentrancy_guard, s);
    qemu_format_nic_info_str(qemu_get_queue(s->nic), s->c.macaddr.a);
}

static const Property ne2000_isa_properties[] = {
    DEFINE_PROP_UINT32("iobase", ISANE2000State, iobase, 0x300),
    DEFINE_PROP_UINT32("irq",   ISANE2000State, isairq, UINT32_MAX),
    DEFINE_NIC_PROPERTIES(ISANE2000State, ne2000.c),
};

static void isa_ne2000_class_initfn(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    rc->phases.hold = isa_ne2000_reset_hold;
    dc->desc = "NE2000-compatible ISA Ethernet adapter";
    dc->realize = isa_ne2000_realizefn;
    device_class_set_props(dc, ne2000_isa_properties);
    dc->vmsd = &vmstate_isa_ne2000;
    set_bit(DEVICE_CATEGORY_NETWORK, dc->categories);
}

static void isa_ne2000_get_bootindex(Object *obj, Visitor *v,
                                     const char *name, void *opaque,
                                     Error **errp)
{
    ISANE2000State *isa = ISA_NE2000(obj);
    NE2000State *s = &isa->ne2000;

    visit_type_int32(v, name, &s->c.bootindex, errp);
}

static void isa_ne2000_set_bootindex(Object *obj, Visitor *v,
                                     const char *name, void *opaque,
                                     Error **errp)
{
    ISANE2000State *isa = ISA_NE2000(obj);
    NE2000State *s = &isa->ne2000;
    int32_t boot_index;
    Error *local_err = NULL;

    if (!visit_type_int32(v, name, &boot_index, errp)) {
        return;
    }
    /* check whether bootindex is present in fw_boot_order list  */
    check_boot_index(boot_index, &local_err);
    if (local_err) {
        goto out;
    }
    /* change bootindex to a new one */
    s->c.bootindex = boot_index;

out:
    error_propagate(errp, local_err);
}

static void isa_ne2000_instance_init(Object *obj)
{
    object_property_add(obj, "bootindex", "int32",
                        isa_ne2000_get_bootindex,
                        isa_ne2000_set_bootindex, NULL, NULL);
    object_property_set_int(obj, "bootindex", -1, NULL);
}
static const TypeInfo ne2000_isa_info = {
    .name          = TYPE_ISA_NE2000,
    .parent        = TYPE_ISA_DEVICE,
    .instance_size = sizeof(ISANE2000State),
    .class_init    = isa_ne2000_class_initfn,
    .instance_init = isa_ne2000_instance_init,
};

static void ne2000_isa_register_types(void)
{
    type_register_static(&ne2000_isa_info);
}

type_init(ne2000_isa_register_types)
