/*
 * QEMU ATI VGA runtime profile
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/core/qdev.h"
#include "qemu/module.h"
#include "qom/compat-properties.h"
#include "qom/object.h"

/*
 * Keep Pixman fills enabled, but do not enable Pixman blits by default.
 * Reverse/overlapping screen copies can otherwise allocate a temporary
 * image for every blit.  An explicit x-pixman= setting still overrides
 * this profile after device construction.
 */
static void ati_vga_register_profile(void)
{
#ifdef CONFIG_PIXMAN
    object_register_sugar_prop("ati-vga", "x-pixman", "1", false);
#endif
}

static void ati_vga_register_description(void)
{
    ObjectClass *klass = object_class_by_name("ati-vga");

    g_assert(klass);
    DEVICE_CLASS(klass)->desc =
        "ATI Rage 128 Pro / Radeon RV100 PCI VGA controller";
}

type_init(ati_vga_register_profile)
opts_init(ati_vga_register_description)
