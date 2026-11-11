#!/usr/bin/env python3
"""SDL3 input contract: preserve QEMU key state and separate event ownership."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "ui/sdl3-input.c").read_text(encoding="utf-8")
header = (ROOT / "include/ui/sdl3-input.h").read_text(encoding="utf-8")
display = (ROOT / "ui/sdl3-display.c").read_text(encoding="utf-8")
display_header = (ROOT / "include/ui/sdl3-display.h").read_text(encoding="utf-8")
ui_meson = (ROOT / "ui/meson.build").read_text(encoding="utf-8")

required = {
    "SDL3 key events": "SDL_EVENT_KEY_DOWN" in source and "SDL_EVENT_KEY_UP" in source,
    "physical scancodes": "event->key.scancode" in source,
    "bounds checking": "qemu_input_map_usb_to_linux_len" in source,
    "unmapped key guard": "SDL_SCANCODE_UNKNOWN" in source and "KEY_RESERVED" in source,
    "QEMU key state": "qkbd_state_key_event" in source and "qkbd_state_init" in source,
    "window-scoped key events": "event->key.windowID" in source,
    "window-scoped text events": "event->text.windowID" in source,
    "window-scoped focus events": "event->window.windowID" in source,
    "text input lifecycle": "SDL_StartTextInput(window)" in source
        and "SDL_StopTextInput(input->window)" in source,
    "UTF-8 input only to text console": "QEMU_IS_TEXT_CONSOLE(con)" in source
        and "qemu_text_console_put_string" in source,
    "release modifiers on focus loss": "SDL_EVENT_WINDOW_FOCUS_LOST" in source
        and "qkbd_state_lift_all_keys(input->kbd)" in source,
    "SDL3 main-thread dispatch": "SDL_IsMainThread()" in source,
    "SDL3 only": "#include <SDL3/SDL.h>" in header and "ui/sdl2.h" not in source,
    "Meson compile": "'sdl3-input.c'" in ui_meson,
    "display init": "qemu_sdl3_input_init" in display,
    "display cleanup": "qemu_sdl3_input_destroy" in display,
    "display event entrypoint": "qemu_sdl3_display_2d_event" in display
        and "qemu_sdl3_display_2d_event" in display_header,
}
forbidden = {
    "obsolete SDL2 key structure": "keysym.scancode" in source,
    "obsolete SDL2 events": "SDL_KEYDOWN" in source or "SDL_TEXTINPUT" in source,
    "SDL2 scancode mapping": "SDL_ScancodeToKeycode" in source,
    "event polling inside receiver": "SDL_PollEvent" in source,
}
failed = [name for name, ok in required.items() if not ok]
failed += [f"forbidden: {name}" for name, found in forbidden.items() if found]
if failed:
    raise SystemExit("SDL3 input contract failed: " + ", ".join(failed))
print("SDL3 keyboard / text / focus-loss contract OK")
