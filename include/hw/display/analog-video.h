/*
 * Analogue television/video signal descriptors
 *
 * Keep scanning, composite colour coding and RF tuning as separate concepts.
 * NTSC, PAL and SECAM names must not be used as aliases for a particular
 * line/field timing or broadcast channel system.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_DISPLAY_ANALOG_VIDEO_H
#define HW_DISPLAY_ANALOG_VIDEO_H

#include <stdbool.h>
#include <stdint.h>

typedef enum AnalogVideoScanSystem {
    ANALOG_VIDEO_SCAN_NONE = 0,
    ANALOG_VIDEO_SCAN_525_59_94,
    ANALOG_VIDEO_SCAN_625_50,
    ANALOG_VIDEO_SCAN__MAX,
} AnalogVideoScanSystem;

/*
 * Baseband composite-colour encoding profile.  This is deliberately more
 * specific than the broad NTSC/PAL/SECAM family name: a decoder which handles
 * conventional PAL 4.43 is not thereby assumed to decode PAL-M or PAL-N.
 *
 * RF system letters, sound carriers and channel plans belong to a later RF
 * descriptor and must not be inferred from these values.
 */
typedef enum AnalogVideoColorEncoding {
    ANALOG_VIDEO_COLOR_MONOCHROME = 0,
    ANALOG_VIDEO_COLOR_NTSC_358,
    ANALOG_VIDEO_COLOR_PAL_443,
    ANALOG_VIDEO_COLOR_PAL_M,
    ANALOG_VIDEO_COLOR_PAL_N,
    ANALOG_VIDEO_COLOR_SECAM,
    ANALOG_VIDEO_COLOR__MAX,
} AnalogVideoColorEncoding;

typedef struct AnalogVideoTiming {
    uint16_t lines_per_frame;
    uint32_t field_rate_num;
    uint32_t field_rate_den;
    bool interlaced;
} AnalogVideoTiming;

typedef struct AnalogVideoSignal {
    AnalogVideoScanSystem scan;
    AnalogVideoColorEncoding color;
} AnalogVideoSignal;

#define ANALOG_VIDEO_SCAN_BIT(scan) (1U << (scan))
#define ANALOG_VIDEO_COLOR_BIT(color) (1U << (color))

typedef struct AnalogVideoReceiverCaps {
    uint32_t scan_mask;
    uint32_t color_mask;
} AnalogVideoReceiverCaps;

typedef enum AnalogVideoReceiverLock {
    ANALOG_VIDEO_LOCK_NONE = 0,
    ANALOG_VIDEO_LOCK_LUMA,
    ANALOG_VIDEO_LOCK_COLOR,
} AnalogVideoReceiverLock;

extern const AnalogVideoSignal analog_video_ntsc_525_59_94;
extern const AnalogVideoSignal analog_video_pal_625_50;
extern const AnalogVideoSignal analog_video_pal_m_525_59_94;
extern const AnalogVideoSignal analog_video_pal_n_625_50;
extern const AnalogVideoSignal analog_video_secam_625_50;

const AnalogVideoTiming *analog_video_get_timing(AnalogVideoScanSystem scan);

/*
 * Return the line rate as an exact rational derived from field timing.  The
 * caller may pass NULL for either output it does not need.
 */
bool analog_video_get_line_rate(AnalogVideoScanSystem scan,
                                uint64_t *numerator,
                                uint64_t *denominator);

/*
 * A receiver can lock to luminance/sync without understanding the transmitted
 * composite-colour encoding.  This distinction is important for monochrome
 * monitors and for multi-standard television hardware.
 */
AnalogVideoReceiverLock
analog_video_receiver_lock(const AnalogVideoReceiverCaps *caps,
                           const AnalogVideoSignal *signal);

#endif /* HW_DISPLAY_ANALOG_VIDEO_H */
