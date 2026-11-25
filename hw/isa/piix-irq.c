/*
 * QEMU PIIX PCI-to-ISA interrupt routing
 *
 * Copyright (c) 2006 Fabrice Bellard
 * Copyright (c) 2018 Hervé Poussineau
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
#include "qemu/range.h"
#include "hw/core/irq.h"
#include "hw/isa/isa.h"
#include "piix-internal.h"

static bool piix_get_irq_pic_level(PIIXState *s, int pic_irq)
{
    return !!(s->pic_levels &
              (((1ULL << PIIX_NUM_PIRQS) - 1) <<
               (pic_irq * PIIX_NUM_PIRQS)));
}

static void piix_set_irq_pic(PIIXState *s, int pic_irq)
{
    qemu_set_irq(s->isa_irqs_in[pic_irq],
                 piix_get_irq_pic_level(s, pic_irq));
}

static void piix_set_pci_irq_level_internal(PIIXState *s, int pirq, int level)
{
    int pic_irq;
    uint64_t mask;

    pic_irq = s->dev.config[PIIX_PIRQCA + pirq];
    if (pic_irq >= ISA_NUM_IRQS) {
        return;
    }

    mask = 1ULL << ((pic_irq * PIIX_NUM_PIRQS) + pirq);
    s->pic_levels &= ~mask;
    s->pic_levels |= mask * !!level;
}

static void piix_set_pci_irq_level(PIIXState *s, int pirq, int level)
{
    bool old_level;
    bool new_level;
    int pic_irq;

    pic_irq = s->dev.config[PIIX_PIRQCA + pirq];
    if (pic_irq >= ISA_NUM_IRQS) {
        return;
    }

    old_level = piix_get_irq_pic_level(s, pic_irq);
    piix_set_pci_irq_level_internal(s, pirq, level);
    new_level = piix_get_irq_pic_level(s, pic_irq);

    if (old_level != new_level) {
        qemu_set_irq(s->isa_irqs_in[pic_irq], new_level);
    }
}

void piix_set_pci_irq(void *opaque, int pirq, int level)
{
    PIIXState *s = opaque;
    piix_set_pci_irq_level(s, pirq, level);
}

PCIINTxRoute piix_route_intx_pin_to_irq(void *opaque, int pin)
{
    PCIDevice *pci_dev = opaque;
    int irq = pci_dev->config[PIIX_PIRQCA + pin];
    PCIINTxRoute route;

    if (irq < ISA_NUM_IRQS) {
        route.mode = PCI_INTX_ENABLED;
        route.irq = irq;
    } else {
        route.mode = PCI_INTX_DISABLED;
        route.irq = -1;
    }
    return route;
}

/* Rebuild the complete routing bitmap without driving ISA IRQ lines. */
void piix_rebuild_irq_levels(PIIXState *s)
{
    PCIBus *bus = pci_get_bus(&s->dev);
    int pirq;

    s->pic_levels = 0;
    for (pirq = 0; pirq < PIIX_NUM_PIRQS; pirq++) {
        piix_set_pci_irq_level_internal(s, pirq,
                                         pci_bus_get_irq_level(bus, pirq));
    }
}

void piix_write_config(PCIDevice *dev, uint32_t address, uint32_t val,
                              int len)
{
    pci_default_write_config(dev, address, val, len);
    if (ranges_overlap(address, len, PIIX_PIRQCA, 4)) {
        PIIXState *s = PIIX_PCI_DEVICE(dev);
        int pic_irq;

        pci_bus_fire_intx_routing_notifier(pci_get_bus(&s->dev));
        piix_rebuild_irq_levels(s);
        /* Publish only after every PIRQ has been accounted for. */
        for (pic_irq = 0; pic_irq < ISA_NUM_IRQS; pic_irq++) {
            piix_set_irq_pic(s, pic_irq);
        }
    }
}
