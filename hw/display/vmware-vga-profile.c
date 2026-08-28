/*
 * QEMU VMware SVGA runtime profile
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "qemu/module.h"
#include "qom/object.h"

static void vmware_vga_register_description(void)
{
    ObjectClass *klass = object_class_by_name("vmware-svga");

    g_assert(klass);
    DEVICE_CLASS(klass)->desc = "VMware SVGA II PCI VGA controller";
}

opts_init(vmware_vga_register_description)
