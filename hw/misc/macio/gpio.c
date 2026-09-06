/*
 * PowerMac NewWorld MacIO GPIO emulation
 *
 * Copyright (c) 2016 Benjamin Herrenschmidt
 * Copyright (c) 2018 Mark Cave-Ayland
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "hw/misc/macio/macio.h"
#include "hw/misc/macio/gpio.h"
#include "hw/core/irq.h"
#include "hw/core/nmi.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "trace.h"

enum MacioGPIORegisterBits {
    OUT_DATA   = 1,
    IN_DATA    = 2,
    OUT_ENABLE = 4,
};

void macio_set_gpio(MacIOGPIOState *s, uint32_t gpio, bool state)
{
    uint8_t new_reg;

    if (gpio >= MACIO_GPIO_EXTINT_COUNT) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "GPIO: external GPIO index %u out of range\n", gpio);
        return;
    }

    trace_macio_set_gpio(gpio, state);

    if (s->gpio_regs[gpio] & OUT_ENABLE) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "GPIO: Setting GPIO %d while it's an output\n", gpio);
    }

    new_reg = s->gpio_regs[gpio] & ~IN_DATA;
    if (state) {
        new_reg |= IN_DATA;
    }

    if (new_reg == s->gpio_regs[gpio]) {
        return;
    }

    s->gpio_regs[gpio] = new_reg;

    /*
     * Note that we probably need to get access to the MPIC config to
     * decode polarity since qemu always use "raise" regardless.
     *
     * For now, we hard wire known GPIOs
     */

    switch (gpio) {
    case 1:
        /* Level low */
        if (!state) {
            trace_macio_gpio_irq_assert(gpio);
            qemu_irq_raise(s->gpio_extirqs[gpio]);
        } else {
            trace_macio_gpio_irq_deassert(gpio);
            qemu_irq_lower(s->gpio_extirqs[gpio]);
        }
        break;

    case 9:
        /* Edge, triggered by NMI below */
        if (state) {
            trace_macio_gpio_irq_assert(gpio);
            qemu_irq_raise(s->gpio_extirqs[gpio]);
        } else {
            trace_macio_gpio_irq_deassert(gpio);
            qemu_irq_lower(s->gpio_extirqs[gpio]);
        }
        break;

    default:
        qemu_log_mask(LOG_UNIMP, "GPIO: setting unimplemented GPIO %d", gpio);
    }
}

static void macio_gpio_write(void *opaque, hwaddr addr, uint64_t value,
                             unsigned size)
{
    MacIOGPIOState *s = opaque;
    uint8_t ibit;

    trace_macio_gpio_write(addr, value);

    /*
     * Apple saves and restores both GPIO level registers across sleep, so
     * preserve byte writes here instead of treating the 0x50-0x57 block as
     * read-only.  Multi-byte accesses are split to byte operations by the
     * MemoryRegion implementation below.
     */
    if (addr < MACIO_GPIO_LEVEL_BYTES) {
        s->gpio_levels[addr] = value;
        return;
    }

    addr -= MACIO_GPIO_LEVEL_BYTES;
    if (addr < MACIO_GPIO_REG_COUNT) {
        value &= ~IN_DATA;

        if (value & OUT_ENABLE) {
            ibit = (value & OUT_DATA) << 1;
        } else {
            ibit = s->gpio_regs[addr] & IN_DATA;
        }

        s->gpio_regs[addr] = value | ibit;
    }
}

static uint64_t macio_gpio_read(void *opaque, hwaddr addr, unsigned size)
{
    MacIOGPIOState *s = opaque;
    uint64_t val = 0;

    /* Levels regs */
    if (addr < MACIO_GPIO_LEVEL_BYTES) {
        val = s->gpio_levels[addr];
    } else {
        addr -= MACIO_GPIO_LEVEL_BYTES;

        if (addr < MACIO_GPIO_REG_COUNT) {
            val = s->gpio_regs[addr];
        }
    }

    trace_macio_gpio_read(addr, val);
    return val;
}

static const MemoryRegionOps macio_gpio_ops = {
    .read = macio_gpio_read,
    .write = macio_gpio_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
};

static void macio_gpio_init(Object *obj)
{
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    MacIOGPIOState *s = MACIO_GPIO(obj);
    int i;

    for (i = 0; i < MACIO_GPIO_EXTINT_COUNT; i++) {
        sysbus_init_irq(sbd, &s->gpio_extirqs[i]);
    }

    memory_region_init_io(&s->gpiomem, OBJECT(s), &macio_gpio_ops, obj,
                          "gpio", MACIO_GPIO_MMIO_SIZE);
    sysbus_init_mmio(sbd, &s->gpiomem);
}

static const VMStateDescription vmstate_macio_gpio = {
    .name = "macio_gpio",
    .version_id = 0,
    .minimum_version_id = 0,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8_ARRAY(gpio_levels, MacIOGPIOState,
                            MACIO_GPIO_LEVEL_BYTES),
        VMSTATE_UINT8_ARRAY(gpio_regs, MacIOGPIOState,
                            MACIO_GPIO_MIG_REG_COUNT),
        VMSTATE_END_OF_LIST()
    }
};

static void macio_gpio_reset(DeviceState *dev)
{
    MacIOGPIOState *s = MACIO_GPIO(dev);

    /* GPIO 1 is up by default */
    macio_set_gpio(s, 1, true);
}

static void macio_gpio_nmi(NMIState *n, int cpu_index, Error **errp)
{
    macio_set_gpio(MACIO_GPIO(n), 9, true);
    macio_set_gpio(MACIO_GPIO(n), 9, false);
}

static void macio_gpio_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    NMIClass *nc = NMI_CLASS(oc);

    device_class_set_legacy_reset(dc, macio_gpio_reset);
    dc->vmsd = &vmstate_macio_gpio;
    nc->nmi_monitor_handler = macio_gpio_nmi;
}

static const TypeInfo macio_gpio_init_info = {
    .name          = TYPE_MACIO_GPIO,
    .parent        = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(MacIOGPIOState),
    .instance_init = macio_gpio_init,
    .class_init    = macio_gpio_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { TYPE_NMI },
        { }
    },
};

static void macio_gpio_register_types(void)
{
    type_register_static(&macio_gpio_init_info);
}

type_init(macio_gpio_register_types)
