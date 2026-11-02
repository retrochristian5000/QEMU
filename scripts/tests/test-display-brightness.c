/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include "ui/display-brightness.h"
int main(void)
{
    uint8_t level = QEMU_DISPLAY_BRIGHTNESS_FULL;
    assert(level == 255);
    level = qemu_display_brightness_next(level);
    assert(level == QEMU_DISPLAY_BRIGHTNESS_DIM);
    level = qemu_display_brightness_next(level);
    assert(level == QEMU_DISPLAY_BRIGHTNESS_FULL);
    return 0;
}
