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

/*
 * Standard 16-bit PC Card CIS tuple identifiers.  These are format constants,
 * not a declaration that QEMU implements every corresponding card function.
 * Preserve native CIS byte values (PCMCIA tuple assignments).
 */
#define CISTPL_NULL             0x00
#define CISTPL_DEVICE           0x01
#define CISTPL_CHECKSUM         0x10
#define CISTPL_LONGLINK_A       0x11
#define CISTPL_LONGLINK_C       0x12
#define CISTPL_LINKTARGET       0x13
#define CISTPL_NO_LINK         0x14
#define CISTPL_VERS_1           0x15
#define CISTPL_ALTSTR           0x16
#define CISTPL_DEVICE_A         0x17
#define CISTPL_JEDEC_C          0x18
#define CISTPL_JEDEC_A          0x19
#define CISTPL_CONFIG           0x1a
#define CISTPL_CFTABLE_ENTRY    0x1b
#define CISTPL_DEVICE_OC        0x1c
#define CISTPL_DEVICE_OA        0x1d
#define CISTPL_DEVICE_GEO       0x1e
#define CISTPL_DEVICE_GEO_A     0x1f
#define CISTPL_MANFID           0x20
#define CISTPL_FUNCID           0x21
#define CISTPL_FUNCE            0x22
#define CISTPL_SWIL             0x23
#define CISTPL_VERS_2           0x40
#define CISTPL_FORMAT           0x41
#define CISTPL_GEOMETRY         0x42
#define CISTPL_BYTEORDER        0x43
#define CISTPL_DATE             0x44
#define CISTPL_BATTERY          0x45
#define CISTPL_ORG              0x46
#define CISTPL_FORMAT_A         0x47
#define CISTPL_SPCL             0x90
#define CISTPL_END              0xff

/* CISTPL_FUNCID values, which are distinct from the tuple identifier. */
#define CISTPL_FUNCID_MULTI     0x00
#define CISTPL_FUNCID_MEMORY    0x01
#define CISTPL_FUNCID_SERIAL    0x02
#define CISTPL_FUNCID_PARALLEL  0x03
#define CISTPL_FUNCID_FIXED     0x04
#define CISTPL_FUNCID_VIDEO     0x05
#define CISTPL_FUNCID_NETWORK   0x06
#define CISTPL_FUNCID_AIMS      0x07
#define CISTPL_FUNCID_SCSI      0x08

/* Serial-function extension selectors and UART identification codes. */
#define CISTPL_FUNCE_SERIAL_IF  0x00
#define CISTPL_FUNCE_SERIAL_CAP 0x01
#define CISTPL_SERIAL_UART_8250 0x00
#define CISTPL_SERIAL_UART_16450 0x01
#define CISTPL_SERIAL_UART_16550 0x02
#define CISTPL_SERIAL_UART_8251 0x03
#define CISTPL_SERIAL_UART_8530 0x04
#define CISTPL_SERIAL_UART_85230 0x05

#endif
