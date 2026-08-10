/*
 * Weitek 4167 floating-point coprocessor stub
 *
 * The 4167 is a memory-mapped coprocessor for 80486-class systems.  Its
 * address lines participate in operation decoding, so unaligned 32-bit MMIO
 * accesses must reach the device as a single transaction.  This initial
 * model only reserves the device shape and logs accesses; arithmetic and
 * register semantics are intentionally left unimplemented.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "hw/i386/weitek4167.h"
#include "qemu/log.h"
#include "qemu/module.h"

struct Weitek4167State {
    SysBusDevice parent_obj;

    MemoryRegion mmio;
    qemu_irq irq;
};

static uint64_t weitek4167_read(void *opaque, hwaddr offset, unsigned size)
{
    qemu_log_mask(LOG_UNIMP,
                  "weitek4167: unimplemented read "
                  "(size %u, offset 0x%08" HWADDR_PRIx ")\n",
                  size, offset);

    return 0;
}

static void weitek4167_write(void *opaque, hwaddr offset,
                             uint64_t value, unsigned size)
{
    qemu_log_mask(LOG_UNIMP,
                  "weitek4167: unimplemented write "
                  "(size %u, offset 0x%08" HWADDR_PRIx
                  ", value 0x%08" PRIx64 ")\n",
                  size, offset, value);
}

static const MemoryRegionOps weitek4167_ops = {
    .read = weitek4167_read,
    .write = weitek4167_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 4,
        .max_access_size = 4,
        .unaligned = true,
    },
    .impl = {
        .min_access_size = 4,
        .max_access_size = 4,
        .unaligned = true,
    },
};

static void weitek4167_init(Object *obj)
{
    Weitek4167State *s = WEITEK4167(obj);

    memory_region_init_io(&s->mmio, obj, &weitek4167_ops, s,
                          TYPE_WEITEK4167, WEITEK4167_MMIO_SIZE);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->mmio);
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
}

static void weitek4167_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
}

static const TypeInfo weitek4167_info = {
    .name = TYPE_WEITEK4167,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Weitek4167State),
    .instance_init = weitek4167_init,
    .class_init = weitek4167_class_init,
};

static void weitek4167_register_types(void)
{
    type_register_static(&weitek4167_info);
}

type_init(weitek4167_register_types)
