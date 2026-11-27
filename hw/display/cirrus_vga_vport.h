/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DISPLAY_CIRRUS_VGA_VPORT_H
#define HW_DISPLAY_CIRRUS_VGA_VPORT_H

#include <stdint.h>

/*
 * GD5446 TRM 6.15-6.21 and 6.25: capture-only CRTC controls.
 * CR58-CR5A and CR5E are shared with video playback.
 * CR55 is reserved; CR5B is a playback brightness control.
 */
static inline uint8_t cirrus_vport_reg_mask(unsigned index)
{
    switch (index) {
    case 0x50:
    case 0x57:
    case 0x5c:
        return 0xff;
    case 0x51:
        return 0x0f;
    case 0x52:
    case 0x53:
        return 0x07;
    case 0x54:
    case 0x56:
        return 0x1f;
    default:
        return 0;
    }
}

/*
 * TRM 8.26: programmable outputs, feature-connector direction and
 * interrupt enable. With no V-Port source, interrupt pending remains
 * clear. Active display line readback is separate from capture.
 */
#define CIRRUS_VPORT_GR17_CONTROL_MASK 0x6c

#endif
