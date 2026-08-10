/*
 * Extended Industry Standard Architecture (EISA) bus
 *
 * EISA is an ISA-compatible bus.  Each logical slot owns a 4 KiB I/O
 * window and exposes its compressed four-byte product identifier at +0xc80
 * followed by the board control register at +0xc84.
 *
 * This initial model implements the standardized enumeration/control layer.
 * Enhanced EISA DMA, arbitration and burst timing are separate pieces of the
 * architecture and are intentionally not synthesized here.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "hw/isa/eisa.h"
#include "qapi/error.h"
#include "qemu/module.h"

static uint8_t eisa_slot_read_byte(EISASlotState *slot, hwaddr offset)
{
    if (!slot->present) {
        return 0xff;
    }

    if (offset < 4) {
        return slot->id[offset];
    }
    if (offset == 4) {
        return slot->control;
    }

    return 0xff;
}

static uint64_t eisa_slot_read(void *opaque, hwaddr offset, unsigned size)
{
    EISASlotState *slot = opaque;
    uint64_t value = 0;
    unsigned i;

    for (i = 0; i < size; i++) {
        value |= (uint64_t)eisa_slot_read_byte(slot, offset + i) << (i * 8);
    }

    return value;
}

static void eisa_slot_write(void *opaque, hwaddr offset,
                            uint64_t value, unsigned size)
{
    EISASlotState *slot = opaque;
    unsigned i;

    if (!slot->present) {
        return;
    }

    for (i = 0; i < size; i++) {
        hwaddr byte_offset = offset + i;

        if (byte_offset == 4) {
            /* BCTL ENABLE is the standardized software-visible R/W bit. */
            slot->control = (value >> (i * 8)) & EISA_CONFIG_ENABLED;
        }
    }
}

static const MemoryRegionOps eisa_slot_ops = {
    .read = eisa_slot_read,
    .write = eisa_slot_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
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

static int eisa_hex_value(char ch)
{
    if (ch >= '0' && ch <= '9') {
        return ch - '0';
    }
    if (ch >= 'A' && ch <= 'F') {
        return ch - 'A' + 10;
    }
    if (ch >= 'a' && ch <= 'f') {
        return ch - 'a' + 10;
    }
    return -1;
}

static bool eisa_encode_id(const char *id, uint8_t encoded[4], Error **errp)
{
    unsigned mfr[3];
    unsigned product = 0;
    int nibble;
    int i;

    if (!id || strlen(id) != 7) {
        error_setg(errp, "EISA ID must contain three letters and four hex digits");
        return false;
    }

    for (i = 0; i < 3; i++) {
        if (id[i] < 'A' || id[i] > 'Z') {
            error_setg(errp, "EISA manufacturer code '%.*s' is invalid", 3, id);
            return false;
        }
        mfr[i] = id[i] - 'A' + 1;
    }

    for (i = 3; i < 7; i++) {
        nibble = eisa_hex_value(id[i]);
        if (nibble < 0) {
            error_setg(errp, "EISA product code '%s' is invalid", id + 3);
            return false;
        }
        product = (product << 4) | nibble;
    }

    encoded[0] = (mfr[0] << 2) | (mfr[1] >> 3);
    encoded[1] = ((mfr[1] & 0x7) << 5) | mfr[2];
    encoded[2] = product >> 8;
    encoded[3] = product;
    return true;
}

bool eisa_bus_set_slot_id(EISABus *bus, unsigned slot, const char *id,
                          bool enabled, Error **errp)
{
    EISASlotState *s;
    uint8_t encoded[4];

    if (slot >= EISA_MAX_SLOTS) {
        error_setg(errp, "EISA slot %u is out of range", slot);
        return false;
    }
    if (!eisa_encode_id(id, encoded, errp)) {
        return false;
    }

    s = &bus->slots[slot];
    memcpy(s->id, encoded, sizeof(s->id));
    s->present = true;
    s->control = enabled ? EISA_CONFIG_ENABLED : 0;
    return true;
}

EISABus *eisa_bus_new(DeviceState *dev, MemoryRegion *address_space,
                      MemoryRegion *address_space_io, Error **errp)
{
    ISABus *isa_bus;
    EISABus *bus;
    unsigned i;

    isa_bus = isa_bus_new_type(TYPE_EISA_BUS, dev, address_space,
                               address_space_io, errp);
    if (!isa_bus) {
        return NULL;
    }

    bus = EISA_BUS(isa_bus);
    for (i = 0; i < EISA_MAX_SLOTS; i++) {
        EISASlotState *slot = &bus->slots[i];

        slot->bus = bus;
        slot->slot = i;
        memory_region_init_io(&slot->config_io, OBJECT(bus), &eisa_slot_ops,
                              slot, "eisa-slot-config", EISA_CONFIG_SIZE);
        memory_region_add_subregion(address_space_io,
                                    i * EISA_SLOT_SIZE + EISA_VENDOR_ID_OFFSET,
                                    &slot->config_io);
    }

    return bus;
}

static const TypeInfo eisa_bus_info = {
    .name = TYPE_EISA_BUS,
    .parent = TYPE_ISA_BUS,
    .instance_size = sizeof(EISABus),
};

static void eisa_bus_register_types(void)
{
    type_register_static(&eisa_bus_info);
}

type_init(eisa_bus_register_types)
