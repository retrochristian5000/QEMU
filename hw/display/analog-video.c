/*
 * Analogue television/video signal descriptors
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/display/analog-video.h"

static const AnalogVideoTiming analog_video_timings[] = {
    [ANALOG_VIDEO_SCAN_525_59_94] = {
        .lines_per_frame = 525,
        .field_rate_num = 60000,
        .field_rate_den = 1001,
        .interlaced = true,
    },
    [ANALOG_VIDEO_SCAN_625_50] = {
        .lines_per_frame = 625,
        .field_rate_num = 50,
        .field_rate_den = 1,
        .interlaced = true,
    },
};

const AnalogVideoSignal analog_video_ntsc_525_59_94 = {
    .scan = ANALOG_VIDEO_SCAN_525_59_94,
    .color = ANALOG_VIDEO_COLOR_NTSC_358,
};

const AnalogVideoSignal analog_video_pal_625_50 = {
    .scan = ANALOG_VIDEO_SCAN_625_50,
    .color = ANALOG_VIDEO_COLOR_PAL_443,
};

/* PAL-M is intentionally present to prevent PAL from becoming a 625/50 alias. */
const AnalogVideoSignal analog_video_pal_m_525_59_94 = {
    .scan = ANALOG_VIDEO_SCAN_525_59_94,
    .color = ANALOG_VIDEO_COLOR_PAL_M,
};

/* PAL-N is a distinct baseband profile despite sharing the 625/50 scan family. */
const AnalogVideoSignal analog_video_pal_n_625_50 = {
    .scan = ANALOG_VIDEO_SCAN_625_50,
    .color = ANALOG_VIDEO_COLOR_PAL_N,
};

const AnalogVideoSignal analog_video_secam_625_50 = {
    .scan = ANALOG_VIDEO_SCAN_625_50,
    .color = ANALOG_VIDEO_COLOR_SECAM,
};

const AnalogVideoTiming *analog_video_get_timing(AnalogVideoScanSystem scan)
{
    if (scan <= ANALOG_VIDEO_SCAN_NONE || scan >= ANALOG_VIDEO_SCAN__MAX) {
        return NULL;
    }

    return &analog_video_timings[scan];
}

bool analog_video_get_line_rate(AnalogVideoScanSystem scan,
                                uint64_t *numerator,
                                uint64_t *denominator)
{
    const AnalogVideoTiming *timing = analog_video_get_timing(scan);
    uint64_t den;

    if (!timing) {
        return false;
    }

    den = timing->field_rate_den;
    if (timing->interlaced) {
        den *= 2;
    }

    if (numerator) {
        *numerator = (uint64_t)timing->field_rate_num *
                     timing->lines_per_frame;
    }
    if (denominator) {
        *denominator = den;
    }

    return true;
}

AnalogVideoReceiverLock
analog_video_receiver_lock(const AnalogVideoReceiverCaps *caps,
                           const AnalogVideoSignal *signal)
{
    if (!caps || !signal ||
        signal->scan <= ANALOG_VIDEO_SCAN_NONE ||
        signal->scan >= ANALOG_VIDEO_SCAN__MAX ||
        signal->color >= ANALOG_VIDEO_COLOR__MAX) {
        return ANALOG_VIDEO_LOCK_NONE;
    }

    if (!(caps->scan_mask & ANALOG_VIDEO_SCAN_BIT(signal->scan))) {
        return ANALOG_VIDEO_LOCK_NONE;
    }

    if (signal->color == ANALOG_VIDEO_COLOR_MONOCHROME) {
        return ANALOG_VIDEO_LOCK_LUMA;
    }

    if (caps->color_mask & ANALOG_VIDEO_COLOR_BIT(signal->color)) {
        return ANALOG_VIDEO_LOCK_COLOR;
    }

    return ANALOG_VIDEO_LOCK_LUMA;
}
