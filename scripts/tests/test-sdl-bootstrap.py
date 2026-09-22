#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-sdl.py").read_text(encoding="utf-8")
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")

    require(gitmodules, '[submodule "toolchains/sdl"]', "SDL submodule declaration")
    require(gitmodules, "path = toolchains/sdl", "SDL submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/SDLosaurus.git",
        "WHP SDL fork URL",
    )
    require(gitmodules, "branch = main", "SDL fork branch")

    require(
        config,
        "Option('BOOTSTRAP_SDL', 'Host features', 'Bootstrap/use WHP SDL3', "
        "'choice', 'auto', ('auto', 'y', 'n'))",
        "menuconfig SDL bootstrap policy",
    )
    require(config, "'BOOTSTRAP_SDL',", "SDL tri-state shell export")

    require(build, "BOOTSTRAP_SDL=${BOOTSTRAP_SDL:-auto}", "SDL bootstrap default")
    require(build, 'scripts/ensure-sdl.py', "SDL bootstrap hook")
    require(build, 'SDL_BOOTSTRAP_MODE=force', "forced SDL fork policy")
    require(build, 'PKG_CONFIG_PATH=', "SDL pkg-config handoff")
    require(build, 'CMAKE_PREFIX_PATH=', "SDL CMake handoff")
    require(build, 'SDL3_ROOT=', "SDL prefix identity handoff")

    require(helper, 'toolchains/sdl', "pinned SDL source path")
    require(helper, '"submodule",', "lazy SDL submodule initialization")
    require(helper, 'SDL_GIT_COMMIT=', "SDL cache revision identity")
    require(helper, 'SDL_BOOTSTRAP_SCHEMA', "SDL bootstrap cache schema")
    require(helper, '"--atleast-version=3.2.0"', "host SDL3 minimum version probe")
    require(helper, '"-DSDL_SHARED=OFF"', "static-only SDL bootstrap")
    require(helper, '"-DSDL_STATIC=ON"', "static SDL library bootstrap")
    require(helper, '"-DSDL_INSTALL=ON"', "SDL install staging")
    require(helper, 'CMAKE_MAKE_PROGRAM', "selected Ninja handoff to SDL CMake")

    require(
        meson,
        "dependency('sdl3', version: '>=3.2.0'",
        "QEMU SDL3 dependency contract",
    )

    print("WHP SDL3 bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
