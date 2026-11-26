/*
 * Creative Sound Blaster AWE32 legacy ISA board profile.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The board combines an SB16-compatible DSP with the separate EMU8000
 * synthesizer. Do not expose the SB16 alone as an AWE32.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qapi/error.h"
#include "hw/isa/isa.h"

#define TYPE_AWE32 "awe32"

static void awe32_realize(DeviceState *dev, Error **errp)
{
    error_setg(errp, "awe32: EMU8000 synthesis and sound memory are not "
               "implemented; use sb16-generic for legacy PCM audio");
}

static void awe32_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Creative Sound Blaster AWE32 (reserved legacy ISA profile)";
    dc->realize = awe32_realize;
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
}

static const TypeInfo awe32_info = {
    .name = TYPE_AWE32,
    .parent = TYPE_ISA_DEVICE,
    .class_init = awe32_class_init,
};

static void awe32_register_types(void)
{
    type_register_static(&awe32_info);
}

type_init(awe32_register_types)
