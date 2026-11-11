/*
 * Extended Industry Standard Architecture (EISA) bus
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_EISA_H
#define HW_EISA_H

#include "hw/isa/isa.h"

#define TYPE_EISA_BUS "EISA"
OBJECT_DECLARE_SIMPLE_TYPE(EISABus, EISA_BUS)

/* EISA allocates a 4 KiB slot-specific I/O window to each logical slot. */
#define EISA_SLOT_SIZE              0x1000
#define EISA_MAX_SLOTS              16
#define EISA_VENDOR_ID_OFFSET       0x0c80
#define EISA_CONFIG_OFFSET          0x0c84
#define EISA_CONFIG_SIZE            5
#define EISA_CONFIG_ENABLED         0x01

typedef struct EISASlotState {
    struct EISABus *bus;
    MemoryRegion config_io;
    uint8_t slot;
    bool present;
    uint8_t id[4];
    uint8_t control;
} EISASlotState;

struct EISABus {
    ISABus parent_obj;

    EISASlotState slots[EISA_MAX_SLOTS];
};

EISABus *eisa_bus_new(DeviceState *dev, MemoryRegion *address_space,
                      MemoryRegion *address_space_io, Error **errp);

/*
 * Install or replace the compressed EISA product identifier for @slot.
 * @id uses the canonical seven-character form, for example "DEL0001".
 */
bool eisa_bus_set_slot_id(EISABus *bus, unsigned slot, const char *id,
                          bool enabled, Error **errp);

#endif /* HW_EISA_H */
