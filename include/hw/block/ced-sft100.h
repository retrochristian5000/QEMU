/*
 * Standalone RCA SelectaVision SFT100 QOM device.
 * Host/front-panel API; no invented guest I/O ports or QMP commands.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_BLOCK_CED_SFT100_H
#define HW_BLOCK_CED_SFT100_H

#include "hw/block/ced-sft100-control.h"
#include <stddef.h>
#include "hw/core/qdev.h"
#include "qom/object.h"

#define TYPE_RCA_SFT100 "rca-sft100"
OBJECT_DECLARE_SIMPLE_TYPE(RcaSft100State, RCA_SFT100)

typedef struct RcaSft100Status {
    CedSft100Lever lever;
    CedTransportState state;
    CedSft100RFSource rf_source;
    uint32_t field;
    uint8_t side;
    uint8_t rf_channel;
    bool motor_running;
    bool video_visible;
    bool audio_audible;
    bool stylus_engaged;
} RcaSft100Status;

/* Call only on a realized instance from the emulation/I/O thread. */
bool rca_sft100_set_lever(RcaSft100State *s, CedSft100Lever lever);
bool rca_sft100_insert(RcaSft100State *s, const CedMedia *media, uint8_t side);
bool rca_sft100_remove(RcaSft100State *s);
bool rca_sft100_pause_toggle(RcaSft100State *s);
bool rca_sft100_search(RcaSft100State *s, bool forward);
bool rca_sft100_search_release(RcaSft100State *s);
bool rca_sft100_rapid_access(RcaSft100State *s, uint32_t target_field);
bool rca_sft100_select_channel(RcaSft100State *s, uint8_t channel);
/* Read a coherent host-side snapshot.  No analog RF or picture samples. */
void rca_sft100_get_status(RcaSft100State *s, RcaSft100Status *out);
/* Backend-only post-demodulation mono signed16 PCM at 48000 Hz.
 * Calls must originate on the device emulation thread.  No FM decoder yet.
 * Returns frames queued (may be less than requested), zero if muted.
 */
size_t rca_sft100_submit_pcm(RcaSft100State *s,
                             const int16_t *samples, size_t frames);

#endif /* HW_BLOCK_CED_SFT100_H */
