#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
meson = (ROOT / "meson.build").read_text()
options = (ROOT / "meson_options.txt").read_text()
audio_meson = (ROOT / "audio/meson.build").read_text()
sdlaudio = (ROOT / "audio/sdlaudio.c").read_text()

required = {
    "independent SDL3 audio option": "option('sdl_audio'" in options,
    "SDL3 audio dependency": "dependency('sdl3'" in meson and "sdl_audio" in meson,
    "audio driver availability uses SDL3": "'sdl': sdl_audio.found()" in meson,
    "audio module uses SDL3 dependency": "['sdl', sdl_audio, files('sdlaudio.c')]" in audio_meson,
    "SDL3 header": "#include <SDL3/SDL.h>" in sdlaudio,
    "SDL3 audio stream ownership": "SDL_AudioStream *" in sdlaudio,
    "SDL3 stream open": "SDL_OpenAudioDeviceStream(" in sdlaudio,
    "SDL3 playback transfer": "SDL_PutAudioStreamData(" in sdlaudio,
    "SDL3 recording transfer": "SDL_GetAudioStreamData(" in sdlaudio,
    "SDL3 stream resume": "SDL_ResumeAudioStreamDevice(" in sdlaudio,
    "SDL3 stream pause": "SDL_PauseAudioStreamDevice(" in sdlaudio,
    "SDL3 stream destroy": "SDL_DestroyAudioStream(" in sdlaudio,
    "SDL3 bool init semantics": "if (!SDL_InitSubSystem(SDL_INIT_AUDIO))" in sdlaudio,
}

forbidden = [
    "SDL_OpenAudioDevice(NULL",
    "SDL_LockAudioDevice(",
    "SDL_UnlockAudioDevice(",
    "SDL_PauseAudioDevice(",
    "SDL_CloseAudioDevice(",
    "req.samples",
    "req.callback",
    "req.userdata",
]

failed = False
for label, ok in required.items():
    if not ok:
        print(f"missing: {label}")
        failed = True

for token in forbidden:
    if token in sdlaudio:
        print(f"stale SDL2 audio API: {token}")
        failed = True

if failed:
    raise SystemExit(1)

print("SDL3 audio split contract: verified")
