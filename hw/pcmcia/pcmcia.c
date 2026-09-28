/*
 * 16-bit PC Card / PCMCIA core
 *
 * This is intentionally not a CardBus implementation.  CardBus is a
 * PCI-like secondary bus and requires a separate bridge/bus model.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "hw/pcmcia/pcmcia.h"

void pcmcia_bus_init(PCMCIABus *bus, DeviceState *parent, const char *name,
                     uint8_t socket, qemu_irq card_irq,
                     PCMCIACardEvent *card_event, void *opaque)
{
    qbus_init(bus, sizeof(*bus), TYPE_PCMCIA_BUS, parent, name);
    bus->socket = socket;
    bus->card_irq = card_irq;
    bus->card_event = card_event;
    bus->opaque = opaque;
}

bool pcmcia_bus_card_present(PCMCIABus *bus)
{
    return bus->card != NULL;
}

void pcmcia_card_set_irq(PCMCIACardState *card, int level)
{
    if (card->bus) {
        qemu_set_irq(card->bus->card_irq, level);
    }
}

static uint8_t pcmcia_default_attr_read(PCMCIACardState *card,
                                        uint32_t address)
{
    PCMCIACardClass *pcc = PCMCIA_CARD_GET_CLASS(card);

    if (address < pcc->cis_len) {
        return pcc->cis[address];
    }
    return 0xff;
}

uint8_t pcmcia_bus_attr_read(PCMCIABus *bus, uint32_t address)
{
    PCMCIACardClass *pcc;

    if (!bus->card) {
        return 0xff;
    }

    pcc = PCMCIA_CARD_GET_CLASS(bus->card);
    if (pcc->attr_read) {
        return pcc->attr_read(bus->card, address);
    }
    return pcmcia_default_attr_read(bus->card, address);
}

void pcmcia_bus_attr_write(PCMCIABus *bus, uint32_t address, uint8_t value)
{
    PCMCIACardClass *pcc;

    if (!bus->card) {
        return;
    }

    pcc = PCMCIA_CARD_GET_CLASS(bus->card);
    if (pcc->attr_write) {
        pcc->attr_write(bus->card, address, value);
    }
}

uint16_t pcmcia_bus_common_read(PCMCIABus *bus, uint32_t address)
{
    PCMCIACardClass *pcc;

    if (!bus->card) {
        return 0xffff;
    }

    pcc = PCMCIA_CARD_GET_CLASS(bus->card);
    return pcc->common_read ? pcc->common_read(bus->card, address) : 0xffff;
}

void pcmcia_bus_common_write(PCMCIABus *bus, uint32_t address, uint16_t value)
{
    PCMCIACardClass *pcc;

    if (!bus->card) {
        return;
    }

    pcc = PCMCIA_CARD_GET_CLASS(bus->card);
    if (pcc->common_write) {
        pcc->common_write(bus->card, address, value);
    }
}

uint16_t pcmcia_bus_io_read(PCMCIABus *bus, uint32_t address)
{
    PCMCIACardClass *pcc;

    if (!bus->card) {
        return 0xffff;
    }

    pcc = PCMCIA_CARD_GET_CLASS(bus->card);
    return pcc->io_read ? pcc->io_read(bus->card, address) : 0xffff;
}

void pcmcia_bus_io_write(PCMCIABus *bus, uint32_t address, uint16_t value)
{
    PCMCIACardClass *pcc;

    if (!bus->card) {
        return;
    }

    pcc = PCMCIA_CARD_GET_CLASS(bus->card);
    if (pcc->io_write) {
        pcc->io_write(bus->card, address, value);
    }
}

static void pcmcia_card_realize(DeviceState *dev, Error **errp)
{
    PCMCIACardState *card = PCMCIA_CARD(dev);
    PCMCIACardClass *pcc = PCMCIA_CARD_GET_CLASS(card);
    BusState *parent = qdev_get_parent_bus(dev);
    PCMCIABus *bus;

    if (!parent || !object_dynamic_cast(OBJECT(parent), TYPE_PCMCIA_BUS)) {
        error_setg(errp, "%s must be attached to a PC Card bus",
                   object_get_typename(OBJECT(dev)));
        return;
    }

    bus = PCMCIA_BUS(parent);
    if (bus->card) {
        error_setg(errp, "PC Card socket %u already contains a card",
                   bus->socket);
        return;
    }

    card->bus = bus;
    if (pcc->realize_card) {
        pcc->realize_card(card, errp);
        if (*errp) {
            card->bus = NULL;
            return;
        }
    }

    bus->card = card;
    if (bus->card_event) {
        bus->card_event(bus, true, bus->opaque);
    }
}

static void pcmcia_card_unrealize(DeviceState *dev)
{
    PCMCIACardState *card = PCMCIA_CARD(dev);
    PCMCIACardClass *pcc = PCMCIA_CARD_GET_CLASS(card);
    PCMCIABus *bus = card->bus;

    if (pcc->unrealize_card) {
        pcc->unrealize_card(card);
    }

    if (bus) {
        qemu_set_irq(bus->card_irq, 0);
        if (bus->card == card) {
            bus->card = NULL;
        }
        if (bus->card_event) {
            bus->card_event(bus, false, bus->opaque);
        }
    }
    card->bus = NULL;
}

static void pcmcia_card_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    dc->realize = pcmcia_card_realize;
    dc->unrealize = pcmcia_card_unrealize;
    dc->bus_type = TYPE_PCMCIA_BUS;
}

static const TypeInfo pcmcia_bus_type_info = {
    .name = TYPE_PCMCIA_BUS,
    .parent = TYPE_BUS,
    .instance_size = sizeof(PCMCIABus),
};

static const TypeInfo pcmcia_card_type_info = {
    .name = TYPE_PCMCIA_CARD,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(PCMCIACardState),
    .class_size = sizeof(PCMCIACardClass),
    .class_init = pcmcia_card_class_init,
    .abstract = true,
};

static void pcmcia_register_types(void)
{
    type_register_static(&pcmcia_bus_type_info);
    type_register_static(&pcmcia_card_type_info);
}

type_init(pcmcia_register_types)
