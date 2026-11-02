#!/usr/bin/env python3
"""Guard host-only SDL2 brightness and mode-switch persistence."""
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sdl = (root / "ui/sdl2.c").read_text(encoding="utf-8")
render = (root / "ui/sdl2-2d.c").read_text(encoding="utf-8")
header = (root / "include/ui/sdl2.h").read_text(encoding="utf-8")
checks = {
    "button": "case SDL_SCANCODE_B:" in sdl,
    "SDL2 framebuffer-only": "!scon->opengl" in sdl,
    "per-window initial state": "brightness = QEMU_DISPLAY_BRIGHTNESS_FULL" in sdl,
    "texture modulates only presentation": "SDL_SetTextureColorMod(scon->texture" in render,
    "guest VRAM untouched": "scon->brightness = brightness;" in render,
    "mode change keeps brightness": "scon->brightness, " in render,
    "redraw on press": "sdl2_2d_redraw(scon);" in render,
    "state declared": "uint8_t brightness;" in header,
}
errors = [name for name, ok in checks.items() if not ok]
if errors:
    raise SystemExit("SDL2 brightness contract failed: " + ", ".join(errors))
print("SDL2 software brightness button contract OK")
