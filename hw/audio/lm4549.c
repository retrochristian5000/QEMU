/*
 * LM4549 Audio Codec Interface
 *
 * Copyright (c) 2011
 * Written by Mathieu Sonet - www.elasticsheep.com
 *
 * This code is licensed under the GPL.
 *
 * *****************************************************************
 *
 * This driver emulates the LM4549 codec.
 *
 * It supports only one playback voice and no record voice.
 */

#include "qemu/osdep.h"
#include "hw/audio/ac97-codec.h"
#include "hw/core/hw-error.h"
#include "qemu/log.h"
#include "qemu/audio.h"
#include "lm4549.h"
#include "ac97.h"
#include "migration/vmstate.h"

#if 0
#define LM4549_DEBUG  1
#endif

#if 0
#define LM4549_DUMP_DAC_INPUT 1
#endif

#ifdef LM4549_DEBUG
#define DPRINTF(fmt, ...) \
do { printf("lm4549: " fmt , ## __VA_ARGS__); } while (0)
#else
#define DPRINTF(fmt, ...) do {} while (0)
#endif

#if defined(LM4549_DUMP_DAC_INPUT)
static FILE *fp_dac_input;
#endif

static void lm4549_audio_out_callback(void *opaque, int free);

static AC97Codec lm4549_codec(lm4549_state *s)
{
    AC97Codec codec;

    /*
     * Preserve the historical sparse regfile layout: the AC'97 byte offset
     * is the uint16_t array index.  vmstate_lm4549_state migrates this exact
     * array, so repacking it would break old snapshots.
     */
    ac97_codec_init_u16_offsets(&codec, s->regfile,
                                &ac97_codec_profile_lm4549, 0);
    return codec;
}

static uint16_t lm4549_codec_read(lm4549_state *s, unsigned reg)
{
    AC97Codec codec = lm4549_codec(s);

    return ac97_codec_read(&codec, reg);
}

static void lm4549_open_voice(lm4549_state *s, unsigned freq)
{
    struct audsettings as = {
        .freq = freq,
        .nchannels = 2,
        .fmt = AUDIO_FORMAT_S16,
        .big_endian = false,
    };

    s->voice = audio_be_open_out(
        s->audio_be,
        s->voice,
        "lm4549.out",
        s,
        lm4549_audio_out_callback,
        &as
    );
}

static void lm4549_reset(lm4549_state *s)
{
    AC97Codec codec = lm4549_codec(s);

    ac97_codec_reset(&codec);
}

static void lm4549_audio_transfer(lm4549_state *s)
{
    uint32_t written_bytes, written_samples;
    uint32_t i;

    /* Activate the voice */
    audio_be_set_active_out(s->audio_be, s->voice, 1);
    s->voice_is_active = 1;

    /* Try to write the buffer content */
    written_bytes = audio_be_write(s->audio_be, s->voice, s->buffer,
                                   s->buffer_level * sizeof(uint16_t));
    written_samples = written_bytes >> 1;

#if defined(LM4549_DUMP_DAC_INPUT)
    fwrite(s->buffer, sizeof(uint8_t), written_bytes, fp_dac_input);
#endif

    s->buffer_level -= written_samples;

    if (s->buffer_level > 0) {
        /* Move the data back to the start of the buffer */
        for (i = 0; i < s->buffer_level; i++) {
            s->buffer[i] = s->buffer[i + written_samples];
        }
    }
}

static void lm4549_audio_out_callback(void *opaque, int free)
{
    lm4549_state *s = (lm4549_state *)opaque;
    static uint32_t prev_buffer_level;

#ifdef LM4549_DEBUG
    int size = audio_be_get_buffer_size_out(s->audio_be, s->voice);
    DPRINTF("audio_out_callback size = %i free = %i\n", size, free);
#endif

    /* Detect that no data are consumed
       => disable the voice */
    if (s->buffer_level == prev_buffer_level) {
        audio_be_set_active_out(s->audio_be, s->voice, 0);
        s->voice_is_active = 0;
    }
    prev_buffer_level = s->buffer_level;

    /* Check if a buffer transfer is pending */
    if (s->buffer_level == LM4549_BUFFER_SIZE) {
        lm4549_audio_transfer(s);

        /* Request more data */
        if (s->data_req_cb != NULL) {
            (s->data_req_cb)(s->opaque);
        }
    }
}

uint32_t lm4549_read(lm4549_state *s, hwaddr offset)
{
    uint32_t value;

    assert(offset < 128);
    value = lm4549_codec_read(s, offset);

    DPRINTF("read [0x%02x] = 0x%04x\n", (unsigned)offset, value);

    return value;
}

void lm4549_write(lm4549_state *s, hwaddr offset, uint32_t value)
{
    AC97Codec codec = lm4549_codec(s);
    uint32_t events;

    assert(offset < 128);
    DPRINTF("write [0x%02x] = 0x%04x\n", (unsigned)offset, value);

    events = ac97_codec_write(&codec, offset, value);

    if (events & AC97_CODEC_EVENT_INVALID_RATE) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "%s: DAC sample rate %d Hz is invalid, ignoring it\n",
                      __func__, value);
        return;
    }

    if (events & AC97_CODEC_EVENT_FRONT_DAC_RATE) {
        DPRINTF("DAC rate change = %i\n", value);
        lm4549_open_voice(s, lm4549_codec_read(s,
                                                AC97_PCM_Front_DAC_Rate));
    }
}

uint32_t lm4549_write_samples(lm4549_state *s, uint32_t left, uint32_t right)
{
    /* The left and right samples are in 20-bit resolution.
       The LM4549 has 18-bit resolution and only uses the bits [19:2].
       This model supports 16-bit playback.
    */

    if (s->buffer_level > LM4549_BUFFER_SIZE - 2) {
        DPRINTF("write_sample Buffer full\n");
        return 0;
    }

    /* Store 16-bit samples in the buffer */
    s->buffer[s->buffer_level++] = (left >> 4);
    s->buffer[s->buffer_level++] = (right >> 4);

    if (s->buffer_level == LM4549_BUFFER_SIZE) {
        /* Trigger the transfer of the buffer to the audio host */
        lm4549_audio_transfer(s);
    }

    return 1;
}

static int lm4549_post_load(void *opaque, int version_id)
{
    lm4549_state *s = (lm4549_state *)opaque;
    uint32_t freq = lm4549_codec_read(s, AC97_PCM_Front_DAC_Rate);

    DPRINTF("post_load freq = %i\n", freq);
    DPRINTF("post_load voice_is_active = %i\n", s->voice_is_active);

    /* Re-open a voice with the current sample rate. */
    lm4549_open_voice(s, freq);

    /* Request data */
    if (s->voice_is_active == 1) {
        lm4549_audio_out_callback(s,
            audio_be_get_buffer_size_out(s->audio_be, s->voice));
    }

    return 0;
}

void lm4549_init(lm4549_state *s, lm4549_callback data_req_cb, void *opaque,
                 Error **errp)
{
    /* Register an audio card */
    if (!audio_be_check(&s->audio_be, errp)) {
        return;
    }

    /* Store the callback and opaque pointer */
    s->data_req_cb = data_req_cb;
    s->opaque = opaque;

    /* Init the registers */
    lm4549_reset(s);

    /* Open a default voice */
    lm4549_open_voice(s, 48000);

    audio_be_set_volume_out_lr(s->audio_be, s->voice, 0, 255, 255);

    s->voice_is_active = 0;

    /* Reset the input buffer */
    memset(s->buffer, 0x00, sizeof(s->buffer));
    s->buffer_level = 0;

#if defined(LM4549_DUMP_DAC_INPUT)
    fp_dac_input = fopen("lm4549_dac_input.pcm", "wb");
    if (!fp_dac_input) {
        hw_error("Unable to open lm4549_dac_input.pcm for writing\n");
    }
#endif
}

const VMStateDescription vmstate_lm4549_state = {
    .name = "lm4549_state",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = lm4549_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(voice_is_active, lm4549_state),
        VMSTATE_UINT16_ARRAY(regfile, lm4549_state, 128),
        VMSTATE_UINT16_ARRAY(buffer, lm4549_state, LM4549_BUFFER_SIZE),
        VMSTATE_UINT32(buffer_level, lm4549_state),
        VMSTATE_END_OF_LIST()
    }
};
