#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
meson = (ROOT / "pc-bios/meson.build").read_text(encoding="utf-8")
build_targets = (ROOT / "scripts/whp-build/build-targets.bash").read_text(encoding="utf-8")

targets = (
    "whp-openbios-ppc",
    "whp-seabios-x86",
    "whp-seabios-grub",
    "whp-seabios-hybrid-iso",
)

for target in targets:
    assert target in build_targets, f"build driver no longer requests {target}"
    assert f"alias_target('{target}'" in meson, (
        f"Meson does not expose {target} as a backend target"
    )

print("firmware Ninja target aliases: verified")
