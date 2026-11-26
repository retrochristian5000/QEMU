/*
 * Historical ATA hard disk identity profiles.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * These profiles inherit the generic ATA engine with revision-specific
 * command and identification restrictions. Vendor firmware and mechanical
 * timing are not reproduced.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "hw/ide/ide-dev.h"

static void ata_hd_identity_init(Object *obj, const char *model, uint16_t rpm,
                                 IDEATARevision revision)
{
    IDEDevice *dev = IDE_DEVICE(obj);

    /* Instance defaults precede compatibility and user property overrides. */
    g_free(dev->model);
    dev->model = g_strdup(model);
    dev->rotation_rate = rpm;
    dev->ata_revision = revision;
}

static void st31640a_init(Object *obj)
{
    ata_hd_identity_init(obj, "ST31640A", 5376, IDE_ATA_2);
}

static void st32140a_init(Object *obj)
{
    ata_hd_identity_init(obj, "ST32140A", 5376, IDE_ATA_2);
}

static void dtta351010_init(Object *obj)
{
    ata_hd_identity_init(obj, "IBM-DTTA-351010", 5400, IDE_ATA_4);
}

static void ata_hd_identity_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = data;
}

static const TypeInfo ata_hd_profiles[] = {
    {
        .name = "seagate-st31640a",
        .parent = "ide-hd",
        .instance_init = st31640a_init,
        .class_init = ata_hd_identity_class_init,
        .class_data = "Seagate Medalist 1640 (ATA-2 compatibility profile)",
    }, {
        .name = "seagate-st32140a",
        .parent = "ide-hd",
        .instance_init = st32140a_init,
        .class_init = ata_hd_identity_class_init,
        .class_data = "Seagate Medalist 2140 (ATA-2 compatibility profile)",
    }, {
        .name = "ibm-dtta-351010",
        .parent = "ide-hd",
        .instance_init = dtta351010_init,
        .class_init = ata_hd_identity_class_init,
        .class_data = "IBM Deskstar DTTA-351010 (ATA/ATAPI-4 compatibility profile)",
    },
};

DEFINE_TYPES(ata_hd_profiles)
