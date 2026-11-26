/*
 * Aztech Sound Galaxy Nova 16 (AZT1605-U05) ISA identification interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Initial probe-only model: the AZT1605 DSP reports version 2.1.
 * The codec, mixer, configuration latches, DMA and IRQ are not implemented.
 * Reference: Linux sound/isa/galaxy/azt1605.c and the Nova 16 board inventory.
 */
#include "qemu/osdep.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "qom/object.h"
#include "qapi/error.h"
#include "hw/isa/isa.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"

#define TYPE_AZTECH_SG_NOVA16 "aztech-sg-nova16"
OBJECT_DECLARE_SIMPLE_TYPE(AztechNova16State, AZTECH_SG_NOVA16)

struct AztechNova16State {
    ISADevice parent_obj;
    MemoryRegion io;
    uint32_t iobase;
    bool reset_asserted;
    uint8_t response[2];
    uint8_t response_count;
};

static void nova16_reset(DeviceState *dev)
{
    AztechNova16State *s = AZTECH_SG_NOVA16(dev);

    s->reset_asserted = false;
    memset(s->response, 0, sizeof(s->response));
    s->response_count = 0;
}

static uint64_t nova16_read(void *opaque, hwaddr addr, unsigned size)
{
    AztechNova16State *s = opaque;
    uint8_t value;

    switch (addr) {
    case 0x0a:
        if (!s->response_count) {
            return 0xff;
        }
        value = s->response[0];
        s->response[0] = s->response[1];
        s->response[1] = 0;
        s->response_count--;
        return value;
    case 0x0c:
        return 0x00; /* Command port ready. */
    case 0x0e:
        return s->response_count ? 0x80 : 0x00;
    default:
        return 0xff;
    }
}

static void nova16_write(void *opaque, hwaddr addr, uint64_t value,
                         unsigned size)
{
    AztechNova16State *s = opaque;

    switch (addr) {
    case 0x06:
        if (value & 1) {
            nova16_reset(DEVICE(s));
            s->reset_asserted = true;
        } else if (s->reset_asserted) {
            s->reset_asserted = false;
            s->response[0] = 0xaa;
            s->response_count = 1;
        }
        break;
    case 0x0c:
        if (value == 0xe1 && !s->reset_asserted) {
            s->response[0] = 2;
            s->response[1] = 1;
            s->response_count = 2;
        } else {
            qemu_log_mask(LOG_UNIMP, "Nova 16: unsupported DSP command 0x%02"
                          PRIx64 "\n", value);
        }
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "Nova 16: unsupported I/O write at offset 0x%"
                      HWADDR_PRIx "\n", addr);
        break;
    }
}

static const MemoryRegionOps nova16_io_ops = {
    .read = nova16_read,
    .write = nova16_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
    .impl = { .min_access_size = 1, .max_access_size = 1 },
};

static void nova16_init(Object *obj)
{
    AztechNova16State *s = AZTECH_SG_NOVA16(obj);

    memory_region_init_io(&s->io, obj, &nova16_io_ops, s,
                          TYPE_AZTECH_SG_NOVA16, 0x10);
}

static void nova16_realize(DeviceState *dev, Error **errp)
{
    AztechNova16State *s = AZTECH_SG_NOVA16(dev);

    switch (s->iobase) {
    case 0x220:
    case 0x240:
    case 0x260:
    case 0x280:
        break;
    default:
        error_setg(errp, "Nova 16 I/O base must be 0x220, 0x240, 0x260 or 0x280");
        return;
    }

    isa_register_ioport(ISA_DEVICE(dev), &s->io, s->iobase);
}

static int nova16_post_load(void *opaque, int version_id)
{
    AztechNova16State *s = opaque;

    return s->response_count <= sizeof(s->response) ? 0 : -EINVAL;
}

static const VMStateDescription vmstate_nova16 = {
    .name = TYPE_AZTECH_SG_NOVA16,
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = nova16_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(reset_asserted, AztechNova16State),
        VMSTATE_UINT8_ARRAY(response, AztechNova16State, 2),
        VMSTATE_UINT8(response_count, AztechNova16State),
        VMSTATE_END_OF_LIST()
    },
};

static const Property nova16_properties[] = {
    DEFINE_PROP_UINT32("iobase", AztechNova16State, iobase, 0x220),
};

static void nova16_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = nova16_realize;
    device_class_set_legacy_reset(dc, nova16_reset);
    dc->vmsd = &vmstate_nova16;
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
    dc->desc = "Aztech Sound Galaxy Nova 16 (experimental DSP probe only)";
    device_class_set_props(dc, nova16_properties);
}

static const TypeInfo nova16_info = {
    .name = TYPE_AZTECH_SG_NOVA16,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(AztechNova16State),
    .instance_init = nova16_init,
    .class_init = nova16_class_init,
};

static void nova16_register_types(void)
{
    type_register_static(&nova16_info);
}

type_init(nova16_register_types)
