#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Static guard for SDL2's VGA dirty-band presentation and active cadence."""

from pathlib import Path

root = Path(__file__).resolve().parents[2]
renderer = (root / "ui/sdl2-2d.c").read_text(encoding="utf-8")
header = (root / "include/ui/sdl2.h").read_text(encoding="utf-8")
core = (root / "include/ui/console.h").read_text(encoding="utf-8")
events = (root / "ui/sdl2.c").read_text(encoding="utf-8")


def section(start: str, end: str) -> str:
    i = renderer.index(start)
    j = renderer.index(end, i + len(start))
    return renderer[i:j]


present = section("static void sdl2_2d_present(", "void sdl2_2d_update(")
update = section("void sdl2_2d_update(", "void sdl2_2d_switch(")
switch = section("void sdl2_2d_switch(", "void sdl2_2d_refresh(")
refresh = section("void sdl2_2d_refresh(", "void sdl2_2d_redraw(")

assert "bool frame_dirty;" in header, "missing pending-frame state"
assert "SDL_UpdateTexture(" in update, "dirty region uploads missing"
assert "scon->frame_dirty = true;" in update, "successful uploads must queue a present"
assert "SDL_RenderPresent(" not in update, "one present per dirty band regressed"
assert renderer.count("SDL_RenderPresent(") == 1, "unexpected additional SDL2 presents"
assert "SDL_RenderPresent(" in present, "present callback missing"
assert "scon->frame_dirty = false;" in present, "present must clear pending state"
assert "scon->frame_dirty = false;" in switch, "mode switch must discard stale damage"
assert refresh.index("qemu_console_hw_update(") < refresh.index("sdl2_2d_present(")
assert refresh.index("sdl2_poll_events(") < refresh.index("sdl2_2d_present(")
assert "if (scon->frame_dirty)" in refresh, "guest animation must count as activity"
assert "scon->idle_counter = 0;" in refresh, "active frames must reset idle tracking"
assert "SDL2_2D_ACTIVE_REFRESH_INTERVAL 16" in renderer
assert "SDL2_REFRESH_INTERVAL_BUSY 10" in events, "input cadence should remain intact"
assert "GUI_REFRESH_INTERVAL_DEFAULT    30" in core, "idle cadence must remain intact"

print("SDL2 VGA presentation and active-frame cadence contract passed")
