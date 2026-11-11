#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

meson = (ROOT / "meson.build").read_text()
ui_meson = (ROOT / "ui/meson.build").read_text()
header_path = ROOT / "include/ui/sdl3-core.h"
source_path = ROOT / "ui/sdl3-core.c"

required = {
    "SDL3 video dependency": "sdl3_video = dependency('sdl3'" in meson,
    "SDL3 minimum version": "version: '>=3.2.0'" in meson,
    "SDL3 core build target": "sdl3-core.c" in ui_meson and "sdl3_video" in ui_meson,
    "SDL3 core header": header_path.exists(),
    "SDL3 core source": source_path.exists(),
}

if header_path.exists() and source_path.exists():
    header = header_path.read_text()
    source = source_path.read_text()
    required.update({
        "native SDL3 header": "#include <SDL3/SDL.h>" in header,
        "main-thread guard": "SDL_IsMainThread()" in source,
        "SDL3 bool init semantics": "SDL_InitSubSystem(SDL_INIT_VIDEO)" in source,
        "four-argument SDL3 window creation": "SDL_CreateWindow(title, width, height, flags)" in source,
        "SDL3 resize semantics": "SDL_SetWindowSize(window, width, height)" in source,
        "SDL3 fullscreen semantics": "SDL_SetWindowFullscreen(window, fullscreen)" in source,
        "SDL3 window destruction": "SDL_DestroyWindow(window)" in source,
    })

    forbidden = {
        "renderer code deferred": "SDL_CreateRenderer",
        "event/input code deferred": "SDL_Event",
        "OpenGL code deferred": "SDL_GL_",
    }
    for label, token in forbidden.items():
        required[label] = token not in source

failed = [name for name, ok in required.items() if not ok]
if failed:
    raise SystemExit("SDL3 video core contract failed: " + ", ".join(failed))

print("SDL3 video core contract: ok")
