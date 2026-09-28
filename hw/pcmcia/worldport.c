/*
 * U.S. Robotics WorldPort PCMCIA V.34 modem
 *
 * The card-facing profile is based on the documented PCMCIA 2.0/2.1
 * 16550-compatible interface.  The CIS below is reconstructed from verified
 * product/interface characteristics; it is not claimed to be a byte-for-byte
 * dump of a retail WorldPort CIS ROM.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/module.h"
#include "hw/char/serial.h"
#include "hw/pcmcia/pcmcia.h"
#include "migration/vmstate.h"
#include "system/memory.h"

#define TYPE_USR_WORLDPORT_V34 "usr-worldport-v34"
OBJECT_DECLARE_SIMPLE_TYPE(USRWorldPortState, USR_WORLDPORT_V34)

#define WORLDPORT_CONFIG_BASE 0x0200
#define WORLDPORT_COR_FUNC_ENA 0x01

struct USRWorldPortState {
    PCMCIACardState parent_obj;

    SerialState uart;
    qemu_irq uart_irq;
    uint8_t cor;
};

/*
 * Logical CIS bytes.  Attribute memory presents these on even byte addresses;
 * odd addresses read as 0xff.
 *
 * VERS_1 identifies only facts verified from U.S. Robotics documentation.
 * No numeric MANFID/CARD pair is synthesized because a trustworthy retail
 * WorldPort CIS dump has not yet been recovered.
 */
static const uint8_t worldport_cis[] = {
    /* CISTPL_VERS_1 */
    CISTPL_VERS_1, 0x35, 0x04, 0x01,
    'U', '.', 'S', '.', ' ', 'R', 'o', 'b', 'o', 't', 'i', 'c', 's', 0x00,
    'W', 'o', 'r', 'l', 'd', 'P', 'o', 'r', 't', ' ',
    'P', 'C', 'M', 'C', 'I', 'A', ' ', 'V', '.', '3', '4', ' ', 'C', 'E',
    0x00,
    'P', 'C', 'M', 'C', 'I', 'A', ' ', '2', '.', '1', 0x00,
    0x00,

    /* Serial-function card with a 16550-compatible UART. */
    CISTPL_FUNCID, 0x02, CISTPL_FUNCID_SERIAL, 0x00,
    CISTPL_FUNCE, 0x04, CISTPL_FUNCE_SERIAL_IF,
    CISTPL_SERIAL_UART_16550, 0x0c, 0x58,

    /*
     * Reconstructed configuration layout:
     * one COR at attribute address 0x0200, configuration index 1.
     */
    CISTPL_CONFIG, 0x05, 0x01, 0x01, 0x00, 0x02, 0x01,

    /*
     * Default configuration 1: one relocatable 8-byte I/O window and a
     * level-triggered IRQ.  The host socket controller chooses the I/O base.
     */
    CISTPL_CFTABLE_ENTRY, 0x06, 0x41, 0x18, 0x63, 0x30, 0xff, 0xff,

    CISTPL_END,
};

static void worldport_uart_irq(void *opaque, int n, int level)
{
    USRWorldPortState *s = opaque;

    pcmcia_card_set_irq(PCMCIA_CARD(s), level);
}

static uint8_t worldport_attr_read(PCMCIACardState *card, uint32_t address)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(card);
    uint32_t cis_offset;

    if (address == WORLDPORT_CONFIG_BASE) {
        return s->cor;
    }

    if (address & 1) {
        return 0xff;
    }

    cis_offset = address >> 1;
    if (cis_offset < sizeof(worldport_cis)) {
        return worldport_cis[cis_offset];
    }

    return 0xff;
}

static void worldport_attr_write(PCMCIACardState *card, uint32_t address,
                                 uint8_t value)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(card);

    if (address == WORLDPORT_CONFIG_BASE) {
        s->cor = value;
    }
}

static uint16_t worldport_common_read(PCMCIACardState *card, uint32_t address)
{
    return 0xffff;
}

static void worldport_common_write(PCMCIACardState *card, uint32_t address,
                                   uint16_t value)
{
}

static uint16_t worldport_io_read(PCMCIACardState *card, uint32_t address)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(card);
    uint64_t value = 0xff;

    if (!(s->cor & WORLDPORT_COR_FUNC_ENA) || address >= 8) {
        return 0xff;
    }

    memory_region_dispatch_read(&s->uart.io, address, &value,
                                MO_8, MEMTXATTRS_UNSPECIFIED);
    return value;
}

static void worldport_io_write(PCMCIACardState *card, uint32_t address,
                               uint16_t value)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(card);

    if (!(s->cor & WORLDPORT_COR_FUNC_ENA) || address >= 8) {
        return;
    }

    memory_region_dispatch_write(&s->uart.io, address, value & 0xff,
                                 MO_8, MEMTXATTRS_UNSPECIFIED);
}

static void worldport_realize_card(PCMCIACardState *card, Error **errp)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(card);

    s->uart_irq = qemu_allocate_irq(worldport_uart_irq, s, 0);
    s->uart.irq = s->uart_irq;

    if (!qdev_realize(DEVICE(&s->uart), NULL, errp)) {
        qemu_free_irq(s->uart_irq);
        s->uart_irq = NULL;
        return;
    }

    memory_region_init_io(&s->uart.io, OBJECT(s), &serial_io_ops, &s->uart,
                          "usr-worldport-v34-uart", 8);
}

static void worldport_unrealize_card(PCMCIACardState *card)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(card);

    pcmcia_card_set_irq(card, 0);
    qdev_unrealize(DEVICE(&s->uart));
    qemu_free_irq(s->uart_irq);
    s->uart_irq = NULL;
}

static void worldport_reset(DeviceState *dev)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(dev);

    s->cor = 0;
}

static const VMStateDescription vmstate_worldport = {
    .name = "usr-worldport-v34",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(cor, USRWorldPortState),
        VMSTATE_STRUCT(uart, USRWorldPortState, 0,
                       vmstate_serial, SerialState),
        VMSTATE_END_OF_LIST()
    },
};

static void worldport_init(Object *obj)
{
    USRWorldPortState *s = USR_WORLDPORT_V34(obj);

    object_initialize_child(obj, "uart", &s->uart, TYPE_SERIAL);
    qdev_alias_all_properties(DEVICE(&s->uart), obj);
}

static void worldport_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    PCMCIACardClass *pcc = PCMCIA_CARD_CLASS(oc);

    pcc->cis = worldport_cis;
    pcc->cis_len = sizeof(worldport_cis);
    pcc->realize_card = worldport_realize_card;
    pcc->unrealize_card = worldport_unrealize_card;
    pcc->attr_read = worldport_attr_read;
    pcc->attr_write = worldport_attr_write;
    pcc->common_read = worldport_common_read;
    pcc->common_write = worldport_common_write;
    pcc->io_read = worldport_io_read;
    pcc->io_write = worldport_io_write;

    device_class_set_legacy_reset(dc, worldport_reset);
    dc->desc = "U.S. Robotics WorldPort PCMCIA V.34 modem";
    dc->vmsd = &vmstate_worldport;
    set_bit(DEVICE_CATEGORY_INPUT, dc->categories);
}

static const TypeInfo worldport_info = {
    .name = TYPE_USR_WORLDPORT_V34,
    .parent = TYPE_PCMCIA_CARD,
    .instance_size = sizeof(USRWorldPortState),
    .instance_init = worldport_init,
    .class_init = worldport_class_init,
};

static void worldport_register_types(void)
{
    type_register_static(&worldport_info);
}

type_init(worldport_register_types)
