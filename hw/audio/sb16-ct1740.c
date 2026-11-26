/*
 * Creative Sound Blaster 16 CT1740, initial fixed-jumper PCM profile.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Board-specific policy is separate from the shared DSP/mixer engine.
 * The CT1740/CT1730 jumper table identifies IOS0/IOS1, IS0/IS1,
 * DAS0/DAS1 and DBS0/DBS1 settings. IRQ2 is routed as IRQ9 on a PC/AT.
 * Select the documented DSP 4.05 variant; do not claim other revisions.
 * References: docs/system/devices/sb16.rst.
 */
#include "qemu/osdep.h"
#include "qemu/module.h"
#include "hw/core/qdev.h"
#include "migration/vmstate.h"
#include "sb16-ct1740.h"

bool sb16_ct1740_validate(uint32_t base, uint32_t irq, uint32_t dma,
                          uint32_t hdma, uint32_t version, Error **errp)
{
    if (base != 0x220 && base != 0x240 &&
        base != 0x260 && base != 0x280) {
        error_setg(errp, "sb16: CT1740 I/O base must be 0x220, 0x240, "
                   "0x260 or 0x280");
        return false;
    }
    if (irq != 5 && irq != 7 && irq != 9 && irq != 10) {
        error_setg(errp, "sb16: CT1740 IRQ must be 5, 7, 9 (IRQ2) or 10");
        return false;
    }
    if (dma != 0 && dma != 1 && dma != 3) {
        error_setg(errp, "sb16: CT1740 8-bit DMA channel must be 0, 1 or 3");
        return false;
    }
    if (hdma < 5 || hdma > 7) {
        error_setg(errp, "sb16: CT1740 16-bit DMA channel must be 5, 6 or 7");
        return false;
    }
    if (version != 0x0405) {
        error_setg(errp, "sb16: CT1740 profile requires DSP version 4.05 "
                   "(version=0x0405)");
        return false;
    }
    return true;
}

/* Do not silently interchange this board with the generic migration state. */
static const VMStateDescription vmstate_ct1740 = {
    .name = "creative-ct1740",
    .unmigratable = true,
};

static void sb16_ct1740_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "Creative Sound Blaster 16 CT1740 (experimental PCM and MIDI)";
    dc->fw_name = "creative-ct1740";
    dc->hotpluggable = false;
    dc->vmsd = &vmstate_ct1740;
    sb16_ct1740_add_midi_properties(dc);
}

static const TypeInfo sb16_ct1740_info = {
    .name = TYPE_CREATIVE_SB16,
    .parent = TYPE_SB16_GENERIC,
    .instance_init = sb16_ct1740_midi_init,
    .class_init = sb16_ct1740_class_init,
};

static void sb16_ct1740_register_types(void)
{
    type_register_static(&sb16_ct1740_info);
}

type_init(sb16_ct1740_register_types)
