# SDL3 Audio Backend Split Design

Date: 2026-09-16
Repository: retrochristian5000/QEMU

## Goal

Decouple QEMU's SDL audio backend from the SDL2 display frontend, then port only the audio backend to SDL3. SDL audio must remain usable with non-SDL displays such as Cocoa, GTK, VNC, or headless configurations.

This work also gives us a clean diagnostic boundary for the observed macOS `Abort trap: 6`: after the split, SDL3 audio can be exercised without involving the SDL2 video/input frontend.

## Current Coupling

The top-level Meson build currently defines `sdl` from `dependency('sdl2')`. The same dependency is used by both the SDL display frontend and `audio/sdlaudio.c`, so enabling SDL audio implicitly couples it to SDL2 even when a different display frontend is selected.

The existing audio backend is SDL2-specific. It uses `SDL_AudioDeviceID`, `SDL_OpenAudioDevice`, device locks, `SDL_PauseAudioDevice`, callback fields in `SDL_AudioSpec`, and SDL2-style subsystem lifetime rules.

## Architecture

### Display path

Leave the existing SDL display frontend unchanged in this phase:

- `sdl` continues to mean the SDL2 display dependency.
- `ui/sdl2.c`, `ui/sdl2-2d.c`, `ui/sdl2-gl.c`, `ui/sdl2-input.c`, and `include/ui/sdl2.h` remain SDL2 code.
- `SDL2_image` remains tied to the SDL2 display frontend.

### Audio path

Add a separate SDL3 dependency for audio, named independently from the display dependency (for example `sdl_audio`). The SDL audio module in `audio/meson.build` must depend on this SDL3 object rather than the SDL2 display object.

The SDL audio backend must be selectable and buildable even when `-Dsdl=disabled` disables the SDL display frontend.

### Backend model

Port `audio/sdlaudio.c` to SDL3's stream API:

- Replace `SDL_AudioDeviceID` ownership with `SDL_AudioStream *` ownership per voice.
- Playback uses `SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, ...)`.
- Recording uses `SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_RECORDING, ...)`.
- Playback moves QEMU PCM data into SDL with `SDL_PutAudioStreamData()`.
- Recording drains SDL data with `SDL_GetAudioStreamData()` into QEMU's existing input ring.
- Voice enable/disable uses SDL3 stream-device resume/pause operations instead of SDL2 `SDL_PauseAudioDevice(..., bool)`.
- Voice teardown destroys the stream and relies on SDL3 stream/device ownership semantics.
- Remove SDL2 device-lock calls and SDL2 callback fields from `SDL_AudioSpec`.
- Convert audio format constants to SDL3 `SDL_AUDIO_*` constants.

QEMU's existing audio ring/accounting remains authoritative. SDL3 buffering must not replace or redefine the QEMU audio core model.

## Configuration

The Meson configuration must expose audio and display availability independently:

- `CONFIG_SDL` continues to describe the SDL2 display frontend.
- `CONFIG_AUDIO_SDL` is derived from the SDL3 audio dependency.
- The audio-driver availability table uses the SDL3 audio dependency, not the SDL2 display dependency.
- Build summaries should make the distinction visible so a configuration can report SDL display disabled while SDL audio remains enabled.

No SDL3 display migration is included in this work.

## Error Handling and Lifetime

SDL3 subsystem initialization must follow SDL3 boolean success semantics rather than SDL2 integer-return assumptions. Initialization errors should include `SDL_GetError()` in the QEMU error path.

Audio subsystem lifetime remains owned by the audio backend. The backend must initialize the SDL audio subsystem before opening streams and release it when the backend is finalized, without requiring SDL video initialization.

A failure to open one playback or recording stream must fail that voice cleanly without aborting QEMU.

## Testing

The implementation must be developed test-first where practical.

Required regression coverage:

1. Configure/build with SDL display disabled while SDL3 audio is enabled; the SDL audio module must still build.
2. Configure/build with SDL2 display enabled and SDL3 audio enabled; both dependencies must coexist without symbol/header confusion.
3. Compile `audio/sdlaudio.c` against SDL3 with warnings treated as errors.
4. Add a macOS runtime smoke test that initializes SDL3 audio, opens/resumes/destroys a stream, and exits normally; `SIGABRT`/`Abort trap: 6` is a failure.
5. Exercise both playback and recording backend initialization paths.
6. Preserve existing non-SDL audio backends and SDL2 display behavior.

## Non-Goals

This phase does not:

- port the SDL display frontend to SDL3;
- introduce `sdl2-compat` as a required layer;
- rewrite QEMU's audio core;
- change Cocoa, GTK, VNC, or headless display behavior;
- remove SDL2 support from the repository.

## Acceptance Criteria

The split is complete when:

- SDL3 audio can be enabled with SDL2 display disabled;
- the SDL audio backend uses no removed SDL2 audio-device APIs;
- playback and recording initialize and shut down without aborting on macOS;
- existing SDL2 display code continues to compile against SDL2;
- Meson configuration and generated `CONFIG_AUDIO_SDL` reflect SDL3 audio availability independently of `CONFIG_SDL`.
