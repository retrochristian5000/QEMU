/*
 * RCA Capacitance Electronic Disc (CED) format descriptors and transport.
 *
 * This models documented disc properties and physical player operations,
 * not a digitized capacitance waveform or a CED video/audio decoder.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_BLOCK_CED_H
#define HW_BLOCK_CED_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* RCA NTSC CED: eight fields / four frames per disc revolution. */
#define CED_NTSC_FIELDS_PER_REV 8U
#define CED_NTSC_FIELD_RATE_NUM 60000U
#define CED_NTSC_FIELD_RATE_DEN 1001U
#define CED_NTSC_NOMINAL_RPM 450U

/* Approximate documented frequencies; NOT a signal processing implementation. */
#define CED_NTSC_BURIED_CHROMA_HZ 1530000U
#define CED_NTSC_MONO_AUDIO_HZ 716000U
#define CED_NTSC_OPTIONAL_AUDIO_B_HZ 905000U
#define CED_NTSC_VIDEO_SYNC_HZ 4300000U
#define CED_NTSC_VIDEO_BLACK_HZ 5000000U
#define CED_NTSC_VIDEO_WHITE_HZ 6300000U
#define CED_NTSC_OUTPUT_CHROMA_HZ 3579545U

/* WHP test-only CED *descriptor*, never a claim of an RCA on-disc bitstream. */
#define CED_DESCRIPTOR_SIZE 24U

typedef enum CedVideoProfile {
    CED_VIDEO_NTSC = 1,
} CedVideoProfile;

typedef enum CedAudioProfile {
    CED_AUDIO_UNKNOWN = 0,
    CED_AUDIO_MONO = 1,
    CED_AUDIO_STEREO = 2,
    CED_AUDIO_INDEPENDENT = 3,
} CedAudioProfile;

typedef enum CedDaxiKnowledge {
    CED_DAXI_UNEXAMINED = 0,
    CED_DAXI_VERIFIED = 1, /* presence, NOT decoded fields */
} CedDaxiKnowledge;

typedef struct CedMedia {
    CedVideoProfile video;
    CedAudioProfile audio;
    CedDaxiKnowledge daxi;
    uint8_t side_count;
    uint32_t side_fields[2];
} CedMedia;

/* Exact 24-byte synthetic descriptor. No Disney assets or analogue samples. */
bool ced_media_decode(const uint8_t *data, size_t len, CedMedia *media);
bool ced_media_encode(const CedMedia *media,
                      uint8_t out[CED_DESCRIPTOR_SIZE]);
bool ced_media_valid(const CedMedia *media);

typedef enum CedTransportProfile {
    CED_TRANSPORT_GENERIC = 0,
    CED_TRANSPORT_RCA_SFT100 = 1,
} CedTransportProfile;

typedef enum CedTransportState {
    CED_EMPTY = 0,
    CED_RETAINED,
    CED_STARTING,
    CED_PLAYING,
    CED_PAUSED,
    CED_VISUAL_SEARCH,
    CED_RAPID_SEEK,
    CED_END_OF_SIDE,
} CedTransportState;

typedef struct CedPlayer {
    CedTransportProfile profile;
    CedTransportState state;
    CedMedia media;
    uint32_t position_fields;
    uint32_t seek_target_fields;
    uint32_t start_remaining_fields;
    uint8_t side;      /* 1 or 2 while retained, 0 when empty */
    uint8_t rf_channel; /* SFT100 external CH3/CH4 switch (not RF synthesis) */
} CedPlayer;

void ced_player_init(CedPlayer *player, CedTransportProfile profile);
bool ced_player_insert(CedPlayer *player, const CedMedia *media, uint8_t side);
bool ced_player_eject(CedPlayer *player);
bool ced_player_play(CedPlayer *player);
bool ced_player_pause(CedPlayer *player);
bool ced_player_stop(CedPlayer *player);
bool ced_player_visual_search(CedPlayer *player);
bool ced_player_rapid_seek(CedPlayer *player, uint32_t target_field);
void ced_player_step_fields(CedPlayer *player, uint64_t elapsed_fields);
bool ced_player_set_rf_channel(CedPlayer *player, uint8_t channel);
bool ced_player_stylus_engaged(const CedPlayer *player);
bool ced_player_video_visible(const CedPlayer *player);
bool ced_player_audio_audible(const CedPlayer *player);
bool ced_player_motor_running(const CedPlayer *player);

#endif /* HW_BLOCK_CED_H */
