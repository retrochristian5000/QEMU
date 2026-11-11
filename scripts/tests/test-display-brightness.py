#!/usr/bin/env python3
"""SDL2/SDL3 brightness switch remains presentation-only."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
s2 = (root / "ui/sdl2.c").read_text(encoding="utf-8")
r2 = (root / "ui/sdl2-2d.c").read_text(encoding="utf-8")
s3 = (root / "ui/sdl3-display.c").read_text(encoding="utf-8")
r3 = (root / "ui/sdl3-2d.c").read_text(encoding="utf-8")
h3 = (root / "include/ui/sdl3-2d.h").read_text(encoding="utf-8")
checks = {
    "SDL2 hotkey": "case SDL_SCANCODE_B:" in s2,
    "SDL2 no OpenGL": "!scon->opengl" in s2,
    "SDL2 texture-modulated": "SDL_SetTextureColorMod(scon->texture" in r2,
    "SDL3 neutral start": "display->brightness = QEMU_DISPLAY_BRIGHTNESS_FULL" in r3,
    "SDL3 new texture keeps level": "SDL_SetTextureColorMod(texture, display->brightness" in r3,
    "SDL3 immediate present": "SDL_RenderPresent(display->renderer)" in r3,
    "SDL3 window-specific key": "event->key.windowID == scon->input.window_id" in s3,
    "SDL3 modifier conversion": "SDL_KMOD_CTRL" in s3 and "SDL_KMOD_ALT" in s3,
    "SDL3 state": "uint8_t brightness;" in h3,
}
failed = [name for name, ok in checks.items() if not ok]
if failed:
    raise SystemExit("Brightness bridge regression: " + ", ".join(failed))
print("SDL2/SDL3 display brightness migration contract OK")
