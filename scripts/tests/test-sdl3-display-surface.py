#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source_path = ROOT / "ui/sdl3-display.c"
header_path = ROOT / "include/ui/sdl3-display.h"
ui_meson = (ROOT / "ui/meson.build").read_text()

required_files = {
    "SDL3 display bridge source": source_path,
    "SDL3 display bridge header": header_path,
}
missing = [name for name, path in required_files.items() if not path.exists()]
if missing:
    raise SystemExit("missing: " + ", ".join(missing))

source = source_path.read_text()
header = header_path.read_text()

formats = {
    "PIXMAN_x1r5g5b5": "SDL_PIXELFORMAT_ARGB1555",
    "PIXMAN_r5g6b5": "SDL_PIXELFORMAT_RGB565",
    "PIXMAN_a8r8g8b8": "SDL_PIXELFORMAT_ARGB8888",
    "PIXMAN_x8r8g8b8": "SDL_PIXELFORMAT_ARGB8888",
    "PIXMAN_a8b8g8r8": "SDL_PIXELFORMAT_ABGR8888",
    "PIXMAN_x8b8g8r8": "SDL_PIXELFORMAT_ABGR8888",
    "PIXMAN_r8g8b8a8": "SDL_PIXELFORMAT_RGBA8888",
    "PIXMAN_r8g8b8x8": "SDL_PIXELFORMAT_RGBA8888",
    "PIXMAN_b8g8r8x8": "SDL_PIXELFORMAT_BGRX8888",
    "PIXMAN_b8g8r8a8": "SDL_PIXELFORMAT_BGRA8888",
}

required = {
    "QEMU console integration": '#include "ui/console.h"' in header,
    "SDL3 2D integration": '#include "ui/sdl3-2d.h"' in header,
    "display listener ops": "DisplayChangeListenerOps" in source and '.dpy_name = "sdl3-2d"' in source,
    "surface update callback": ".dpy_gfx_update" in source,
    "surface switch callback": ".dpy_gfx_switch" in source,
    "format callback": ".dpy_gfx_check_format" in source,
    "refresh callback": ".dpy_refresh" in source and "qemu_console_hw_update" in source,
    "stride-aware x offset": "surface_bytes_per_pixel(surf) * x" in source,
    "stride-aware y offset": "surface_stride(surf) * y" in source,
    "surface stride upload": "surface_stride(surf)" in source and "qemu_sdl3_2d_update" in source,
    "surface resize": "qemu_sdl3_window_resize" in source,
    "texture reconfigure": "qemu_sdl3_2d_configure" in source,
    "bridge built with SDL3 core": "'sdl3-display.c'" in ui_meson,
    "pixman build dependency": "pixman" in ui_meson,
}

for pixman_name, sdl_name in formats.items():
    required[f"format {pixman_name}"] = pixman_name in source and sdl_name in source

forbidden = {
    "input/event migration deferred": "SDL_PollEvent" in source or "SDL_Event" in source,
    "OpenGL migration deferred": "SDL_GL_" in source,
    "SDL2 bridge dependency": "sdl2" in source.lower() or "ui/sdl2.h" in source,
}

failures = [name for name, ok in required.items() if not ok]
failures += [f"forbidden: {name}" for name, present in forbidden.items() if present]
if failures:
    raise SystemExit("SDL3 DisplaySurface contract failures: " + ", ".join(failures))

print("SDL3 DisplaySurface contract OK")
