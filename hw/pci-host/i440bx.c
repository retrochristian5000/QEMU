/*
 * Intel 82443BX host bridge, initial AGP-disabled model.
 *
 * Hardware reference: Intel 82443BX datasheet, order 290633-001,
 * chapter 3 (device 0 configuration registers).
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/range.h"
#include "qemu/units.h"
#include "hw/core/boards.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_device.h"
#include "hw/pci/pci_ids.h"
#include "hw/pci-host/i440fx.h"
#include "hw/pci-host/i440bx.h"
#include "migration/vmstate.h"
#include "qapi/error.h"

#define BX_DRAMC       0x57
#define BX_DRAMT       0x58
#define BX_PAM         0x59
#define BX_PAM_COUNT   7
#define BX_DRB         0x60
#define BX_DRB_COUNT   8
#define BX_SMRAM       0x72
#define BX_ESMRAMC     0x73
#define BX_PMCR        0x7a
#define BX_AGP_DIS     0x02
#define BX_ROW_UNIT    (8 * MiB)
#define BX_ROW_MAX     (128 * MiB)

/*
 * QEMU maps RAM at machine creation. Report a deterministic synthetic
 * row layout; do not let DRB writes silently change the reported size
 * without implementing DRAM address decoding.
 */
static void i440bx_reset_config(PCIDevice *dev)
{
    uint64_t remaining = MACHINE(qdev_get_machine())->ram_size;
    unsigned boundary = 0;
    unsigned i;

    pci_set_word(dev->config + PCI_COMMAND,
                 PCI_COMMAND_MEMORY | PCI_COMMAND_MASTER);
    pci_set_word(dev->config + PCI_STATUS, 0x0200);
    dev->config[BX_DRAMC] = 0;
    dev->config[BX_DRAMT] = 0x03;
    memset(dev->config + BX_PAM, 0, BX_PAM_COUNT);

    for (i = 0; i < BX_DRB_COUNT; i++) {
        uint64_t row = MIN(remaining, BX_ROW_MAX);

        remaining -= row;
        boundary += row / BX_ROW_UNIT;
        dev->config[BX_DRB + i] = boundary;
    }

    dev->config[BX_SMRAM] = SMRAM_C_BASE_SEG;
    dev->config[BX_ESMRAMC] = 0x38;
    dev->config[BX_PMCR] = BX_AGP_DIS;
}

static void i440bx_reset(DeviceState *dev)
{
    i440bx_reset_config(PCI_DEVICE(dev));
    i440fx_update_memory_mappings(I440FX_PCI_DEVICE(dev));
}

static void i440bx_realize(PCIDevice *dev, Error **errp)
{
    PCII440FXState *s = I440FX_PCI_DEVICE(dev);
    uint64_t ram = MACHINE(qdev_get_machine())->ram_size;

    if (ram < BX_ROW_UNIT || ram > GiB || ram % BX_ROW_UNIT) {
        error_setg(errp, "440BX requires 8 MiB to 1 GiB of RAM "
                   "in 8 MiB increments");
        return;
    }

    /* Offset 0x57 is DRAMC, not the i440FX coreboot compatibility byte. */
    s->skip_legacy_coreboot_ram_size = true;

    /* Only expose writable fields whose effects are implemented. */
    memset(dev->wmask + PCI_CONFIG_HEADER_SIZE, 0,
           PCI_CONFIG_SPACE_SIZE - PCI_CONFIG_HEADER_SIZE);
    pci_set_word(dev->wmask + PCI_COMMAND, 0);
    pci_set_word(dev->w1cmask + PCI_STATUS, 0);
    dev->wmask[PCI_CACHE_LINE_SIZE] = 0;
    dev->wmask[PCI_INTERRUPT_LINE] = 0;
    pci_set_word(dev->config + PCI_SUBSYSTEM_VENDOR_ID, 0);
    pci_set_word(dev->config + PCI_SUBSYSTEM_ID, 0);

    dev->wmask[BX_PAM] = 0x30;
    memset(dev->wmask + BX_PAM + 1, 0x33, BX_PAM_COUNT - 1);
    dev->wmask[BX_SMRAM] = SMRAM_G_SMRAME | SMRAM_D_LCK | SMRAM_D_OPEN;

    i440bx_reset_config(dev);
}

static void i440bx_write_config(PCIDevice *dev, uint32_t addr,
                                 uint32_t val, int len)
{
    uint8_t old_pam[BX_PAM_COUNT];
    uint8_t old_smram = dev->config[BX_SMRAM];
    bool pam_write = ranges_overlap(addr, len, BX_PAM, BX_PAM_COUNT);
    bool smram_write = range_covers_byte(addr, len, BX_SMRAM);

    if (pam_write) {
        memcpy(old_pam, dev->config + BX_PAM, sizeof(old_pam));
    }

    pci_default_write_config(dev, addr, val, len);

    /* D_LCK is sticky until reset and forces D_OPEN clear. */
    if (smram_write && ((old_smram | dev->config[BX_SMRAM]) & SMRAM_D_LCK)) {
        dev->config[BX_SMRAM] |= SMRAM_D_LCK;
        dev->config[BX_SMRAM] &= ~SMRAM_D_OPEN;
    }

    if ((pam_write && memcmp(old_pam, dev->config + BX_PAM,
                            sizeof(old_pam))) ||
        (smram_write && old_smram != dev->config[BX_SMRAM])) {
        i440fx_update_memory_mappings(I440FX_PCI_DEVICE(dev));
    }
}

static int i440bx_post_load(void *opaque, int version_id)
{
    i440fx_update_memory_mappings(opaque);
    return 0;
}

static const VMStateDescription vmstate_i440bx = {
    .name = "I440BX",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = i440bx_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_PCI_DEVICE(parent_obj, PCII440FXState),
        VMSTATE_END_OF_LIST()
    }
};

static void i440bx_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *pc = PCI_DEVICE_CLASS(klass);

    pc->realize = i440bx_realize;
    pc->config_write = i440bx_write_config;
    pc->device_id = PCI_DEVICE_ID_INTEL_82443BX_NO_AGP;
    pc->revision = 0x02;
    dc->desc = "Intel 82443BX host bridge (AGP disabled, experimental)";
    dc->vmsd = &vmstate_i440bx;
    device_class_set_legacy_reset(dc, i440bx_reset);
}

static const TypeInfo i440bx_info = {
    .name = TYPE_I440BX_PCI_DEVICE,
    .parent = TYPE_I440FX_PCI_DEVICE,
    .instance_size = sizeof(PCII440FXState),
    .class_init = i440bx_class_init,
};

static void i440bx_register_types(void)
{
    type_register_static(&i440bx_info);
}

type_init(i440bx_register_types)
