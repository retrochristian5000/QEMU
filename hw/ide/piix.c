/*
 * QEMU IDE Emulation: PCI PIIX3/4 support.
 *
 * Copyright (c) 2003 Fabrice Bellard
 * Copyright (c) 2006 Openedhand Ltd.
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
 *
 * References:
 *  [1] 82371FB (PIIX) AND 82371SB (PIIX3) PCI ISA IDE XCELERATOR,
 *      290550-002, Intel Corporation, April 1997.
 *  [2] 82371AB PCI-to-ISA / IDE Xcelerator (PIIX4), Intel,
 *      April 1997, sections 5.1.10-5.1.13.
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/pci/pci.h"
#include "hw/core/qdev-properties.h"
#include "hw/ide/piix.h"
#include "hw/ide/pci.h"
#include "ide-internal.h"
#include "trace.h"

static uint64_t bmdma_read(void *opaque, hwaddr addr, unsigned size)
{
    BMDMAState *bm = opaque;
    uint32_t val;

    if (size != 1) {
        return ((uint64_t)1 << (size * 8)) - 1;
    }

    switch(addr & 3) {
    case 0:
        val = bm->cmd;
        break;
    case 2:
        val = bm->status;
        break;
    default:
        val = 0xff;
        break;
    }

    trace_bmdma_read(addr, val);
    return val;
}

static void bmdma_write(void *opaque, hwaddr addr,
                        uint64_t val, unsigned size)
{
    BMDMAState *bm = opaque;

    if (size != 1) {
        return;
    }

    trace_bmdma_write(addr, val);

    switch(addr & 3) {
    case 0:
        bmdma_cmd_writeb(bm, val);
        break;
    case 2:
        bmdma_status_writeb(bm, val);
        break;
    }
}

static const MemoryRegionOps piix_bmdma_ops = {
    .read = bmdma_read,
    .write = bmdma_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    /* PIIX supports byte, word and dword accesses to the IDE BAR.
     * Dispatch wider accesses to the individual byte registers. */
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
};

static void bmdma_setup_bar(PCIIDEState *d)
{
    int i;

    memory_region_init(&d->bmdma_bar, OBJECT(d), "piix-bmdma-container", 16);
    for(i = 0;i < 2; i++) {
        BMDMAState *bm = &d->bmdma[i];

        memory_region_init_io(&bm->extra_io, OBJECT(d), &piix_bmdma_ops, bm,
                              "piix-bmdma", 4);
        memory_region_add_subregion(&d->bmdma_bar, i * 8, &bm->extra_io);
        memory_region_init_io(&bm->addr_ioport, OBJECT(d),
                              &bmdma_addr_ioport_ops, bm, "bmdma", 4);
        memory_region_add_subregion(&d->bmdma_bar, i * 8 + 4, &bm->addr_ioport);
    }
}

enum {
    PIIX4_IDETIM_PRIMARY = 0x40,
    PIIX4_IDETIM_SECONDARY = 0x42,
    PIIX4_SIDETIM = 0x44,
    PIIX4_UDMACTL = 0x48,
    PIIX4_UDMATIM = 0x4a,
};

static void piix_ide_reset(DeviceState *dev)
{
    PCIIDEState *d = PCI_IDE(dev);
    PCIDevice *pd = PCI_DEVICE(d);
    uint8_t *pci_conf = pd->config;
    int i;

    for (i = 0; i < 2; i++) {
        ide_bus_reset(&d->bus[i]);
    }

    /* PCI command register default value (0000h) per [1, p.48].  */
    pci_set_word(pci_conf + PCI_COMMAND, 0x0000);
    pci_set_word(pci_conf + PCI_STATUS,
                 PCI_STATUS_DEVSEL_MEDIUM | PCI_STATUS_FAST_BACK);
    pci_set_long(pci_conf + 0x20, 0x1);  /* BMIBA: 20-23h */
}

static bool pci_piix_init_bus(PCIIDEState *d, unsigned i, Error **errp)
{
    static const struct {
        int iobase;
        int iobase2;
        int isairq;
    } port_info[] = {
        {0x1f0, 0x3f6, 14},
        {0x170, 0x376, 15},
    };
    int ret;

    ide_bus_init(&d->bus[i], sizeof(d->bus[i]), DEVICE(d), i, 2);
    ret = ide_init_ioport(&d->bus[i], NULL, port_info[i].iobase,
                          port_info[i].iobase2);
    if (ret) {
        error_setg_errno(errp, -ret, "Failed to realize %s port %u",
                         object_get_typename(OBJECT(d)), i);
        return false;
    }
    ide_bus_init_output_irq(&d->bus[i], isa_get_irq(NULL, port_info[i].isairq));

    bmdma_init(&d->bus[i], &d->bmdma[i], d);
    ide_bus_register_restart_cb(&d->bus[i]);

    return true;
}

static void pci_piix_ide_realize(PCIDevice *dev, Error **errp)
{
    PCIIDEState *d = PCI_IDE(dev);
    uint8_t *pci_conf = dev->config;

    pci_conf[PCI_CLASS_PROG] = 0x80; // legacy ATA mode

    bmdma_setup_bar(d);
    pci_register_bar(dev, 4, PCI_BASE_ADDRESS_SPACE_IO, &d->bmdma_bar);

    for (unsigned i = 0; i < 2; i++) {
        if (!pci_piix_init_bus(d, i, errp)) {
            return;
        }
    }
}

static void pci_piix_ide_exitfn(PCIDevice *dev)
{
    PCIIDEState *d = PCI_IDE(dev);
    unsigned i;

    for (i = 0; i < 2; ++i) {
        memory_region_del_subregion(&d->bmdma_bar, &d->bmdma[i].extra_io);
        memory_region_del_subregion(&d->bmdma_bar, &d->bmdma[i].addr_ioport);
    }
}

/* NOTE: for the PIIX3, the IRQs and IOports are hardcoded */
static void piix3_ide_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, piix_ide_reset);
    dc->vmsd = &vmstate_ide_pci;
    k->realize = pci_piix_ide_realize;
    k->exit = pci_piix_ide_exitfn;
    k->vendor_id = PCI_VENDOR_ID_INTEL;
    k->device_id = PCI_DEVICE_ID_INTEL_82371SB_1;
    dc->desc = "Intel 82371SB PIIX3 PCI IDE controller";
    k->class_id = PCI_CLASS_STORAGE_IDE;
    set_bit(DEVICE_CATEGORY_STORAGE, dc->categories);
    dc->hotpluggable = false;
}

static const TypeInfo piix3_ide_info = {
    .name          = TYPE_PIIX3_IDE,
    .parent        = TYPE_PCI_IDE,
    .class_init    = piix3_ide_class_init,
};

/*
 * PIIX4 supports Ultra DMA/33 configuration, unlike PIIX3.
 * Limit this opt-in policy to register storage and reset semantics; the
 * shared ATA engine does not model the physical UDMA strobe timings.
 */
static void piix4_ide_reset(DeviceState *dev)
{
    PCIIDEState *d = PCI_IDE(dev);
    PCIDevice *pd = PCI_DEVICE(dev);

    piix_ide_reset(dev);
    if (d->piix4_strict_timing_regs) {
        memset(pd->config + PIIX4_IDETIM_PRIMARY, 0,
               PIIX4_UDMATIM + 2 - PIIX4_IDETIM_PRIMARY);
    }
}

static void pci_piix4_ide_realize(PCIDevice *dev, Error **errp)
{
    PCIIDEState *d = PCI_IDE(dev);

    if (d->piix4_strict_timing_regs) {
        /* Intel [2]: IDETIM bits 11:10, UDMACTL bits 7:4,
         * and the high two bits of each UDMATIM nibble are reserved. */
        memset(dev->wmask + PIIX4_IDETIM_PRIMARY, 0,
               PIIX4_UDMATIM + 2 - PIIX4_IDETIM_PRIMARY);
        pci_set_word(dev->wmask + PIIX4_IDETIM_PRIMARY, 0xf3ff);
        pci_set_word(dev->wmask + PIIX4_IDETIM_SECONDARY, 0xf3ff);
        dev->wmask[PIIX4_SIDETIM] = 0xff;
        dev->wmask[PIIX4_UDMACTL] = 0x0f;
        pci_set_word(dev->wmask + PIIX4_UDMATIM, 0x3333);
    }

    pci_piix_ide_realize(dev, errp);
}

static const Property piix4_ide_properties[] = {
    DEFINE_PROP_BOOL("strict-timing-regs", PCIIDEState,
                     piix4_strict_timing_regs, false),
};

/* NOTE: for the PIIX4, the IRQs and IOports are hardcoded */
static void piix4_ide_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    device_class_set_legacy_reset(dc, piix4_ide_reset);
    dc->vmsd = &vmstate_ide_pci;
    k->realize = pci_piix4_ide_realize;
    k->exit = pci_piix_ide_exitfn;
    k->vendor_id = PCI_VENDOR_ID_INTEL;
    k->device_id = PCI_DEVICE_ID_INTEL_82371AB;
    device_class_set_props(dc, piix4_ide_properties);
    dc->desc = "Intel 82371AB PIIX4 PCI IDE controller";
    k->class_id = PCI_CLASS_STORAGE_IDE;
    set_bit(DEVICE_CATEGORY_STORAGE, dc->categories);
    dc->hotpluggable = false;
}

static const TypeInfo piix4_ide_info = {
    .name          = TYPE_PIIX4_IDE,
    .parent        = TYPE_PCI_IDE,
    .class_init    = piix4_ide_class_init,
};

static void piix_ide_register_types(void)
{
    type_register_static(&piix3_ide_info);
    type_register_static(&piix4_ide_info);
}

type_init(piix_ide_register_types)
