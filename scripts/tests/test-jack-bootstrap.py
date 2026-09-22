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
    helper = (ROOT / "scripts/ensure-jack.py").read_text(encoding="utf-8")
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")

    require(gitmodules, '[submodule "toolchains/jack"]', "JACK submodule declaration")
    require(gitmodules, "path = toolchains/jack", "JACK submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/jack.git",
        "WHP JACK fork URL",
    )
    require(gitmodules, "branch = master", "JACK fork branch")

    require(
        config,
        "Option('BOOTSTRAP_JACK', 'Host features', 'Bootstrap/use WHP JACK', "
        "'choice', 'auto', ('auto', 'y', 'n'))",
        "menuconfig JACK bootstrap policy",
    )
    require(config, "'BOOTSTRAP_JACK',", "JACK tri-state shell export")

    require(build, "BOOTSTRAP_JACK=${BOOTSTRAP_JACK:-auto}", "JACK bootstrap default")
    require(build, "scripts/ensure-jack.py", "JACK bootstrap hook")
    require(build, "JACK_BOOTSTRAP_MODE=force", "forced JACK fork policy")
    require(build, "WHP_JACK_PREFIX", "private JACK prefix")
    require(build, "PKG_CONFIG_PATH=", "JACK pkg-config handoff")

    require(helper, 'toolchains/jack', "pinned JACK source path")
    require(helper, '"submodule",', "lazy JACK submodule initialization")
    require(helper, "JACK_GIT_COMMIT=", "JACK cache revision identity")
    require(helper, "JACK_BOOTSTRAP_SCHEMA", "JACK bootstrap cache schema")
    require(helper, '"--client-only"', "JACK client-only build profile")
    require(helper, '"--autostart=none"', "JACK server autostart suppression")
    require(helper, '"WHP_MACOS_ARCH"', "shared macOS ABI policy")
    require(helper, 'abi = f"-arch {arch}"', "explicit JACK Darwin architecture")

    require(meson, "dependency('jack'", "QEMU JACK dependency contract")

    print("WHP JACK bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
