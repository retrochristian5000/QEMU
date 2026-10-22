#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Parse every tracked Meson definition without configuring QEMU.

Use Meson's real parser, not a hand-written delimiter or indentation checker.
This includes conditionally selected architectures that configure may not visit.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

from mesonbuild import mparser


ROOT = pathlib.Path(__file__).resolve().parents[2]
MESON_NAMES = {"meson.build", "meson_options.txt", "meson.options"}


def tracked_meson_files() -> list[pathlib.Path]:
    names = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached"]
    )
    paths = [
        pathlib.Path(name.decode("utf-8"))
        for name in names.split(b"\0")
        if name
    ]
    return sorted(
        (path for path in paths if path.name in MESON_NAMES),
        key=lambda path: path.as_posix(),
    )


def verify_parser() -> None:
    mparser.Parser(
        "project('syntax-probe', 'c')\nif true\n  message('ok')\nendif\n",
        "<syntax-positive>",
    ).parse()

    # If this accidentally starts accepting invalid syntax, the gate is
    # useless. This is deliberately broken with no closing endif.
    try:
        mparser.Parser(
            "if true\n  message('unclosed')\n",
            "<syntax-negative>",
        ).parse()
    except mparser.ParseException:
        return
    raise RuntimeError("Meson parser did not reject an unclosed if statement")


def main() -> int:
    verify_parser()
    paths = tracked_meson_files()
    if not paths or pathlib.Path("meson.build") not in paths:
        print("error: tracked root meson.build was not discovered", file=sys.stderr)
        return 2

    failures = 0
    for path in paths:
        full_path = ROOT / path
        try:
            source = full_path.read_text(encoding="utf-8")
            mparser.Parser(source, path.as_posix()).parse()
        except (OSError, UnicodeError, mparser.ParseException) as exc:
            print(f"error: {path}: {exc}", file=sys.stderr)
            failures += 1

    passed = len(paths) - failures
    print(
        f"Meson {__import__('mesonbuild.coredata', fromlist=['version']).version}: "
        f"parsed {passed}/{len(paths)} tracked Meson files"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
