#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-bash.py").read_text(encoding="utf-8")

    require(gitmodules, '[submodule "toolchains/bash"]', "Bash submodule")
    require(gitmodules, "path = toolchains/bash", "Bash submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/bash.git",
        "WHP Bash fork URL",
    )
    require(gitmodules, "branch = master", "Bash fork branch")
    require(
        config,
        "Option('BOOTSTRAP_BASH', 'Host features', 'Bootstrap/use WHP Bash'",
        "Bash bootstrap menu policy",
    )
    require(config, "'BOOTSTRAP_BASH',", "Bash tri-state shell export")
    require(build, "BOOTSTRAP_BASH=", "Bash default policy")
    require(build, "scripts/ensure-bash.py", "Bash bootstrap hook")
    require(build, "WHP_BUILD_BASH_EXPLICIT", "explicit Bash override")
    require(helper, "toolchains/bash", "pinned Bash source")
    require(helper, '"submodule", "update"', "lazy Bash submodule initialization")
    require(helper, "BASH_GIT_COMMIT=", "Bash cache revision identity")
    require(helper, 'env.pop("INSTALL", None)', "INSTALL namespace isolation")
    require(helper, '"--without-bash-malloc"', "system malloc profile")
    require(helper, '"--disable-nls"', "minimal Bash profile")
    require(helper, '"-isysroot", sdkroot', "macOS Bash SDK routing")
    print("WHP Bash bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
