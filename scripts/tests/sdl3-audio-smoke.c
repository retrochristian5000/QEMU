#include <SDL3/SDL.h>
#include <stdio.h>
#include <string.h>

static int smoke_stream(SDL_AudioDeviceID device, const char *name, bool playback)
{
    SDL_AudioSpec spec = {
        .format = SDL_AUDIO_F32,
        .channels = 2,
        .freq = 48000,
    };
    SDL_AudioStream *stream;
    float silence[256 * 2] = { 0 };

    stream = SDL_OpenAudioDeviceStream(device, &spec, NULL, NULL);
    if (!stream) {
        fprintf(stderr, "%s open failed: %s\n", name, SDL_GetError());
        return 1;
    }

    if (playback && !SDL_PutAudioStreamData(stream, silence, sizeof(silence))) {
        fprintf(stderr, "%s put failed: %s\n", name, SDL_GetError());
        SDL_DestroyAudioStream(stream);
        return 1;
    }

    if (!SDL_ResumeAudioStreamDevice(stream)) {
        fprintf(stderr, "%s resume failed: %s\n", name, SDL_GetError());
        SDL_DestroyAudioStream(stream);
        return 1;
    }

    SDL_Delay(20);

    if (!playback) {
        int available = SDL_GetAudioStreamAvailable(stream);

        if (available < 0) {
            fprintf(stderr, "%s available failed: %s\n", name, SDL_GetError());
            SDL_DestroyAudioStream(stream);
            return 1;
        }
        if (available > 0) {
            unsigned char buffer[4096];
            int amount = available < (int)sizeof(buffer) ? available : (int)sizeof(buffer);

            if (SDL_GetAudioStreamData(stream, buffer, amount) < 0) {
                fprintf(stderr, "%s get failed: %s\n", name, SDL_GetError());
                SDL_DestroyAudioStream(stream);
                return 1;
            }
        }
    }

    if (!SDL_PauseAudioStreamDevice(stream)) {
        fprintf(stderr, "%s pause failed: %s\n", name, SDL_GetError());
        SDL_DestroyAudioStream(stream);
        return 1;
    }

    SDL_DestroyAudioStream(stream);
    return 0;
}

int main(void)
{
    if (!SDL_Init(SDL_INIT_AUDIO)) {
        fprintf(stderr, "SDL audio init failed: %s\n", SDL_GetError());
        return 1;
    }

    if (smoke_stream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, "playback", true) ||
        smoke_stream(SDL_AUDIO_DEVICE_DEFAULT_RECORDING, "recording", false)) {
        SDL_Quit();
        return 1;
    }

    SDL_Quit();
    puts("SDL3 audio stream smoke: passed");
    return 0;
}
