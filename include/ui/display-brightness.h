/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Software preview brightness; not calibrated historical luminance. */
#ifndef UI_DISPLAY_BRIGHTNESS_H
#define UI_DISPLAY_BRIGHTNESS_H
#include <stdint.h>
#define QEMU_DISPLAY_BRIGHTNESS_FULL 255u
#define QEMU_DISPLAY_BRIGHTNESS_DIM  166u
static inline uint8_t qemu_display_brightness_next(uint8_t level)
{
    return level == QEMU_DISPLAY_BRIGHTNESS_FULL ?
        QEMU_DISPLAY_BRIGHTNESS_DIM : QEMU_DISPLAY_BRIGHTNESS_FULL;
}
#endif
