#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GITMODULES = ROOT / ".gitmodules"
LEDGER = ROOT / "docs" / "devel" / "whp-dependency-ledger.rst"


def main() -> int:
    parser = configparser.ConfigParser()
    parser.read(GITMODULES, encoding="utf-8")
    paths = [
        parser[section]["path"].strip()
        for section in parser.sections()
        if section.startswith("submodule ") and "path" in parser[section]
    ]

    ledger = LEDGER.read_text(encoding="utf-8")
    missing = [path for path in paths if f"``{path}``" not in ledger]
    if missing:
        raise SystemExit(
            "error: WHP dependency ledger is missing submodules: "
            + ", ".join(sorted(missing))
        )

    # The pinned Meson fork is the default; an explicitly saved venv
    # selection must remain authoritative without silent migration.
    meson_section = 'submodule "toolchains/meson"'
    if meson_section not in parser:
        raise SystemExit("error: WHP Meson source submodule is missing")
    meson = parser[meson_section]
    if (meson.get("path") != "toolchains/meson"
            or meson.get("url") != "https://github.com/retrochristian5000/Meson.git"
            or meson.get("branch") != "master"):
        raise SystemExit("error: WHP Meson submodule points to an unexpected source")

    required_contracts = {
        "pinned Meson source boundary": (
            "Pinned Meson source boundary",
            "toolchains/meson",
            "toolchains/meson/meson.py",
            "WHP_MESON_PROVIDER=venv",
            "never silently migrated",
        ),
        "Aften/JACK conditional edge": (
            "Full macOS server builds have a conditional Aften edge",
            "``--client-only`` profile deliberately skips Aften",
        ),
        "AArch64/arm64e distinction": (
            "``aarch64``",
            "``arm64e``",
            "NEON",
            "optimization opportunity",
        ),
        "circularity policy": (
            "Circularity guards",
            "must not make\n   itself its own root dependency",
        ),
        "gitlink authority": (
            "The gitlink recorded by the QEMU commit is authoritative",
        ),
        "external active-consumer classification": (
            "External host-tool edges by active consumer",
            "PowerPC GCC/binutils **source rebuild**",
            "Reusing a validated installed PowerPC toolchain",
            "OpenBIOS / SeaBIOS preparation",
            "IA32 EFI GRUB source/LLVM expansion",
            "macOS toolchain and LTO manifests",
            "Optional mold linker",
        ),
        "required dependency guard policy": (
            "Required dependency guard policy",
            "not a second source of immutable commit gates",
            "Downstream",
            "Failure of an unrelated optional dependency must not stop",
            "Incomplete ancestry is",
        ),
    }
    for label, needles in required_contracts.items():
        for needle in needles:
            if needle not in ledger:
                raise SystemExit(
                    f"error: WHP dependency ledger lost {label}: {needle}"
                )

    # The PowerPC cross-toolchain can be reused without network/download,
    # archive, checksum or GNU Make prerequisites. These checks belong after
    # the installed-toolchain marker and capability check, not at entry.
    powerpc = (ROOT / "scripts" / "bootstrap-powerpc-toolchain.bash").read_text(
        encoding="utf-8"
    )
    cache_hit = powerpc.index('toolchain_is_usable "$TOOLCHAIN_DIR"')
    for needle in (
        'make_banner=$("$MAKE_CMD" --version',
        'for required in tar bzip2 gzip perl ln mv rm; do',
        'if command -v curl >/dev/null 2>&1; then',
        'if command -v shasum >/dev/null 2>&1; then',
    ):
        if needle not in powerpc or powerpc.index(needle) < cache_hit:
            raise SystemExit(
                "error: PowerPC rebuild-only prerequisite precedes cache reuse: "
                + needle
            )
    early_checks = powerpc[:cache_hit]
    if 'for required in tar bzip2 gzip perl' in early_checks:
        raise SystemExit("error: PowerPC source tools became universal roots")

    if len(paths) != len(set(paths)):
        raise SystemExit("error: duplicate submodule paths in .gitmodules")

    print(f"WHP dependency ledger: {len(paths)} top-level submodules covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
