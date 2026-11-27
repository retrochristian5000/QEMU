/*
 * SST39SF010A, SST39SF020A and SST39SF040 parallel flash.
 * Reference: Microchip DS20005022F, sections 3 and 4.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "hw/core/sysbus.h"
#include "hw/core/loader.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"

#define TYPE_SST39SF "sst39sf"
OBJECT_DECLARE_TYPE(SST39SFState, SST39SFClass, SST39SF)

#define SST_SECTOR_SIZE (4 * KiB)
#define SST_UNLOCK_MASK 0x7fff
#define SST_UNLOCK1 0x5555
#define SST_UNLOCK2 0x2aaa

enum {
    SST_IDLE, SST_UNLOCKED1, SST_UNLOCKED2, SST_PROGRAM,
    SST_ERASE1, SST_ERASE2, SST_ERASE3,
};

struct SST39SFClass {
    SysBusDeviceClass parent_class;
    uint32_t capacity;
    uint8_t device_id;
};

struct SST39SFState {
    SysBusDevice parent_obj;
    MemoryRegion mem;
    uint8_t *storage;
    char *image;
    uint8_t sequence;
    bool identification;
    bool toggle;
    uint8_t poll_data;
    int64_t busy_until;
};

static void sst_update_romd(SST39SFState *s)
{
    memory_region_rom_device_set_romd(&s->mem,
                                      !s->identification && !s->busy_until);
}

static bool sst_busy(SST39SFState *s)
{
    if (s->busy_until &&
        qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) >= s->busy_until) {
        s->busy_until = 0;
        sst_update_romd(s);
    }
    return s->busy_until != 0;
}

static void sst_start_busy(SST39SFState *s, uint8_t data, int64_t duration)
{
    s->sequence = SST_IDLE;
    s->identification = false;
    s->toggle = false;
    s->poll_data = data;
    s->busy_until = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + duration;
    sst_update_romd(s);
}

static uint64_t sst_read(void *opaque, hwaddr addr, unsigned size)
{
    SST39SFState *s = opaque;
    SST39SFClass *sc = SST39SF_GET_CLASS(s);

    if (sst_busy(s)) {
        s->toggle = !s->toggle;
        return ((~s->poll_data) & 0x80) | (s->toggle ? 0x40 : 0);
    }
    if (s->identification) {
        if (addr == 0) {
            return 0xbf;
        }
        if (addr == 1) {
            return sc->device_id;
        }
        return 0xff;
    }
    return s->storage[addr];
}

static void sst_write(void *opaque, hwaddr addr, uint64_t value,
                      unsigned size)
{
    SST39SFState *s = opaque;
    SST39SFClass *sc = SST39SF_GET_CLASS(s);
    hwaddr cmd_addr = addr & SST_UNLOCK_MASK;
    uint8_t data = value;
    hwaddr offset;

    if (sst_busy(s)) {
        return;
    }
    /* A program data byte may itself be F0h. */
    if (s->sequence != SST_PROGRAM && data == 0xf0) {
        s->sequence = SST_IDLE;
        s->identification = false;
        sst_update_romd(s);
        return;
    }

    switch (s->sequence) {
    case SST_IDLE:
        if (cmd_addr == SST_UNLOCK1 && data == 0xaa) {
            s->sequence = SST_UNLOCKED1;
        }
        return;
    case SST_UNLOCKED1:
        if (cmd_addr == SST_UNLOCK2 && data == 0x55) {
            s->sequence = SST_UNLOCKED2;
            return;
        }
        break;
    case SST_UNLOCKED2:
        if (cmd_addr != SST_UNLOCK1) {
            break;
        }
        if (data == 0x90) {
            s->identification = true;
            s->sequence = SST_IDLE;
            sst_update_romd(s);
            return;
        }
        if (!s->identification && data == 0xa0) {
            s->sequence = SST_PROGRAM;
            return;
        }
        if (!s->identification && data == 0x80) {
            s->sequence = SST_ERASE1;
            return;
        }
        break;
    case SST_PROGRAM:
        /* NOR programming can only clear bits; erase restores ones. */
        s->storage[addr] &= data;
        memory_region_flush_rom_device(&s->mem, addr, 1);
        sst_start_busy(s, data, 14000);
        return;
    case SST_ERASE1:
        if (cmd_addr == SST_UNLOCK1 && data == 0xaa) {
            s->sequence = SST_ERASE2;
            return;
        }
        break;
    case SST_ERASE2:
        if (cmd_addr == SST_UNLOCK2 && data == 0x55) {
            s->sequence = SST_ERASE3;
            return;
        }
        break;
    case SST_ERASE3:
        if (data == 0x30) {
            offset = addr & ~(hwaddr)(SST_SECTOR_SIZE - 1);
            memset(s->storage + offset, 0xff, SST_SECTOR_SIZE);
            memory_region_flush_rom_device(&s->mem, offset, SST_SECTOR_SIZE);
            sst_start_busy(s, 0xff, 18 * SCALE_MS);
            return;
        }
        if (cmd_addr == SST_UNLOCK1 && data == 0x10) {
            memset(s->storage, 0xff, sc->capacity);
            memory_region_flush_rom_device(&s->mem, 0, sc->capacity);
            sst_start_busy(s, 0xff, 70 * SCALE_MS);
            return;
        }
        break;
    }
    s->sequence = SST_IDLE;
    s->identification = false;
    sst_update_romd(s);
}

static const MemoryRegionOps sst_ops = {
    .read = sst_read,
    .write = sst_write,
    .endianness = DEVICE_NATIVE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 4 },
    .impl = { .min_access_size = 1, .max_access_size = 1 },
};

static void sst_reset(DeviceState *dev)
{
    SST39SFState *s = SST39SF(dev);

    s->sequence = SST_IDLE;
    s->identification = false;
    s->busy_until = 0;
    s->toggle = false;
    sst_update_romd(s);
}

static int sst_post_load(void *opaque, int version)
{
    SST39SFState *s = opaque;

    if (s->sequence > SST_ERASE3 || s->busy_until < 0) {
        return -EINVAL;
    }
    sst_update_romd(s);
    return 0;
}

static const VMStateDescription vmstate_sst = {
    .name = "sst39sf",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = sst_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(sequence, SST39SFState),
        VMSTATE_BOOL(identification, SST39SFState),
        VMSTATE_BOOL(toggle, SST39SFState),
        VMSTATE_UINT8(poll_data, SST39SFState),
        VMSTATE_INT64(busy_until, SST39SFState),
        VMSTATE_END_OF_LIST()
    },
};

static void sst_realize(DeviceState *dev, Error **errp)
{
    SST39SFState *s = SST39SF(dev);
    SST39SFClass *sc = SST39SF_GET_CLASS(s);
    g_autofree char *image = NULL;
    gsize size = 0;
    GError *error = NULL;

    if (s->image) {
        int64_t len = get_image_size(s->image, errp);

        if (len < 0) {
            return;
        }
        if (!len || len > sc->capacity) {
            error_setg(errp, "BIOS image must fit the %u-byte SST ROM chip",
                       sc->capacity);
            return;
        }
        if (!g_file_get_contents(s->image, &image, &size, &error)) {
            error_setg(errp, "Could not read SST ROM image: %s", error->message);
            g_error_free(error);
            return;
        }
        if (size != len) {
            error_setg(errp, "SST ROM image size changed while loading");
            return;
        }
    }

    if (!memory_region_init_rom_device(&s->mem, OBJECT(dev), &sst_ops, s,
                                       "sst39sf.array", sc->capacity, errp)) {
        return;
    }
    s->storage = memory_region_get_ram_ptr(&s->mem);
    memset(s->storage, 0xff, sc->capacity);
    if (image) {
        /* Right-align the firmware so the x86 reset vector stays at the top. */
        memcpy(s->storage + sc->capacity - size, image, size);
    }
    sysbus_init_mmio(SYS_BUS_DEVICE(dev), &s->mem);
}

static const Property sst_properties[] = {
    DEFINE_PROP_STRING("image", SST39SFState, image),
};

static void sst_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = sst_realize;
    dc->vmsd = &vmstate_sst;
    dc->user_creatable = false;
    device_class_set_legacy_reset(dc, sst_reset);
    device_class_set_props(dc, sst_properties);
}

typedef struct SST39SFGeometry {
    uint32_t capacity;
    uint8_t id;
} SST39SFGeometry;

static const SST39SFGeometry geometry[] = {
    { 128 * KiB, 0xb5 },
    { 256 * KiB, 0xb6 },
    { 512 * KiB, 0xb7 },
};

static void sst_model_class_init(ObjectClass *oc, const void *data)
{
    SST39SFClass *sc = SST39SF_CLASS(oc);
    const SST39SFGeometry *g = data;

    sc->capacity = g->capacity;
    sc->device_id = g->id;
}

static const TypeInfo sst_types[] = {
    {
        .name = TYPE_SST39SF,
        .parent = TYPE_SYS_BUS_DEVICE,
        .instance_size = sizeof(SST39SFState),
        .class_size = sizeof(SST39SFClass),
        .abstract = true,
        .class_init = sst_class_init,
    }, {
        .name = "sst39sf010a",
        .parent = TYPE_SST39SF,
        .class_init = sst_model_class_init,
        .class_data = (void *)&geometry[0],
    }, {
        .name = "sst39sf020a",
        .parent = TYPE_SST39SF,
        .class_init = sst_model_class_init,
        .class_data = (void *)&geometry[1],
    }, {
        .name = "sst39sf040",
        .parent = TYPE_SST39SF,
        .class_init = sst_model_class_init,
        .class_data = (void *)&geometry[2],
    },
};
DEFINE_TYPES(sst_types)
