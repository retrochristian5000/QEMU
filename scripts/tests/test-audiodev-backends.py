#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard audio backend discovery, default priority, and macOS build parity."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

meson = read("meson.build")
modules = read("audio/meson.build")
audio = read("audio/audio.c")
native = read("scripts/whp-build/prepare-build.bash")
portable = read("scripts/whp-build/portable-build.py")
options = read("meson_options.txt")
workflow = read(".github/workflows/native-llvm-macos.yml")

# Backend implementation, dependency, and dynamic module must agree.
backends = {
    "coreaudio": ("coreaudio.m", "CoreAudio", "appleframeworks"),
    "sdl": ("sdlaudio.c", "sdl3", "sdl_audio"),
    "jack": ("jackaudio.c", "jack", "jack"),
}
for driver, (source, dependency, variable) in backends.items():
    assert f"['{driver}', {variable}, files('{source}')]" in modules
    assert f"module_obj(TYPE_AUDIO_{driver.upper()});" in read(
        f"audio/{source}"
    )
    assert dependency in meson
    
assert "'CONFIG_AUDIO_' + k.to_upper()" in meson
assert "dependency('sdl3', version: '>=3.2.0'" in meson
assert "dependency('jack', required: get_option('jack')" in meson
assert "modules += {'audio': audio_modules}" in modules

# An explicit CoreAudio/PA feature must never hide independently available
# SDL3 from the automatic fallback list. Both build paths agree on this.
assert "whp_add_optional_configure_switch" in native
assert "MACOS_ENABLE_COREAUDIO" in native
assert "MACOS_ENABLE_PA" in native
assert "--audio-drv-list=" not in native
assert "--audio-drv-list=" not in portable
priority = meson.split("  # Prefer native CoreAudio on macOS", 1)[1].split(
    "  audio_drivers_default = []", 1
)[0]
assert "?" not in priority, "nested Meson ternary is not permitted"
assert "if host_os == 'darwin'" in priority
assert "audio_drivers_priority = ['coreaudio', 'pa', 'sdl']" in priority
assert (
    "else\n"
    "    audio_drivers_priority = "
    "['pa', 'coreaudio', 'dsound', 'sndio', 'oss']"
) in priority
assert "if host_os != 'linux'" in priority
assert "audio_drivers_priority += ['sdl']" in priority
assert priority.count("endif") == 2
assert "'default'" in options

# A requested backend still appears in -audiodev help only if its QOM
# backend is actually registered; an unavailable library is not advertised.
assert "module_object_class_by_name(tname)" in audio
assert "if (be) {" in audio
assert 'printf("%s\\n", name);' in audio
assert workflow.count("for backend in sdl jack; do") == 2
assert "CONFIG_AUDIO_${backend^^}" in workflow
assert 'grep -Fxq "$backend"' in workflow

print("Audio backend discovery and macOS default priority: verified")
