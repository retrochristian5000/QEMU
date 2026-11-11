/*
 * QEMU SDL audio driver
 *
 * Copyright (c) 2004-2005 Vassili Karpov (malc)
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include <SDL3/SDL.h>
#include "qemu/module.h"
#include "qemu/error-report.h"
#include "qapi/error.h"
#include "qemu/audio.h"
#include "qom/object.h"

#ifndef _WIN32
#ifdef __sun__
#define _POSIX_PTHREAD_SEMANTICS 1
#elif defined(__OpenBSD__) || defined(__FreeBSD__) || defined(__DragonFly__)
#include <pthread.h>
#endif
#endif

#include "audio_int.h"

#define TYPE_AUDIO_SDL "audio-sdl"
OBJECT_DECLARE_SIMPLE_TYPE(AudioSdl, AUDIO_SDL)

static AudioBackendClass *audio_sdl_parent_class;

struct AudioSdl {
    AudioMixengBackend parent_obj;
};

typedef struct SDLVoiceOut {
    HWVoiceOut hw;
    bool exit;
    SDL_AudioStream *stream;
} SDLVoiceOut;

typedef struct SDLVoiceIn {
    HWVoiceIn hw;
    bool exit;
    SDL_AudioStream *stream;
} SDLVoiceIn;

static SDL_AudioFormat aud_to_sdlfmt(AudioFormat fmt, bool big_endian)
{
    switch (fmt) {
    case AUDIO_FORMAT_S8:
        return SDL_AUDIO_S8;
    case AUDIO_FORMAT_U8:
        return SDL_AUDIO_U8;
    case AUDIO_FORMAT_S16:
        return big_endian ? SDL_AUDIO_S16BE : SDL_AUDIO_S16LE;
    case AUDIO_FORMAT_U16:
        /* SDL3 removed U16; QEMU negotiates this voice to S16 below. */
        return big_endian ? SDL_AUDIO_S16BE : SDL_AUDIO_S16LE;
    case AUDIO_FORMAT_S32:
        return big_endian ? SDL_AUDIO_S32BE : SDL_AUDIO_S32LE;
    case AUDIO_FORMAT_F32:
        return big_endian ? SDL_AUDIO_F32BE : SDL_AUDIO_F32LE;
    default:
        error_report("sdl: internal logic error: bad audio format %d", fmt);
        return SDL_AUDIO_U8;
    }
}

static struct audsettings sdl_audio_settings(const struct audsettings *as)
{
    struct audsettings actual = *as;

    if (actual.fmt == AUDIO_FORMAT_U16) {
        actual.fmt = AUDIO_FORMAT_S16;
    }
    return actual;
}

static SDL_AudioStream *sdl_open_stream(const SDL_AudioSpec *spec,
                                        bool recording,
                                        SDL_AudioStreamCallback callback,
                                        void *opaque)
{
    SDL_AudioStream *stream;
#ifndef _WIN32
    int err;
    sigset_t new, old;

    err = sigfillset(&new);
    if (err) {
        error_report("sdl: sigfillset failed: %s", strerror(errno));
        return NULL;
    }
    err = pthread_sigmask(SIG_BLOCK, &new, &old);
    if (err) {
        error_report("sdl: pthread_sigmask failed: %s", strerror(err));
        return NULL;
    }
#endif

    stream = SDL_OpenAudioDeviceStream(
        recording ? SDL_AUDIO_DEVICE_DEFAULT_RECORDING
                  : SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,
        spec, callback, opaque);
    if (!stream) {
        error_report("SDL_OpenAudioDeviceStream for %s failed: %s",
                     recording ? "recording" : "playback", SDL_GetError());
    }

#ifndef _WIN32
    err = pthread_sigmask(SIG_SETMASK, &old, NULL);
    if (err) {
        if (stream) {
            SDL_DestroyAudioStream(stream);
        }
        error_report("sdl: pthread_sigmask (restore) failed: %s",
                     strerror(err));
        exit(EXIT_FAILURE);
    }
#endif
    return stream;
}

static void sdl_close_out(SDLVoiceOut *sdl)
{
    if (!sdl->stream) {
        return;
    }

    SDL_LockAudioStream(sdl->stream);
    sdl->exit = true;
    SDL_UnlockAudioStream(sdl->stream);
    SDL_PauseAudioStreamDevice(sdl->stream);
    SDL_DestroyAudioStream(sdl->stream);
    sdl->stream = NULL;
}

static void SDLCALL sdl_callback_out(void *opaque, SDL_AudioStream *stream,
                                     int additional_amount,
                                     int total_amount)
{
    SDLVoiceOut *sdl = opaque;
    HWVoiceOut *hw = &sdl->hw;

    (void)total_amount;
    if (sdl->exit || additional_amount <= 0) {
        return;
    }

    while (hw->pending_emul && additional_amount > 0) {
        size_t start = audio_ring_posb(hw->pos_emul, hw->pending_emul,
                                       hw->size_emul);
        size_t write_len;

        assert(start < hw->size_emul);
        write_len = MIN(hw->pending_emul, hw->size_emul - start);
        write_len = MIN(write_len, (size_t)additional_amount);

        if (!SDL_PutAudioStreamData(stream, hw->buf_emul + start,
                                    (int)write_len)) {
            error_report("SDL_PutAudioStreamData failed: %s", SDL_GetError());
            return;
        }
        hw->pending_emul -= write_len;
        additional_amount -= write_len;
    }
}

static void sdl_close_in(SDLVoiceIn *sdl)
{
    if (!sdl->stream) {
        return;
    }

    SDL_LockAudioStream(sdl->stream);
    sdl->exit = true;
    SDL_UnlockAudioStream(sdl->stream);
    SDL_PauseAudioStreamDevice(sdl->stream);
    SDL_DestroyAudioStream(sdl->stream);
    sdl->stream = NULL;
}

static void SDLCALL sdl_callback_in(void *opaque, SDL_AudioStream *stream,
                                    int additional_amount,
                                    int total_amount)
{
    SDLVoiceIn *sdl = opaque;
    HWVoiceIn *hw = &sdl->hw;
    int available;

    (void)additional_amount;
    (void)total_amount;
    if (sdl->exit) {
        return;
    }

    available = SDL_GetAudioStreamAvailable(stream);
    if (available < 0) {
        error_report("SDL_GetAudioStreamAvailable failed: %s", SDL_GetError());
        return;
    }

    while (available > 0 && hw->pending_emul < hw->size_emul) {
        size_t read_len = MIN((size_t)available,
                              hw->size_emul - hw->pending_emul);
        int got;

        read_len = MIN(read_len, hw->size_emul - hw->pos_emul);
        got = SDL_GetAudioStreamData(stream, hw->buf_emul + hw->pos_emul,
                                     (int)read_len);
        if (got < 0) {
            error_report("SDL_GetAudioStreamData failed: %s", SDL_GetError());
            return;
        }
        if (got == 0) {
            break;
        }

        hw->pending_emul += got;
        hw->pos_emul = (hw->pos_emul + got) % hw->size_emul;
        available -= got;
    }
}

#define SDL_WRAPPER_FUNC(name, ret_type, args_decl, args, dir) \
    static ret_type glue(sdl_, name)args_decl                  \
    {                                                          \
        ret_type ret;                                          \
        glue(SDLVoice, dir) *sdl = (glue(SDLVoice, dir) *)hw;  \
                                                               \
        SDL_LockAudioStream(sdl->stream);                      \
        ret = glue(audio_generic_, name)args;                  \
        SDL_UnlockAudioStream(sdl->stream);                    \
                                                               \
        return ret;                                            \
    }

#define SDL_WRAPPER_VOID_FUNC(name, args_decl, args, dir)      \
    static void glue(sdl_, name)args_decl                      \
    {                                                          \
        glue(SDLVoice, dir) *sdl = (glue(SDLVoice, dir) *)hw;  \
                                                               \
        SDL_LockAudioStream(sdl->stream);                      \
        glue(audio_generic_, name)args;                        \
        SDL_UnlockAudioStream(sdl->stream);                    \
    }

SDL_WRAPPER_FUNC(buffer_get_free, size_t, (HWVoiceOut *hw), (hw), Out)
SDL_WRAPPER_FUNC(get_buffer_out, void *, (HWVoiceOut *hw, size_t *size),
                 (hw, size), Out)
SDL_WRAPPER_FUNC(put_buffer_out, size_t,
                 (HWVoiceOut *hw, void *buf, size_t size),
                 (hw, buf, size), Out)
SDL_WRAPPER_FUNC(write, size_t,
                 (HWVoiceOut *hw, void *buf, size_t size),
                 (hw, buf, size), Out)
SDL_WRAPPER_FUNC(read, size_t, (HWVoiceIn *hw, void *buf, size_t size),
                 (hw, buf, size), In)
SDL_WRAPPER_FUNC(get_buffer_in, void *, (HWVoiceIn *hw, size_t *size),
                 (hw, size), In)
SDL_WRAPPER_VOID_FUNC(put_buffer_in,
                      (HWVoiceIn *hw, void *buf, size_t size),
                      (hw, buf, size), In)
#undef SDL_WRAPPER_FUNC
#undef SDL_WRAPPER_VOID_FUNC

static void sdl_fini_out(HWVoiceOut *hw)
{
    sdl_close_out((SDLVoiceOut *)hw);
}

static int sdl_init_out(HWVoiceOut *hw, struct audsettings *as)
{
    SDLVoiceOut *sdl = (SDLVoiceOut *)hw;
    AudiodevSdlPerDirectionOptions *spdo = hw->s->dev->u.sdl.out;
    struct audsettings actual = sdl_audio_settings(as);
    SDL_AudioSpec spec = {
        .format = aud_to_sdlfmt(actual.fmt, actual.big_endian),
        .channels = actual.nchannels,
        .freq = actual.freq,
    };
    int frames;

    audio_pcm_init_info(&hw->info, &actual);
    frames = audio_buffer_frames(
        qapi_AudiodevSdlPerDirectionOptions_base(spdo), &actual, 11610);
    hw->samples = (spdo->has_buffer_count ? spdo->buffer_count : 4) * frames;

    sdl->exit = false;
    sdl->stream = sdl_open_stream(&spec, false, sdl_callback_out, sdl);
    if (!sdl->stream) {
        return -1;
    }

    return 0;
}

static void sdl_enable_out(HWVoiceOut *hw, bool enable)
{
    SDLVoiceOut *sdl = (SDLVoiceOut *)hw;
    bool ok = enable ? SDL_ResumeAudioStreamDevice(sdl->stream)
                     : SDL_PauseAudioStreamDevice(sdl->stream);

    if (!ok) {
        error_report("SDL %s playback stream failed: %s",
                     enable ? "resume" : "pause", SDL_GetError());
    }
}

static void sdl_fini_in(HWVoiceIn *hw)
{
    sdl_close_in((SDLVoiceIn *)hw);
}

static int sdl_init_in(HWVoiceIn *hw, audsettings *as)
{
    SDLVoiceIn *sdl = (SDLVoiceIn *)hw;
    AudiodevSdlPerDirectionOptions *spdo = hw->s->dev->u.sdl.in;
    struct audsettings actual = sdl_audio_settings(as);
    SDL_AudioSpec spec = {
        .format = aud_to_sdlfmt(actual.fmt, actual.big_endian),
        .channels = actual.nchannels,
        .freq = actual.freq,
    };
    int frames;

    audio_pcm_init_info(&hw->info, &actual);
    frames = audio_buffer_frames(
        qapi_AudiodevSdlPerDirectionOptions_base(spdo), &actual, 11610);
    hw->samples = (spdo->has_buffer_count ? spdo->buffer_count : 4) * frames;
    hw->size_emul = hw->samples * hw->info.bytes_per_frame;
    hw->buf_emul = g_malloc(hw->size_emul);
    hw->pos_emul = hw->pending_emul = 0;

    sdl->exit = false;
    sdl->stream = sdl_open_stream(&spec, true, sdl_callback_in, sdl);
    if (!sdl->stream) {
        g_free(hw->buf_emul);
        hw->buf_emul = NULL;
        return -1;
    }

    return 0;
}

static void sdl_enable_in(HWVoiceIn *hw, bool enable)
{
    SDLVoiceIn *sdl = (SDLVoiceIn *)hw;
    bool ok = enable ? SDL_ResumeAudioStreamDevice(sdl->stream)
                     : SDL_PauseAudioStreamDevice(sdl->stream);

    if (!ok) {
        error_report("SDL %s recording stream failed: %s",
                     enable ? "resume" : "pause", SDL_GetError());
    }
}

static bool audio_sdl_realize(AudioBackend *abe, Audiodev *dev, Error **errp)
{
    if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
        error_setg(errp, "SDL failed to initialize audio subsystem: %s",
                   SDL_GetError());
        qapi_free_Audiodev(dev);
        return false;
    }

    return audio_sdl_parent_class->realize(abe, dev, errp);
}

static void audio_sdl_finalize(Object *obj)
{
    SDL_QuitSubSystem(SDL_INIT_AUDIO);
}

static void audio_sdl_class_init(ObjectClass *klass, const void *data)
{
    AudioBackendClass *b = AUDIO_BACKEND_CLASS(klass);
    AudioMixengBackendClass *k = AUDIO_MIXENG_BACKEND_CLASS(klass);

    audio_sdl_parent_class = AUDIO_BACKEND_CLASS(object_class_get_parent(klass));

    b->realize = audio_sdl_realize;
    k->max_voices_out = INT_MAX;
    k->max_voices_in = INT_MAX;
    k->voice_size_out = sizeof(SDLVoiceOut);
    k->voice_size_in = sizeof(SDLVoiceIn);

    k->init_out = sdl_init_out;
    k->fini_out = sdl_fini_out;
    k->write = sdl_write;
    k->buffer_get_free = sdl_buffer_get_free;
    k->get_buffer_out = sdl_get_buffer_out;
    k->put_buffer_out = sdl_put_buffer_out;
    k->enable_out = sdl_enable_out;

    k->init_in = sdl_init_in;
    k->fini_in = sdl_fini_in;
    k->read = sdl_read;
    k->get_buffer_in = sdl_get_buffer_in;
    k->put_buffer_in = sdl_put_buffer_in;
    k->enable_in = sdl_enable_in;
}

static const TypeInfo audio_types[] = {
    {
        .name = TYPE_AUDIO_SDL,
        .parent = TYPE_AUDIO_MIXENG_BACKEND,
        .instance_size = sizeof(AudioSdl),
        .class_init = audio_sdl_class_init,
        .instance_finalize = audio_sdl_finalize,
    },
};

DEFINE_TYPES(audio_types)
module_obj(TYPE_AUDIO_SDL);
