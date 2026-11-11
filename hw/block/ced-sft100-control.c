/*
 * RCA SFT100 VideoDisc front-panel control and virtual-time accounting.
 * Only externally documented behavior; no guessed 1981 microcontroller map.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/block/ced-sft100-control.h"

#define SFT100_NS_PER_SEC UINT64_C(1000000000)
#define SFT100_FIELD_DEN (UINT64_C(1001) * SFT100_NS_PER_SEC)

void ced_sft100_control_init(CedSft100Control *s)
{
    memset(s, 0, sizeof(*s));
    ced_player_init(&s->player, CED_TRANSPORT_RCA_SFT100);
    s->lever = CED_SFT100_OFF;
}

bool ced_sft100_set_lever(CedSft100Control *s, CedSft100Lever lever)
{
    if (!s || lever < CED_SFT100_OFF || lever > CED_SFT100_PLAY) {
        return false;
    }
    if (s->lever == lever) {
        return true;
    }
    if (lever == CED_SFT100_PLAY && s->player.side &&
        s->player.state != CED_END_OF_SIDE &&
        !ced_player_play(&s->player)) {
        return false;
    }
    if (lever != CED_SFT100_PLAY && s->player.side) {
        /* Moving the function lever back stops playback; caddy stays in. */
        ced_player_stop(&s->player);
    }
    s->field_phase = 0;
    s->lever = lever;
    return true;
}

bool ced_sft100_insert(CedSft100Control *s, const CedMedia *media,
                       uint8_t side)
{
    if (!s || s->lever != CED_SFT100_LOAD_UNLOAD ||
        !ced_player_insert(&s->player, media, side)) {
        return false;
    }
    s->field_phase = 0;
    return true;
}

bool ced_sft100_remove(CedSft100Control *s)
{
    if (!s || s->lever != CED_SFT100_LOAD_UNLOAD ||
        !ced_player_eject(&s->player)) {
        return false;
    }
    s->field_phase = 0;
    return true;
}

bool ced_sft100_pause_toggle(CedSft100Control *s)
{
    if (!s || s->lever != CED_SFT100_PLAY) {
        return false;
    }
    if (s->player.state == CED_PAUSED) {
        return ced_player_play(&s->player);
    }
    return ced_player_pause(&s->player);
}

bool ced_sft100_search(CedSft100Control *s, bool forward)
{
    if (!s || s->lever != CED_SFT100_PLAY) {
        return false;
    }
    return ced_player_visual_search_direction(&s->player, forward);
}

bool ced_sft100_search_release(CedSft100Control *s)
{
    if (!s || s->lever != CED_SFT100_PLAY ||
        s->player.state != CED_VISUAL_SEARCH) {
        return false;
    }
    return ced_player_play(&s->player);
}

bool ced_sft100_rapid_access(CedSft100Control *s, uint32_t target_field)
{
    if (!s || s->lever != CED_SFT100_PLAY ||
        s->player.state == CED_END_OF_SIDE) {
        return false;
    }
    return ced_player_rapid_seek(&s->player, target_field);
}

bool ced_sft100_select_channel(CedSft100Control *s, uint8_t channel)
{
    return s && ced_player_set_rf_channel(&s->player, channel);
}

bool ced_sft100_clock_active(const CedSft100Control *s)
{
    if (!s || s->lever != CED_SFT100_PLAY) {
        return false;
    }
    return s->player.state == CED_STARTING ||
           s->player.state == CED_PLAYING ||
           s->player.state == CED_VISUAL_SEARCH ||
           s->player.state == CED_RAPID_SEEK;
}

void ced_sft100_advance_ns(CedSft100Control *s, uint64_t delta_ns)
{
    uint64_t seconds, ns, block, remainder;
    uint64_t fields, numerator;

    if (!ced_sft100_clock_active(s) || !delta_ns) {
        return;
    }
    /*
     * 60000/1001 fields/sec.  Split before multiplying to avoid overflow
     * even for UINT64_MAX elapsed ns.  No __int128 compiler dependence.
     */
    seconds = delta_ns / SFT100_NS_PER_SEC;
    ns = delta_ns % SFT100_NS_PER_SEC;
    block = seconds / 1001;
    remainder = seconds % 1001;
    fields = block * CED_NTSC_FIELD_RATE_NUM;
    numerator = ((remainder * SFT100_NS_PER_SEC + ns) *
                 CED_NTSC_FIELD_RATE_NUM) + s->field_phase;
    fields += numerator / SFT100_FIELD_DEN;
    s->field_phase = numerator % SFT100_FIELD_DEN;
    if (fields) {
        ced_player_step_fields(&s->player, fields);
    }
    /* Never bank partial fields across a detached/finished side. */
    if (!ced_sft100_clock_active(s)) {
        s->field_phase = 0;
    }
}

bool ced_sft100_motor_running(const CedSft100Control *s)
{
    return s && s->lever == CED_SFT100_PLAY &&
           ced_player_motor_running(&s->player);
}

bool ced_sft100_video_visible(const CedSft100Control *s)
{
    return s && s->lever == CED_SFT100_PLAY &&
           ced_player_video_visible(&s->player);
}

bool ced_sft100_audio_audible(const CedSft100Control *s)
{
    return s && s->lever == CED_SFT100_PLAY &&
           ced_player_audio_audible(&s->player);
}

CedSft100RFSource ced_sft100_rf_source(const CedSft100Control *s)
{
    return s && s->lever != CED_SFT100_OFF ? CED_SFT100_RF_PLAYER :
           CED_SFT100_RF_ANTENNA;
}
