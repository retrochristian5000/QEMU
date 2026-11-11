#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    parser = configparser.ConfigParser()
    parser.read(ROOT / ".gitmodules", encoding="utf-8")
    section = 'submodule "toolchains/xen"'
    if section not in parser:
        raise SystemExit("error: Xen fork is not registered as toolchains/xen")
    if parser[section].get("url") != "https://github.com/retrochristian5000/xen.git":
        raise SystemExit("error: toolchains/xen does not point at the WHP Xen fork")
    if parser[section].get("branch") != "master":
        raise SystemExit("error: toolchains/xen must retain master as discovery metadata")
    if parser[section].get("shallow") != "true":
        raise SystemExit("error: toolchains/xen must remain shallow-capable")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(
        encoding="utf-8"
    )
    require(ledger, "toolchains/xen", "Xen ledger row")
    require(ledger, "Xen source boundary", "Xen dependency boundary")
    require(ledger, "planned", "Xen planned-source state")
    require(
        ledger,
        "Routine QEMU source refresh must not materialize Xen",
        "Xen lazy-source policy",
    )

    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    require(
        meson,
        "dependency('xencontrol', required: false,",
        "QEMU xencontrol dependency probe",
    )
    require(meson, "method: 'pkg-config'", "QEMU Xen pkg-config boundary")

    updater = (ROOT / "scripts/whp-build/update-source.sh").read_text(
        encoding="utf-8"
    )
    require(updater, "pinned submodules remain lazy", "lazy submodule updater")
    if "submodule update --init --recursive" in updater:
        raise SystemExit("error: routine source refresh must not eagerly initialize Xen")

    print("Xen dependency policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
