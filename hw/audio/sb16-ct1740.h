/* Creative Sound Blaster 16 CT1740 board policy.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_SB16_CT1740_H
#define HW_AUDIO_SB16_CT1740_H

#include "qapi/error.h"

#define TYPE_SB16_GENERIC "sb16-generic"
#define TYPE_CREATIVE_SB16 "sb16"

bool sb16_ct1740_validate(uint32_t base, uint32_t irq, uint32_t dma,
                          uint32_t hdma, uint32_t version, Error **errp);

#endif
