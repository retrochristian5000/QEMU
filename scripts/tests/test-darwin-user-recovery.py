#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "devel" / "whp-darwin-user.rst"


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    doc = DOC.read_text(encoding="utf-8")
    required = {
        "historical removal commit": "0adb124659cfadf9f0b5c99874c476116f0cf74f",
        "historical parent tree": "148210301e334694badcc8ae72ecb522c6d7bac6",
        "x86_64 target lane": "x86_64-darwin-user",
        "AArch64 target lane": "aarch64-darwin-user",
        "ARM64E distinction": "arm64e",
        "ARM64EC separation": "arm64ec",
        "Mach-O 64-bit boundary": "MH_MAGIC_64",
        "dyld boundary": "/usr/lib/dyld",
        "LLVM direction": "LLVM must\n   never require Darwin-user to bootstrap",
        "no BSD folding": "Do not fold Darwin into ``bsd-user``",
        "no premature target": "Do not add ``*-darwin-user.mak`` targets merely to make configure list them",
    }
    for label, needle in required.items():
        require(doc, needle, label)

    target_configs = ROOT / "configs" / "targets"
    exposed = sorted(target_configs.glob("*-darwin-user.mak"))
    darwin_meson = ROOT / "darwin-user" / "meson.build"
    if exposed and not darwin_meson.is_file():
        names = ", ".join(path.name for path in exposed)
        raise SystemExit(
            "error: Darwin-user targets exposed before implementation exists: " + names
        )

    print("Darwin-user recovery policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
