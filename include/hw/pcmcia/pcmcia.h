/*
 * 16-bit PC Card / PCMCIA core
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef HW_PCMCIA_PCMCIA_H
#define HW_PCMCIA_PCMCIA_H

#include "hw/core/irq.h"
#include "hw/core/qdev.h"
#include "qom/object.h"

#define TYPE_PCMCIA_BUS "pcmcia-bus"
OBJECT_DECLARE_SIMPLE_TYPE(PCMCIABus, PCMCIA_BUS)

#define TYPE_PCMCIA_CARD "pcmcia-card"
OBJECT_DECLARE_TYPE(PCMCIACardState, PCMCIACardClass, PCMCIA_CARD)

typedef void PCMCIACardEvent(PCMCIABus *bus, bool inserted, void *opaque);

struct PCMCIABus {
    BusState parent_obj;

    PCMCIACardState *card;
    qemu_irq card_irq;
    PCMCIACardEvent *card_event;
    void *opaque;
    uint8_t socket;
};

struct PCMCIACardState {
    DeviceState parent_obj;

    PCMCIABus *bus;
};

struct PCMCIACardClass {
    DeviceClass parent_class;

    const uint8_t *cis;
    size_t cis_len;

    void (*realize_card)(PCMCIACardState *card, Error **errp);
    void (*unrealize_card)(PCMCIACardState *card);

    uint8_t (*attr_read)(PCMCIACardState *card, uint32_t address);
    void (*attr_write)(PCMCIACardState *card, uint32_t address, uint8_t value);
    uint16_t (*common_read)(PCMCIACardState *card, uint32_t address);
    void (*common_write)(PCMCIACardState *card,
                         uint32_t address, uint16_t value);
    uint16_t (*io_read)(PCMCIACardState *card, uint32_t address);
    void (*io_write)(PCMCIACardState *card, uint32_t address, uint16_t value);
};

void pcmcia_bus_init(PCMCIABus *bus, DeviceState *parent, const char *name,
                     uint8_t socket, qemu_irq card_irq,
                     PCMCIACardEvent *card_event, void *opaque);

bool pcmcia_bus_card_present(PCMCIABus *bus);
void pcmcia_card_set_irq(PCMCIACardState *card, int level);

uint8_t pcmcia_bus_attr_read(PCMCIABus *bus, uint32_t address);
void pcmcia_bus_attr_write(PCMCIABus *bus, uint32_t address, uint8_t value);
uint16_t pcmcia_bus_common_read(PCMCIABus *bus, uint32_t address);
void pcmcia_bus_common_write(PCMCIABus *bus, uint32_t address, uint16_t value);
uint16_t pcmcia_bus_io_read(PCMCIABus *bus, uint32_t address);
void pcmcia_bus_io_write(PCMCIABus *bus, uint32_t address, uint16_t value);

#define CISTPL_NULL            0x00
#define CISTPL_DEVICE          0x01
#define CISTPL_NO_LINK         0x14
#define CISTPL_VERS_1          0x15
#define CISTPL_CONFIG          0x1a
#define CISTPL_CFTABLE_ENTRY   0x1b
#define CISTPL_MANFID          0x20
#define CISTPL_FUNCID          0x21
#define CISTPL_FUNCE           0x22
#define CISTPL_END             0xff

#define CISTPL_FUNCID_SERIAL   0x02
#define CISTPL_FUNCE_SERIAL_IF 0x00
#define CISTPL_SERIAL_UART_16550 0x02

#endif
