#!/usr/bin/env python3
"""Guard the selective --enable-tools build contract."""

from pathlib import Path


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing selective-tools contract in {where}: {needle}")


meson_options = Path("meson_options.txt").read_text(encoding="utf-8")
meson_build = Path("meson.build").read_text(encoding="utf-8")
configure = Path("configure").read_text(encoding="utf-8")
generator = Path("scripts/meson-buildoptions.py").read_text(encoding="utf-8")
generated = Path("scripts/meson-buildoptions.sh").read_text(encoding="utf-8")
functional = Path("tests/functional/meson.build").read_text(encoding="utf-8")
iotests = Path("tests/qemu-iotests/meson.build").read_text(encoding="utf-8")

# Keep the established all/none interface intact.
require(generated, '--enable-tools) printf "%s" -Dtools=enabled ;;',
        "scripts/meson-buildoptions.sh")
require(generated, '--disable-tools) printf "%s" -Dtools=disabled ;;',
        "scripts/meson-buildoptions.sh")

# Selective mode is a manual configure extension backed by a Meson allowlist.
require(meson_options, "option('tool_list'", "meson_options.txt")
require(generator, '"tool_list"', "scripts/meson-buildoptions.py")
require(configure, '--enable-tools=*)', "configure")
require(configure, '-Dtool_list=', "configure")

# Meson must expose per-tool selection and gate the primary block tools.
require(meson_build, "tool_list = get_option('tool_list')", "meson.build")
require(meson_build, "tool_enabled = {}", "meson.build")
for tool in ('qemu-img', 'qemu-io', 'qemu-nbd', 'qemu-storage-daemon'):
    require(meson_build, f"tool_enabled['{tool}']", "meson.build")

# Tests must not equate 'some tool enabled' with qemu-img/all block tools.
require(functional, "tool_enabled['qemu-img']", "tests/functional/meson.build")
for tool in ('qemu-img', 'qemu-io', 'qemu-nbd', 'qemu-storage-daemon'):
    require(iotests, f"tool_enabled['{tool}']", "tests/qemu-iotests/meson.build")

print("selective tools contract: ok")
