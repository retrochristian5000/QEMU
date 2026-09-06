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

#ifndef MACIO_GPIO_H
#define MACIO_GPIO_H

#include "hw/ppc/openpic.h"
#include "hw/core/sysbus.h"
#include "qom/object.h"

#define TYPE_MACIO_GPIO "macio-gpio"
OBJECT_DECLARE_SIMPLE_TYPE(MacIOGPIOState, MACIO_GPIO)

/*
 * KeyLargo GPIO register layout at MacIO offset 0x50:
 *
 *   0x50-0x57  GPIO level registers (2 x 32-bit)
 *   0x58-0x69  18 external-interrupt GPIO registers
 *   0x6a-0x7a  17 ordinary GPIO registers
 *   0x7b-0x7f  reserved in the current model
 *
 * Apple Cheetah- and Panther-era drivers both save/restore this exact
 * 18 + 17 topology.  Keep the historical 36-byte migration storage for
 * compatibility with older QEMU migration streams, but expose only the
 * 35 hardware GPIO registers.
 */
#define MACIO_GPIO_LEVEL_BYTES       8
#define MACIO_GPIO_EXTINT_COUNT      18
#define MACIO_GPIO_NORMAL_COUNT      17
#define MACIO_GPIO_REG_COUNT         (MACIO_GPIO_EXTINT_COUNT + \
                                      MACIO_GPIO_NORMAL_COUNT)
#define MACIO_GPIO_MIG_REG_COUNT     36
#define MACIO_GPIO_MMIO_SIZE         0x30

struct MacIOGPIOState {
    /*< private >*/
    SysBusDevice parent;
    /*< public >*/

    MemoryRegion gpiomem;
    qemu_irq gpio_extirqs[MACIO_GPIO_EXTINT_COUNT];
    uint8_t gpio_levels[MACIO_GPIO_LEVEL_BYTES];
    uint8_t gpio_regs[MACIO_GPIO_MIG_REG_COUNT];
};

void macio_set_gpio(MacIOGPIOState *s, uint32_t gpio, bool state);

#endif
