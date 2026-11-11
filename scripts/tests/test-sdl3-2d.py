#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source_path = ROOT / "ui/sdl3-2d.c"
header_path = ROOT / "include/ui/sdl3-2d.h"
ui_meson = (ROOT / "ui/meson.build").read_text()

required_files = {
    "SDL3 2D source": source_path,
    "SDL3 2D header": header_path,
}
missing = [name for name, path in required_files.items() if not path.exists()]
if missing:
    raise SystemExit("missing: " + ", ".join(missing))

source = source_path.read_text()
header = header_path.read_text()

required = {
    "SDL3 header": "#include <SDL3/SDL.h>" in header,
    "renderer creation": "SDL_CreateRenderer" in source,
    "streaming texture": "SDL_TEXTUREACCESS_STREAMING" in source,
    "texture upload": "SDL_UpdateTexture" in source,
    "SDL3 logical presentation": "SDL_SetRenderLogicalPresentation" in source,
    "SDL3 texture rendering": "SDL_RenderTexture" in source,
    "frame presentation": "SDL_RenderPresent" in source,
    "nearest scaling": "SDL_SetTextureScaleMode" in source and "SDL_SCALEMODE_NEAREST" in source,
    "2D source wired into SDL3 core library": "'sdl3-2d.c'" in ui_meson,
}

forbidden = {
    "SDL2 RenderCopy": "SDL_RenderCopy" in source,
    "SDL2 RenderSetLogicalSize": "SDL_RenderSetLogicalSize" in source,
}

failures = [name for name, ok in required.items() if not ok]
failures += [f"forbidden: {name}" for name, present in forbidden.items() if present]
if failures:
    raise SystemExit("SDL3 2D contract failures: " + ", ".join(failures))

print("SDL3 2D contract OK")
