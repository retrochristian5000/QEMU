/*
 * IBM-compatible analog ISA game control adapter.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * IBM PC Technical Reference (August 1981), pp. 2-117 through 2-122:
 * four resistance-to-time converters, four active-low button inputs.
 * Creative's legacy SB16 uses the same programming interface.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qapi/error.h"
#include "hw/isa/isa.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"

#define TYPE_ISA_GAMEPORT "isa-gameport"
OBJECT_DECLARE_SIMPLE_TYPE(ISAGameportState, ISA_GAMEPORT)

#define GAMEPORT_BASE 0x201
#define GAMEPORT_MAX_OHMS 100000U

struct ISAGameportState {
    ISADevice parent_obj;
    MemoryRegion io;
    uint32_t resistance[4];
    uint8_t connected;
    uint8_t buttons;
    int64_t trigger_ns;
    bool triggered;
};

static uint64_t gameport_read(void *opaque, hwaddr addr, unsigned size)
{
    ISAGameportState *s = opaque;
    int64_t now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    uint64_t elapsed = now >= s->trigger_ns ?
                       (uint64_t)now - (uint64_t)s->trigger_ns : 0;
    uint8_t result = ((~s->buttons & 0xf) << 4) | (~s->connected & 0xf);

    if (s->triggered) {
        for (unsigned i = 0; i < 4; i++) {
            /* T = 24.2 us + 0.011 us/ohm * R; no host-time dependency. */
            uint32_t duration_ns = 24200 + 11 * s->resistance[i];

            if ((s->connected & (1U << i)) && elapsed < duration_ns) {
                result |= 1U << i;
            }
        }
    }
    return result;
}

static void gameport_write(void *opaque, hwaddr addr, uint64_t value,
                           unsigned size)
{
    ISAGameportState *s = opaque;

    /* Every byte write starts all four converters, regardless of value. */
    s->trigger_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    s->triggered = true;
}

static const MemoryRegionOps gameport_ops = {
    .read = gameport_read,
    .write = gameport_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
};

static void gameport_reset(DeviceState *dev)
{
    ISAGameportState *s = ISA_GAMEPORT(dev);

    s->trigger_ns = 0;
    s->triggered = false;
}

static const VMStateDescription vmstate_gameport = {
    .name = "isa-gameport",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_INT64(trigger_ns, ISAGameportState),
        VMSTATE_BOOL(triggered, ISAGameportState),
        VMSTATE_END_OF_LIST()
    },
};

static void gameport_realize(DeviceState *dev, Error **errp)
{
    ISAGameportState *s = ISA_GAMEPORT(dev);
    ISADevice *isa = ISA_DEVICE(dev);

    if (s->connected > 0xf || s->buttons > 0xf) {
        error_setg(errp, "Gameport connection and button masks must be 0-15");
        return;
    }
    for (unsigned i = 0; i < 4; i++) {
        if (s->resistance[i] > GAMEPORT_MAX_OHMS) {
            error_setg(errp, "Gameport axis %u resistance must be 0-100000 ohms",
                       i);
            return;
        }
    }
    if (!isa_ioport_range_available(isa, GAMEPORT_BASE, 1, errp)) {
        return;
    }

    memory_region_init_io(&s->io, OBJECT(s), &gameport_ops, s,
                          "isa-gameport", 1);
    isa_register_ioport(isa, &s->io, GAMEPORT_BASE);
}

static const Property gameport_properties[] = {
    DEFINE_PROP_UINT8("connected", ISAGameportState, connected, 0),
    DEFINE_PROP_UINT8("buttons", ISAGameportState, buttons, 0),
    DEFINE_PROP_UINT32("a-x", ISAGameportState, resistance[0], 50000),
    DEFINE_PROP_UINT32("a-y", ISAGameportState, resistance[1], 50000),
    DEFINE_PROP_UINT32("b-x", ISAGameportState, resistance[2], 50000),
    DEFINE_PROP_UINT32("b-y", ISAGameportState, resistance[3], 50000),
};

static void gameport_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Generic ISA analog gameport (0x201)";
    dc->realize = gameport_realize;
    dc->hotpluggable = false;
    dc->vmsd = &vmstate_gameport;
    device_class_set_legacy_reset(dc, gameport_reset);
    device_class_set_props(dc, gameport_properties);
    set_bit(DEVICE_CATEGORY_INPUT, dc->categories);
}

static void gameport_profile_class_init(ObjectClass *klass, const void *data)
{
    DEVICE_CLASS(klass)->desc = data;
}

static const TypeInfo gameport_types[] = {
    {
        .name = TYPE_ISA_GAMEPORT,
        .parent = TYPE_ISA_DEVICE,
        .instance_size = sizeof(ISAGameportState),
        .class_init = gameport_class_init,
    }, {
        .name = "ibm-game-control",
        .parent = TYPE_ISA_GAMEPORT,
        .class_init = gameport_profile_class_init,
        .class_data = "IBM PC Game Control Adapter (analog interface)",
    }, {
        .name = "creative-gameport",
        .parent = TYPE_ISA_GAMEPORT,
        .class_init = gameport_profile_class_init,
        .class_data = "Creative Sound Blaster compatible analog gameport",
    },
};

DEFINE_TYPES(gameport_types)
