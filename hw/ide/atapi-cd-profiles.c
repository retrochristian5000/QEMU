/*
 * Historical ATAPI CD-ROM compatibility profiles.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "hw/ide/ide-dev.h"

/*
 * Toshiba XM-6202B: Toshiba announcement (1997-11-12) and 1999
 * Disk/Trend specification, Toshiba table, XM-6202B column.
 * Linux libata identifies this model with ATA_HORKAGE_NODMA.
 * Report documented capabilities without fabricating firmware timing.
 */
static void xm6202b_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    IDEDeviceClass *k = IDE_DEVICE_CLASS(klass);

    dc->desc = "Toshiba XM-6202B (32x ATAPI CD-ROM compatibility profile)";
    k->atapi_cd_only = true;
    k->atapi_default_model = "TOSHIBA CD-ROM XM-6202B";
    k->atapi_inquiry_vendor = "TOSHIBA";
    k->atapi_inquiry_product = "CD-ROM XM-6202B";
    k->atapi_read_speed = 4800;
    k->atapi_buffer_kib = 256;
    k->atapi_pio_only = true;
}

static const TypeInfo xm6202b_info = {
    .name = "toshiba-xm-6202b",
    .parent = "ide-cd",
    .class_init = xm6202b_class_init,
};

static void atapi_cd_register_types(void)
{
    type_register_static(&xm6202b_info);
}

type_init(atapi_cd_register_types)
