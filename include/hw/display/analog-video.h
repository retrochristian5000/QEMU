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

/*
 * Connection and conductor presence are independent of scan/color profiles.
 * S-Video Y includes synchronization.  C carries modulated chrominance.
 */
typedef enum AnalogVideoConnection {
    ANALOG_VIDEO_CONNECTION_NONE = 0,
    ANALOG_VIDEO_CONNECTION_COMPOSITE,
    ANALOG_VIDEO_CONNECTION_SVIDEO,
    ANALOG_VIDEO_CONNECTION__MAX,
} AnalogVideoConnection;

#define ANALOG_VIDEO_WIRE_CVBS (1U << 0)
#define ANALOG_VIDEO_WIRE_Y    (1U << 1)
#define ANALOG_VIDEO_WIRE_C    (1U << 2)

/* Standard S-Video four-pin mini-DIN numbering (grounds are not signals). */
typedef enum AnalogSVideoPin {
    ANALOG_SVIDEO_PIN_Y_GROUND = 1,
    ANALOG_SVIDEO_PIN_C_GROUND = 2,
    ANALOG_SVIDEO_PIN_Y = 3,
    ANALOG_SVIDEO_PIN_C = 4,
} AnalogSVideoPin;

typedef struct AnalogVideoBaseband {
    AnalogVideoSignal signal;
    AnalogVideoConnection connection;
    uint32_t wires;
} AnalogVideoBaseband;

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

/* Evaluate physical connection and Y/C presence before decoder lock. */
AnalogVideoReceiverLock
analog_video_baseband_lock(const AnalogVideoReceiverCaps *caps,
                           AnalogVideoConnection selected_input,
                           const AnalogVideoBaseband *source);

#endif /* HW_DISPLAY_ANALOG_VIDEO_H */
