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
    helper = (ROOT / "scripts/ensure-libisofs.py").read_text(encoding="utf-8")
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    workflow = (
        ROOT / ".github/workflows/native-llvm-macos.yml"
    ).read_text(encoding="utf-8")

    require(
        gitmodules,
        '[submodule "toolchains/libisofs"]',
        "libisofs submodule declaration",
    )
    require(gitmodules, "path = toolchains/libisofs", "libisofs submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/libisofs.git",
        "WHP libisofs fork URL",
    )
    require(gitmodules, "branch = master", "libisofs fork branch")

    require(
        config,
        "Option('BOOTSTRAP_LIBISOFS', 'Host features', "
        "'Bootstrap/use WHP libisofs', 'choice', 'auto', "
        "('auto', 'y', 'n'))",
        "menuconfig libisofs bootstrap policy",
    )
    require(config, "'BOOTSTRAP_LIBISOFS',", "libisofs tri-state export")

    require(
        build,
        "BOOTSTRAP_LIBISOFS=${BOOTSTRAP_LIBISOFS:-auto}",
        "libisofs bootstrap default",
    )
    require(build, "scripts/ensure-libisofs.py", "libisofs bootstrap hook")
    require(build, "LIBISOFS_BOOTSTRAP_MODE=force", "forced fork policy")
    require(build, "WHP_LIBISOFS_PREFIX", "private libisofs prefix")
    require(build, "PKG_CONFIG_PATH=", "libisofs pkg-config handoff")

    require(helper, 'toolchains/libisofs', "pinned libisofs source path")
    require(helper, '"submodule", "update"', "lazy submodule initialization")
    require(helper, "LIBISOFS_GIT_COMMIT=", "libisofs cache revision identity")
    require(helper, 'PKG_NAME = "libisofs-1"', "pkg-config identity")
    require(helper, '"-Werror=strict-prototypes"', "strict prototype probe")
    require(helper, '"--disable-shared"', "static-only fork bootstrap")
    require(helper, '"--enable-static"', "static fork bootstrap")
    require(helper, '"--disable-libjte"', "minimal libisofs bootstrap")

    require(
        meson,
        "dependency('libisofs-1', version: '>=1.1.2'",
        "QEMU libisofs dependency contract",
    )
    require(
        meson,
        "name: 'libisofs strict prototypes'",
        "Meson strict-prototype compile probe",
    )
    require(
        meson,
        "libisofs.h is incompatible with -Wstrict-prototypes",
        "forced dependency diagnostic",
    )

    require(workflow, "autoconf automake", "Autotools CI dependencies")
    require(workflow, "libtool", "libtool CI dependency")
    if "glib libisofs libslirp" in workflow:
        raise SystemExit(
            "error: native macOS CI still installs Homebrew libisofs instead "
            "of exercising the pinned WHP fork"
        )

    print("WHP libisofs bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
