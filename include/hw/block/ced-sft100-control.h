/*
 * Front-panel controls and rational field clock of RCA SFT100.
 * Pure transport control: no QOM, timer or video decoder dependencies.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_BLOCK_CED_SFT100_CONTROL_H
#define HW_BLOCK_CED_SFT100_CONTROL_H

#include "hw/block/ced.h"

typedef enum CedSft100Lever {
    CED_SFT100_OFF = 0,
    CED_SFT100_LOAD_UNLOAD = 1,
    CED_SFT100_PLAY = 2,
} CedSft100Lever;

typedef enum CedSft100RFSource {
    CED_SFT100_RF_ANTENNA = 0,
    CED_SFT100_RF_PLAYER = 1,
} CedSft100RFSource;

typedef struct CedSft100Control {
    CedPlayer player;
    CedSft100Lever lever;
    /* Fractional units of field-rate numerator / (1001 * 1e9 ns). */
    uint64_t field_phase;
} CedSft100Control;

void ced_sft100_control_init(CedSft100Control *s);
bool ced_sft100_set_lever(CedSft100Control *s, CedSft100Lever lever);
bool ced_sft100_insert(CedSft100Control *s, const CedMedia *media,
                       uint8_t side);
bool ced_sft100_remove(CedSft100Control *s);
bool ced_sft100_pause_toggle(CedSft100Control *s);
bool ced_sft100_search(CedSft100Control *s, bool forward);
bool ced_sft100_search_release(CedSft100Control *s);
/* Abstract target position; does not claim physical button hold duration. */
bool ced_sft100_rapid_access(CedSft100Control *s, uint32_t target_field);
bool ced_sft100_select_channel(CedSft100Control *s, uint8_t channel);
/* Exact field-rate time accumulation; virtual time does not use wall clock. */
void ced_sft100_advance_ns(CedSft100Control *s, uint64_t delta_ns);
bool ced_sft100_clock_active(const CedSft100Control *s);
bool ced_sft100_motor_running(const CedSft100Control *s);
bool ced_sft100_video_visible(const CedSft100Control *s);
bool ced_sft100_audio_audible(const CedSft100Control *s);
CedSft100RFSource ced_sft100_rf_source(const CedSft100Control *s);

#endif /* HW_BLOCK_CED_SFT100_CONTROL_H */
