/*
 * Weitek 4167 floating-point coprocessor stub
 *
 * The 4167 is a memory-mapped coprocessor for 80486-class systems. Its
 * address lines participate in operation decoding, so unaligned MMIO accesses
 * must reach the device without QEMU normalizing the operation address.
 *
 * This model currently implements the package/bus-facing shape only: physical
 * address decode, data transfers, byte-lane information, reset, interrupt
 * output, and firmware presence. Arithmetic and register semantics remain
 * intentionally unimplemented until the complete instruction encoding is
 * sourced.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "hw/i386/weitek4167.h"
#include "hw/nvram/fw_cfg.h"
#include "qemu/log.h"
#include "qemu/module.h"

struct Weitek4167State {
    SysBusDevice parent_obj;

    MemoryRegion mmio;
    qemu_irq irq;
};

static hwaddr weitek4167_program_offset(hwaddr offset)
{
    /* A24..A16 are not decoded by the coprocessor programming interface. */
    return offset & WEITEK4167_PROGRAM_MASK;
}

static uint64_t weitek4167_read(void *opaque, hwaddr offset, unsigned size)
{
    hwaddr program_offset = weitek4167_program_offset(offset);

    qemu_log_mask(LOG_UNIMP,
                  "weitek4167: unimplemented memory read "
                  "(size %u, phys 0x%08" HWADDR_PRIx
                  ", program 0x%04" HWADDR_PRIx ")\n",
                  size, WEITEK4167_MMIO_BASE + offset, program_offset);

    return 0;
}

static void weitek4167_write(void *opaque, hwaddr offset,
                             uint64_t value, unsigned size)
{
    hwaddr program_offset = weitek4167_program_offset(offset);

    qemu_log_mask(LOG_UNIMP,
                  "weitek4167: unimplemented memory write "
                  "(size %u, phys 0x%08" HWADDR_PRIx
                  ", program 0x%04" HWADDR_PRIx
                  ", value 0x%08" PRIx64 ")\n",
                  size, WEITEK4167_MMIO_BASE + offset, program_offset, value);
}

static const MemoryRegionOps weitek4167_ops = {
    .read = weitek4167_read,
    .write = weitek4167_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        /* 80486 byte-enable signals select the active data lanes. */
        .min_access_size = 1,
        .max_access_size = 4,
        .unaligned = true,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 4,
        .unaligned = true,
    },
};

static void weitek4167_reset(DeviceState *dev)
{
    Weitek4167State *s = WEITEK4167(dev);

    /* RESET deasserts the coprocessor interrupt output. */
    qemu_set_irq(s->irq, 0);
}

static void weitek4167_realize(DeviceState *dev, Error **errp)
{
    FWCfgState *fw_cfg = fw_cfg_find();

    /* PRES# is represented to the PC firmware by a fw_cfg presence file. */
    if (fw_cfg) {
        uint32_t *present = g_new(uint32_t, 1);

        *present = cpu_to_le32(1);
        fw_cfg_add_file(fw_cfg, "etc/weitek4167", present, sizeof(*present));
    }
}

static void weitek4167_init(Object *obj)
{
    Weitek4167State *s = WEITEK4167(obj);

    /* M/IO# is memory-only: the 4167 has no legacy port-I/O register block. */
    memory_region_init_io(&s->mmio, obj, &weitek4167_ops, s,
                          TYPE_WEITEK4167, WEITEK4167_MMIO_SIZE);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->mmio);

    /* INTR is connected by the PC board to the AT-compatible IRQ13 path. */
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
}

static void weitek4167_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = weitek4167_realize;
    device_class_set_legacy_reset(dc, weitek4167_reset);
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);

    /* The board must map the decode aperture and wire INTR correctly. */
    dc->user_creatable = false;
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
