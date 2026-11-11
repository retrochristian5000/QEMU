/*
 * Dirty-rectangle conversion for the QEMU Cocoa Metal renderer
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_COCOA_METAL_DIRTY_H
#define QEMU_COCOA_METAL_DIRTY_H

#include <stdbool.h>

typedef struct QEMUCocoaMetalDirtyRect {
    int x;
    int y;
    int width;
    int height;
} QEMUCocoaMetalDirtyRect;

static inline int qemu_cocoa_metal_clamp(int value, int low, int high)
{
    if (value < low) {
        return low;
    }
    if (value > high) {
        return high;
    }
    return value;
}

/*
 * Cocoa's dirty rectangles use a bottom-left origin while the pixman image
 * and Metal texture rows use a top-left origin.  Inputs are integer edges in
 * Cocoa coordinates.  Clip them to the framebuffer before flipping Y.
 */
static inline bool qemu_cocoa_metal_dirty_rect(
    int framebuffer_width, int framebuffer_height,
    int x0, int y0, int x1, int y1,
    QEMUCocoaMetalDirtyRect *out)
{
    if (framebuffer_width <= 0 || framebuffer_height <= 0 || !out) {
        return false;
    }

    x0 = qemu_cocoa_metal_clamp(x0, 0, framebuffer_width);
    x1 = qemu_cocoa_metal_clamp(x1, 0, framebuffer_width);
    y0 = qemu_cocoa_metal_clamp(y0, 0, framebuffer_height);
    y1 = qemu_cocoa_metal_clamp(y1, 0, framebuffer_height);

    if (x1 <= x0 || y1 <= y0) {
        return false;
    }

    out->x = x0;
    out->y = framebuffer_height - y1;
    out->width = x1 - x0;
    out->height = y1 - y0;
    return true;
}

#endif /* QEMU_COCOA_METAL_DIRTY_H */
