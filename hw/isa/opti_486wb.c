/*
 * OPTi 486WB PC/AT chipset - 82C491 indexed configuration registers.
 * Three physical chips: 82C491 SYSC, 82C392 DBC and 82C206 IPC.
 * Timing, shadow/cache mapping and physical DBC effects are not modeled.
 * Source: OPTi 82C491/82C392 Data Book, 26 April 1991, chapter 4.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "hw/core/sysbus.h"
#include "hw/isa/isa.h"
#include "hw/isa/opti_486wb.h"
#include "migration/vmstate.h"
#include "system/address-spaces.h"
#include "system/system.h"

#define REG_FIRST 0x20
#define REG_COUNT 12

OBJECT_DECLARE_SIMPLE_TYPE(OPTi486WBState, OPTI_486WB)
struct OPTi486WBState {
    SysBusDevice parent_obj;
    MemoryRegion index_io, data_io;
    uint8_t index;
    bool selected;
    uint8_t regs[REG_COUNT];
};

static const uint8_t masks[REG_COUNT] = {
    0x1f, 0xff, 0xfd, 0xff, 0xff, 0xfb,
    0x7f, 0x9f, 0xe3, 0xff, 0xe3, 0xff
};

static uint64_t idx_read(void *opaque, hwaddr addr, unsigned size)
{
    /* Index port is specified only for writes. */
    return 0xff;
}

static void idx_write(void *opaque, hwaddr addr, uint64_t val,
                      unsigned size)
{
    OPTi486WBState *s = opaque;
    s->index = val;
    s->selected = val >= REG_FIRST && val < REG_FIRST + REG_COUNT;
}

static uint64_t data_read(void *opaque, hwaddr addr, unsigned size)
{
    OPTi486WBState *s = opaque;
    uint8_t v = s->selected ? s->regs[s->index - REG_FIRST] : 0xff;
    s->selected = false;
    return v;
}

static void data_write(void *opaque, hwaddr addr, uint64_t val,
                       unsigned size)
{
    OPTi486WBState *s = opaque;
    if (s->selected) {
        unsigned n = s->index - REG_FIRST;
        s->regs[n] = (s->regs[n] & ~masks[n]) | (val & masks[n]);
    }
    s->selected = false;
}

static const MemoryRegionOps idx_ops = {
    .read = idx_read, .write = idx_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
};
static const MemoryRegionOps data_ops = {
    .read = data_read, .write = data_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
};

static void opti_reset(DeviceState *dev)
{
    OPTi486WBState *s = OPTI_486WB(dev);
    memset(s->regs, 0, sizeof(s->regs));
    s->index = 0;
    s->selected = false;
    /* Datasheet defaults; 29h/2Bh low don't-care bits set to zero. */
    s->regs[0x22 - REG_FIRST] = 0x84;
    s->regs[0x24 - REG_FIRST] = 0x87;
    s->regs[0x25 - REG_FIRST] = 0xf0; /* BCLKS strapped low */
    s->regs[0x27 - REG_FIRST] = 0x91;
    s->regs[0x28 - REG_FIRST] = 0x80;
    s->regs[0x29 - REG_FIRST] = 0x10;
    s->regs[0x2a - REG_FIRST] = 0x80;
    s->regs[0x2b - REG_FIRST] = 0x10;
}

static const VMStateDescription vmstate_opti = {
    .name = "opti-486wb", .version_id = 1, .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(index, OPTi486WBState),
        VMSTATE_BOOL(selected, OPTi486WBState),
        VMSTATE_UINT8_ARRAY(regs, OPTi486WBState, REG_COUNT),
        VMSTATE_END_OF_LIST()
    },
};

static void opti_realize(DeviceState *dev, Error **errp)
{
    OPTi486WBState *s = OPTI_486WB(dev);
    if (!isa_bus_new(dev, get_system_memory(), get_system_io(), errp)) {
        return;
    }
    memory_region_init_io(&s->index_io, OBJECT(dev), &idx_ops, s,
                          "opti-486wb-index", 1);
    memory_region_init_io(&s->data_io, OBJECT(dev), &data_ops, s,
                          "opti-486wb-data", 1);
    memory_region_add_subregion(get_system_io(), 0x22, &s->index_io);
    memory_region_add_subregion(get_system_io(), 0x24, &s->data_io);
}

static void opti_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    dc->realize = opti_realize;
    dc->vmsd = &vmstate_opti;
    dc->desc = "OPTi 486WB AT chipset (initial 82C491 model)";
    dc->user_creatable = false;
    device_class_set_legacy_reset(dc, opti_reset);
}

static const TypeInfo opti_info = {
    .name = TYPE_OPTI_486WB, .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(OPTi486WBState),
    .class_init = opti_class_init,
};

static void opti_register(void)
{
    type_register_static(&opti_info);
}
type_init(opti_register)
