/*
 * Sierra Semiconductor Falcon/64 SC15064 PCI VGA compatibility device
 *
 * The first stage intentionally presents the real SC15064 PCI identity and
 * memory envelope while reusing QEMU's mature PCI VGA/VBE implementation.
 * The QEMU MMIO/VBE extension registers are compatibility infrastructure;
 * they are not claimed to be native Falcon/64 accelerator registers.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "hw/pci/pci.h"
#include "hw/pci/pci_ids.h"
#include "qemu/module.h"
#include "qom/object.h"

#define TYPE_SIERRA_FALCON64 "sierra-falcon64"

static void (*sierra_falcon64_parent_realize)(PCIDevice *dev, Error **errp);

static void sierra_falcon64_realize(PCIDevice *dev, Error **errp)
{
    Error *local_err = NULL;
    uint64_t vram_mb;

    vram_mb = object_property_get_uint(OBJECT(dev), "vgamem_mb", &local_err);
    if (local_err) {
        error_propagate(errp, local_err);
        return;
    }

    if (vram_mb != 1 && vram_mb != 2 && vram_mb != 4) {
        error_setg(errp,
                   TYPE_SIERRA_FALCON64
                   ": vgamem_mb must be 1, 2, or 4 MiB (got %" PRIu64 ")",
                   vram_mb);
        return;
    }

    sierra_falcon64_parent_realize(dev, errp);
}

static void sierra_falcon64_instance_init(Object *obj)
{
    /* Falcon/64 boards were populated with at most 4 MiB of display RAM. */
    object_property_set_uint(obj, "vgamem_mb", 4, &error_abort);
}

static void sierra_falcon64_class_init(ObjectClass *klass, const void *data)
{
    PCIDeviceClass *pc = PCI_DEVICE_CLASS(klass);

    sierra_falcon64_parent_realize = pc->realize;
    pc->realize = sierra_falcon64_realize;
    pc->vendor_id = PCI_VENDOR_ID_SIERRA;
    pc->device_id = PCI_DEVICE_ID_SIERRA_SC15064;
}

static const TypeInfo sierra_falcon64_info = {
    .name = TYPE_SIERRA_FALCON64,
    /* Reuse the existing PCI VGA framebuffer, VBE, EDID and migration ABI. */
    .parent = "VGA",
    .instance_init = sierra_falcon64_instance_init,
    .class_init = sierra_falcon64_class_init,
};

static void sierra_falcon64_register_types(void)
{
    type_register_static(&sierra_falcon64_info);
}

type_init(sierra_falcon64_register_types)
