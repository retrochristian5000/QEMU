/*
 * Cocoa Metal bridge helpers.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_COCOA_METAL_H
#define QEMU_COCOA_METAL_H

#include <stdbool.h>
#include <stdint.h>

/*
 * Keep Objective-C types out of this header so cocoa.m and the rest of the UI
 * can exchange an optional native Metal texture without adding Metal headers
 * to generic display code.
 */
bool qemu_cocoa_metal_can_use_texture(void *view, void *texture,
                                      uint32_t width, uint32_t height);
void qemu_cocoa_metal_set_texture(void *view, void *texture,
                                  uint32_t width, uint32_t height);
void qemu_cocoa_metal_clear_texture(void *view);

#endif /* QEMU_COCOA_METAL_H */
