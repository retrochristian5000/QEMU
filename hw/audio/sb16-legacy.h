/* Creative Sound Blaster 16 fixed-jumper ISA board policy.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_SB16_LEGACY_H
#define HW_AUDIO_SB16_LEGACY_H

#include "qapi/error.h"
#include "hw/core/qdev.h"

#define TYPE_SB16_GENERIC "sb16-generic"
#define TYPE_CREATIVE_SB16 "sb16-ct1740"

const char *sb16_legacy_model(Object *obj);
bool sb16_legacy_validate(Object *obj, uint32_t base, uint32_t irq,
                          uint32_t dma, uint32_t hdma, uint32_t version,
                          uint32_t mpu_base, Error **errp);
void sb16_legacy_add_midi_properties(DeviceClass *dc);
void sb16_legacy_midi_init(Object *obj);

#endif
