/*
 * Host-side SoundFont synthesis for a Wave Blaster-compatible connector.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * QEMU owns MIDI frame timing and the final audio backend. No FluidSynth
 * audio driver or MIDI input thread is opened. Calls follow the existing
 * QEMU audio callback and virtual timer serialization under the BQL.
 */
#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/log.h"
#include "waveblaster-synth.h"

#ifdef CONFIG_FSYNTH
#include <fluidsynth.h>

#define WAVE_RATE 44100
#define WAVE_FRAMES 512
#define WAVE_FRAME_BYTES (2 * sizeof(int16_t))

struct WaveBlasterSynth {
    AudioBackend *be;
    SWVoiceOut *voice;
    fluid_settings_t *settings;
    fluid_synth_t *synth;
    fluid_midi_stream_t *stream;
    const uint8_t *mixer_regs;
    int16_t pcm[WAVE_FRAMES * 2];
    size_t offset;
    size_t pending;
    bool input_error_logged;
    bool render_error_logged;
};

/*
 * First-pass linear gain for the CT1745 master and MIDI volume controls.
 * This is not the physical logarithmic attenuation curve or analog mixer.
 */
static void waveblaster_apply_volume(WaveBlasterSynth *s, size_t frames)
{
    unsigned int left = (s->mixer_regs[0x30] >> 3) *
                        (s->mixer_regs[0x34] >> 3);
    unsigned int right = (s->mixer_regs[0x31] >> 3) *
                         (s->mixer_regs[0x35] >> 3);

    for (size_t i = 0; i < frames; i++) {
        s->pcm[2 * i] = (int32_t)s->pcm[2 * i] * (int)left / (31 * 31);
        s->pcm[2 * i + 1] =
            (int32_t)s->pcm[2 * i + 1] * (int)right / (31 * 31);
    }
}

static void waveblaster_audio(void *opaque, int avail)
{
    WaveBlasterSynth *s = opaque;

    while (avail >= (int)WAVE_FRAME_BYTES) {
        size_t bytes;
        size_t written;

        if (!s->pending) {
            size_t frames = MIN((size_t)avail / WAVE_FRAME_BYTES, WAVE_FRAMES);

            if (fluid_synth_write_s16(s->synth, frames, s->pcm, 0, 2,
                                      s->pcm, 1, 2) != FLUID_OK) {
                memset(s->pcm, 0, frames * WAVE_FRAME_BYTES);
                if (!s->render_error_logged) {
                    qemu_log_mask(LOG_GUEST_ERROR,
                                  "Wave Blaster: PCM rendering failed\n");
                    s->render_error_logged = true;
                }
            }
            waveblaster_apply_volume(s, frames);
            s->offset = 0;
            s->pending = frames * WAVE_FRAME_BYTES;
        }

        bytes = MIN(s->pending, (size_t)avail);
        bytes -= bytes % WAVE_FRAME_BYTES;
        if (!bytes) {
            break;
        }
        written = audio_be_write(s->be, s->voice,
                                 (uint8_t *)s->pcm + s->offset, bytes);
        if (!written) {
            break;
        }
        assert(written <= bytes && written % WAVE_FRAME_BYTES == 0);
        s->pending -= written;
        s->offset += written;
        avail -= (int)written;
    }
}

void waveblaster_synth_free(WaveBlasterSynth *s)
{
    if (!s) {
        return;
    }
    if (s->voice) {
        audio_be_set_active_out(s->be, s->voice, false);
        audio_be_close_out(s->be, s->voice);
    }
    if (s->stream) {
        delete_fluid_midi_stream(s->stream);
    }
    if (s->synth) {
        delete_fluid_synth(s->synth);
    }
    if (s->settings) {
        delete_fluid_settings(s->settings);
    }
    g_free(s);
}

WaveBlasterSynth *waveblaster_synth_new(AudioBackend *be, const char *soundfont,
                                      const uint8_t *mixer_regs, Error **errp)
{
    const struct audsettings as = {
        .freq = WAVE_RATE,
        .nchannels = 2,
        .fmt = AUDIO_FORMAT_S16,
        .big_endian = HOST_BIG_ENDIAN,
    };
    WaveBlasterSynth *s = g_new0(WaveBlasterSynth, 1);

    s->be = be;
    s->mixer_regs = mixer_regs;
    s->settings = new_fluid_settings();
    if (!s->settings ||
        fluid_settings_setnum(s->settings, "synth.sample-rate", WAVE_RATE)
        != FLUID_OK ||
        fluid_settings_setint(s->settings, "synth.cpu-cores", 1) != FLUID_OK ||
        fluid_settings_setint(s->settings, "synth.polyphony", 64) != FLUID_OK) {
        error_setg(errp, "Wave Blaster: unable to configure Fsynth");
        goto fail;
    }
    s->synth = new_fluid_synth(s->settings);
    if (!s->synth) {
        error_setg(errp, "Wave Blaster: unable to initialize Fsynth");
        goto fail;
    }
    if (fluid_synth_sfload(s->synth, soundfont, 1) == FLUID_FAILED) {
        error_setg(errp, "Wave Blaster: unable to load SoundFont '%s'", soundfont);
        goto fail;
    }
    s->stream = new_fluid_midi_stream(s->synth);
    if (!s->stream) {
        error_setg(errp, "Wave Blaster: unable to initialize MIDI stream");
        goto fail;
    }
    s->voice = audio_be_open_out(be, NULL, "waveblaster", s,
                                 waveblaster_audio, &as);
    if (!s->voice) {
        error_setg(errp, "Wave Blaster: unable to open QEMU stereo voice");
        goto fail;
    }
    audio_be_set_active_out(be, s->voice, true);
    return s;

fail:
    waveblaster_synth_free(s);
    return NULL;
}

void waveblaster_synth_reset(WaveBlasterSynth *s)
{
    if (s) {
        fluid_midi_stream_reset(s->stream);
        fluid_synth_system_reset(s->synth);
        s->offset = 0;
        s->pending = 0;
        s->input_error_logged = false;
        s->render_error_logged = false;
    }
}

void waveblaster_synth_write(WaveBlasterSynth *s, uint8_t byte)
{
    if (s && fluid_midi_stream_write(s->stream, byte) != FLUID_OK &&
        !s->input_error_logged) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "Wave Blaster: Fsynth rejected a MIDI message\n");
        s->input_error_logged = true;
    }
}

#else

WaveBlasterSynth *waveblaster_synth_new(AudioBackend *be, const char *soundfont,
                                      const uint8_t *mixer_regs, Error **errp)
{
    error_setg(errp, "Wave Blaster: Fsynth support is not built in "
               "(configure with --enable-fsynth)");
    return NULL;
}

void waveblaster_synth_free(WaveBlasterSynth *s)
{
}

void waveblaster_synth_reset(WaveBlasterSynth *s)
{
}

void waveblaster_synth_write(WaveBlasterSynth *s, uint8_t byte)
{
}

#endif
