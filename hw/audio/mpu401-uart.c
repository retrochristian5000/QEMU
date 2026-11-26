/*
 * ISA MPU-401 UART-compatible MIDI interface (not intelligent mode).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Creative Sound Blaster Series Hardware Programming Guide, chapter 5.
 * The backend transports raw MIDI bytes, not audio or parsed messages.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qemu/log.h"
#include "qapi/error.h"
#include "chardev/char-fe.h"
#include "hw/audio/mpu401-uart.h"
#include "hw/core/irq.h"
#include "hw/core/qdev-properties.h"
#include "hw/core/qdev-properties-system.h"
#include "hw/isa/isa.h"
#include "migration/vmstate.h"

OBJECT_DECLARE_SIMPLE_TYPE(MPU401UARTState, MPU401_UART)

#define MPU_RX_SIZE 256
#define MPU_BYTE_NS 320000 /* 31.25 kbaud, 8 data bits + start/stop. */
#define MPU_RX_EMPTY 0x80
#define MPU_TX_BUSY 0x40
#define MPU_ACK 0xfe

struct MPU401UARTState {
    ISADevice parent_obj;
    MemoryRegion io;
    CharFrontend chr;
    qemu_irq irq_out;
    QEMUTimer *tx_timer;
    uint32_t iobase;
    uint32_t irq;
    uint8_t rx[MPU_RX_SIZE];
    unsigned int rx_head;
    unsigned int rx_count;
    uint8_t tx_byte;
    bool tx_busy;
    bool uart;
    bool ack_pending;
};

static void mpu_update_irq(MPU401UARTState *s)
{
    qemu_set_irq(s->irq_out, s->uart && (s->ack_pending || s->rx_count));
}

static void mpu_reset(DeviceState *dev)
{
    MPU401UARTState *s = MPU401_UART(dev);

    timer_del(s->tx_timer);
    s->tx_busy = false;
    s->uart = false;
    s->ack_pending = false;
    s->rx_head = 0;
    s->rx_count = 0;
    mpu_update_irq(s);
}

static int mpu_can_receive(void *opaque)
{
    MPU401UARTState *s = opaque;

    return s->uart ? MPU_RX_SIZE - s->rx_count : 0;
}

static void mpu_receive(void *opaque, const uint8_t *buf, int size)
{
    MPU401UARTState *s = opaque;

    while (size > 0 && s->uart && s->rx_count < MPU_RX_SIZE) {
        unsigned int tail = (s->rx_head + s->rx_count) % MPU_RX_SIZE;

        s->rx[tail] = *buf++;
        s->rx_count++;
        size--;
    }
    mpu_update_irq(s);
}

static void mpu_tx_complete(void *opaque)
{
    MPU401UARTState *s = opaque;
    int ret;

    if (!s->tx_busy) {
        return;
    }
    if (qemu_chr_fe_backend_connected(&s->chr) &&
        qemu_chr_fe_backend_open(&s->chr)) {
        ret = qemu_chr_fe_write(&s->chr, &s->tx_byte, 1);
        if (ret == 0 ||
            (ret < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))) {
            timer_mod(s->tx_timer,
                      qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + MPU_BYTE_NS);
            return;
        }
        if (ret < 0) {
            qemu_log_mask(LOG_GUEST_ERROR, "MPU-401 UART: MIDI output failed\n");
        }
    }
    /* No connected instrument: the byte leaves the UART without a reply. */
    s->tx_busy = false;
}

static uint64_t mpu_read(void *opaque, hwaddr addr, unsigned int size)
{
    MPU401UARTState *s = opaque;
    uint8_t value = 0xff;

    if (addr == 1) {
        return ((!s->ack_pending && !s->rx_count) ? MPU_RX_EMPTY : 0) |
               (s->tx_busy ? MPU_TX_BUSY : 0);
    }
    if (s->ack_pending) {
        s->ack_pending = false;
        value = MPU_ACK;
    } else if (s->rx_count) {
        value = s->rx[s->rx_head];
        s->rx_head = (s->rx_head + 1) % MPU_RX_SIZE;
        s->rx_count--;
    }
    mpu_update_irq(s);
    qemu_chr_fe_accept_input(&s->chr);
    return value;
}

static void mpu_write(void *opaque, hwaddr addr, uint64_t value,
                      unsigned int size)
{
    MPU401UARTState *s = opaque;

    if (addr == 1) {
        if (value == 0xff) {
            mpu_reset(DEVICE(s));
            s->ack_pending = true;
        } else if (!s->uart && value == 0x3f) {
            s->uart = true;
            s->ack_pending = true;
            mpu_update_irq(s);
            qemu_chr_fe_accept_input(&s->chr);
        }
        return;
    }
    if (!s->uart || s->tx_busy) {
        return;
    }
    s->tx_byte = value;
    s->tx_busy = true;
    timer_mod(s->tx_timer,
              qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) + MPU_BYTE_NS);
}

static const MemoryRegionOps mpu_io_ops = {
    .read = mpu_read,
    .write = mpu_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 1, .max_access_size = 1 },
    .impl = { .min_access_size = 1, .max_access_size = 1 },
};

static void mpu_init(Object *obj)
{
    MPU401UARTState *s = MPU401_UART(obj);

    qdev_init_gpio_out_named(DEVICE(obj), &s->irq_out, "irq", 1);
    memory_region_init_io(&s->io, obj, &mpu_io_ops, s, TYPE_MPU401_UART, 2);
    s->tx_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, mpu_tx_complete, s);
}

static void mpu_finalize(Object *obj)
{
    MPU401UARTState *s = MPU401_UART(obj);

    timer_free(s->tx_timer);
}

static void mpu_realize(DeviceState *dev, Error **errp)
{
    MPU401UARTState *s = MPU401_UART(dev);
    ISADevice *isa = ISA_DEVICE(dev);

    if (s->irq != MPU401_UART_SHARED_IRQ && (s->irq < 3 || s->irq > 15)) {
        error_setg(errp, "MPU-401 UART: ISA IRQ must be 3 through 15");
        return;
    }
    if (!isa_ioport_range_available(isa, s->iobase, 2, errp)) {
        return;
    }
    if (s->irq != MPU401_UART_SHARED_IRQ) {
        qdev_connect_gpio_out_named(dev, "irq", 0,
                         isa_bus_get_irq(isa_bus_from_device(isa), s->irq));
    } else if (!qdev_get_gpio_out_connector(dev, "irq", 0)) {
        error_setg(errp, "MPU-401 UART: shared IRQ requires board wiring");
        return;
    }

    isa_register_ioport(isa, &s->io, s->iobase);
    qemu_chr_fe_set_handlers(&s->chr, mpu_can_receive, mpu_receive,
                             NULL, NULL, s, NULL, true);
}

static void mpu_unrealize(DeviceState *dev)
{
    MPU401UARTState *s = MPU401_UART(dev);

    qemu_chr_fe_set_handlers(&s->chr, NULL, NULL, NULL, NULL, NULL, NULL, false);
    mpu_reset(dev);
    memory_region_del_subregion(isa_address_space_io(ISA_DEVICE(dev)), &s->io);
}

/* Raw backend and pending serial timing do not yet have a migration ABI. */
static const VMStateDescription vmstate_mpu = {
    .name = TYPE_MPU401_UART,
    .unmigratable = true,
};

static const Property mpu_properties[] = {
    DEFINE_PROP_UINT32("iobase", MPU401UARTState, iobase, 0x330),
    DEFINE_PROP_UINT32("irq", MPU401UARTState, irq, 9),
    DEFINE_PROP_CHR("chardev", MPU401UARTState, chr),
};

static void mpu_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "MPU-401 UART-compatible ISA MIDI interface";
    dc->realize = mpu_realize;
    dc->unrealize = mpu_unrealize;
    dc->hotpluggable = false;
    dc->vmsd = &vmstate_mpu;
    device_class_set_legacy_reset(dc, mpu_reset);
    device_class_set_props(dc, mpu_properties);
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
}

static const TypeInfo mpu_info = {
    .name = TYPE_MPU401_UART,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(MPU401UARTState),
    .instance_init = mpu_init,
    .instance_finalize = mpu_finalize,
    .class_init = mpu_class_init,
};

static void mpu_register_types(void)
{
    type_register_static(&mpu_info);
}

type_init(mpu_register_types)
