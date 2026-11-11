/*
 * RCA CED format and mechanically meaningful virtual player transport.
 *
 * Digital descriptor images are test fixtures: a real CED contains an
 * analogue capacitance/FM recording, buried chroma and DAXI metadata.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/block/ced.h"

static const uint8_t ced_descriptor_magic[8] = {
    'W', 'H', 'P', '-', 'C', 'E', 'D', '1'
};

static uint32_t ced_get_le32(const uint8_t *data)
{
    return (uint32_t)data[0] | ((uint32_t)data[1] << 8) |
           ((uint32_t)data[2] << 16) | ((uint32_t)data[3] << 24);
}

static void ced_put_le32(uint8_t *data, uint32_t value)
{
    for (unsigned i = 0; i < 4; i++) {
        data[i] = (uint8_t)(value >> (8 * i));
    }
}

bool ced_media_valid(const CedMedia *media)
{
    if (!media || media->video != CED_VIDEO_NTSC ||
        (media->audio < CED_AUDIO_UNKNOWN ||
         media->audio > CED_AUDIO_INDEPENDENT) ||
        (media->daxi < CED_DAXI_UNEXAMINED ||
         media->daxi > CED_DAXI_VERIFIED) ||
        media->side_count < 1 || media->side_count > 2 ||
        media->side_fields[0] == 0) {
        return false;
    }
    if (media->side_count == 1) {
        return media->side_fields[1] == 0;
    }
    return media->side_fields[1] != 0;
}

bool ced_media_decode(const uint8_t *data, size_t len, CedMedia *media)
{
    CedMedia parsed;

    if (!data || !media || len != CED_DESCRIPTOR_SIZE ||
        memcmp(data, ced_descriptor_magic, sizeof(ced_descriptor_magic)) ||
        data[8] != 1 || data[13] || data[14] || data[15]) {
        return false;
    }
    parsed.video = data[9];
    parsed.audio = data[10];
    parsed.side_count = data[11];
    parsed.daxi = data[12];
    parsed.side_fields[0] = ced_get_le32(data + 16);
    parsed.side_fields[1] = ced_get_le32(data + 20);
    if (!ced_media_valid(&parsed)) {
        return false;
    }
    *media = parsed;
    return true;
}

bool ced_media_encode(const CedMedia *media,
                      uint8_t out[CED_DESCRIPTOR_SIZE])
{
    if (!out || !ced_media_valid(media)) {
        return false;
    }
    memset(out, 0, CED_DESCRIPTOR_SIZE);
    memcpy(out, ced_descriptor_magic, sizeof(ced_descriptor_magic));
    out[8] = 1;
    out[9] = (uint8_t)media->video;
    out[10] = (uint8_t)media->audio;
    out[11] = media->side_count;
    out[12] = (uint8_t)media->daxi;
    ced_put_le32(out + 16, media->side_fields[0]);
    ced_put_le32(out + 20, media->side_fields[1]);
    return true;
}

void ced_player_init(CedPlayer *player, CedTransportProfile profile)
{
    memset(player, 0, sizeof(*player));
    player->profile = profile;
    player->rf_channel = profile == CED_TRANSPORT_RCA_SFT100 ? 3 : 0;
    player->search_direction = 1;
}

bool ced_player_insert(CedPlayer *player, const CedMedia *media, uint8_t side)
{
    if (!player || player->state != CED_EMPTY ||
        !ced_media_valid(media) || side < 1 || side > media->side_count) {
        return false;
    }
    player->media = *media;
    player->side = side;
    player->position_fields = 0;
    player->seek_target_fields = 0;
    player->start_remaining_fields = 0;
    player->state = CED_RETAINED;
    return true;
}

bool ced_player_eject(CedPlayer *player)
{
    if (!player || (player->state != CED_RETAINED &&
                    player->state != CED_END_OF_SIDE)) {
        return false;
    }
    memset(&player->media, 0, sizeof(player->media));
    player->side = 0;
    player->position_fields = 0;
    player->seek_target_fields = 0;
    player->start_remaining_fields = 0;
    player->state = CED_EMPTY;
    return true;
}

bool ced_player_play(CedPlayer *player)
{
    if (!player || player->state == CED_EMPTY ||
        player->state == CED_RAPID_SEEK ||
        player->state == CED_END_OF_SIDE) {
        return false;
    }
    if (player->state == CED_PLAYING || player->state == CED_STARTING) {
        return true;
    }
    if (player->state == CED_RETAINED &&
        player->profile == CED_TRANSPORT_RCA_SFT100) {
        /* About eight seconds on the SFT100; 480 NTSC fields ~= 8 s. */
        player->start_remaining_fields = 480;
        player->state = CED_STARTING;
    } else {
        player->start_remaining_fields = 0;
        player->state = CED_PLAYING;
    }
    return true;
}

bool ced_player_pause(CedPlayer *player)
{
    if (!player || (player->state != CED_PLAYING &&
                    player->state != CED_VISUAL_SEARCH)) {
        return false;
    }
    player->state = CED_PAUSED;
    return true;
}

bool ced_player_stop(CedPlayer *player)
{
    if (!player || player->state == CED_EMPTY) {
        return false;
    }
    player->start_remaining_fields = 0;
    player->state = CED_RETAINED;
    return true;
}

bool ced_player_visual_search_direction(CedPlayer *player, bool forward)
{
    /* RCA SFT100 has nominal 16x visual search in both directions. */
    if (!player || player->profile != CED_TRANSPORT_RCA_SFT100 ||
        player->state != CED_PLAYING) {
        return false;
    }
    player->search_direction = forward ? 1 : -1;
    player->state = CED_VISUAL_SEARCH;
    return true;
}

bool ced_player_visual_search(CedPlayer *player)
{
    return ced_player_visual_search_direction(player, true);
}

bool ced_player_rapid_seek(CedPlayer *player, uint32_t target_field)
{
    if (!player || player->profile != CED_TRANSPORT_RCA_SFT100 ||
        player->state == CED_EMPTY || player->state == CED_STARTING ||
        target_field >= player->media.side_fields[player->side - 1]) {
        return false;
    }
    player->seek_target_fields = target_field;
    player->state = CED_RAPID_SEEK;
    return true;
}

void ced_player_step_fields(CedPlayer *player, uint64_t elapsed_fields)
{
    uint64_t advance, remaining;
    uint32_t side_length;

    if (!player || !elapsed_fields || player->state == CED_EMPTY) {
        return;
    }
    side_length = player->media.side_fields[player->side - 1];
    if (player->state == CED_RAPID_SEEK) {
        /* No mechanical seek-duration claim: complete on next clock step. */
        player->position_fields = player->seek_target_fields;
        player->state = CED_PAUSED;
        return;
    }
    if (player->state == CED_STARTING) {
        if (elapsed_fields < player->start_remaining_fields) {
            player->start_remaining_fields -= (uint32_t)elapsed_fields;
            return;
        }
        elapsed_fields -= player->start_remaining_fields;
        player->start_remaining_fields = 0;
        player->state = CED_PLAYING;
    }
    if (player->state != CED_PLAYING &&
        player->state != CED_VISUAL_SEARCH) {
        return;
    }
    if (player->state == CED_VISUAL_SEARCH &&
        player->search_direction < 0) {
        remaining = player->position_fields;
        advance = elapsed_fields >= (remaining + 15) / 16 ?
                  remaining : elapsed_fields * 16;
        player->position_fields -= (uint32_t)advance;
        if (!player->position_fields) {
            player->state = CED_PAUSED;
        }
        return;
    }
    remaining = side_length - player->position_fields;
    /* Clamp before multiplying: handles even UINT64_MAX field steps safely. */
    advance = player->state == CED_VISUAL_SEARCH ?
              (elapsed_fields >= (remaining + 15) / 16 ?
               remaining : elapsed_fields * 16) :
              (elapsed_fields >= remaining ? remaining : elapsed_fields);
    player->position_fields += (uint32_t)advance;
    if (player->position_fields == side_length) {
        player->state = CED_END_OF_SIDE;
    }
}

bool ced_player_set_rf_channel(CedPlayer *player, uint8_t channel)
{
    if (!player || player->profile != CED_TRANSPORT_RCA_SFT100 ||
        (channel != 3 && channel != 4)) {
        return false;
    }
    player->rf_channel = channel;
    return true;
}

bool ced_player_stylus_engaged(const CedPlayer *player)
{
    return player && (player->state == CED_PLAYING ||
                      player->state == CED_VISUAL_SEARCH);
}

bool ced_player_video_visible(const CedPlayer *player)
{
    return ced_player_stylus_engaged(player);
}

bool ced_player_audio_audible(const CedPlayer *player)
{
    return player && player->state == CED_PLAYING;
}

bool ced_player_motor_running(const CedPlayer *player)
{
    return player && (player->state == CED_STARTING ||
                      player->state == CED_PLAYING ||
                      player->state == CED_VISUAL_SEARCH ||
                      player->state == CED_PAUSED ||
                      player->state == CED_RAPID_SEEK);
}
