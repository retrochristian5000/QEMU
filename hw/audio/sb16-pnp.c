/*
 * Creative Sound Blaster 16 Plug and Play profile.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Keep the later ISA PnP family separate from the legacy sb16 device.
 * Do not expose a legacy DSP under a PnP identity until the ISA PnP
 * bus can enumerate and activate its logical devices.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qapi/error.h"
#include "hw/isa/isa.h"

#define TYPE_SB16_PNP "sb16-pnp"

static void sb16_pnp_realize(DeviceState *dev, Error **errp)
{
    error_setg(errp, "sb16-pnp requires ISA Plug and Play enumeration "
               "and resource activation, which are not yet implemented");
}

static void sb16_pnp_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Creative Sound Blaster 16 Plug and Play (reserved profile)";
    dc->realize = sb16_pnp_realize;
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
}

static const TypeInfo sb16_pnp_info = {
    .name = TYPE_SB16_PNP,
    .parent = TYPE_ISA_DEVICE,
    .class_init = sb16_pnp_class_init,
};

static void sb16_pnp_register_types(void)
{
    type_register_static(&sb16_pnp_info);
}

type_init(sb16_pnp_register_types)
