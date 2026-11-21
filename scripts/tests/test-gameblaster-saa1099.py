#!/usr/bin/env python3
"""Compile SAA1099 mixer regression tests using the native C compiler."""

import os
import pathlib
import shlex
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> None:
    device = (ROOT / "hw/audio/gameblaster.c").read_text(encoding="utf-8")
    for call in ("cms_voice_signed_level(", "cms_envelope_stereo_level("):
        if device.count(call) != 1:
            raise RuntimeError(f"Game Blaster sound output lost helper call: {call}")

    compiler = shlex.split(os.environ.get("CC_FOR_BUILD") or "cc")
    if len(compiler) != 1:
        raise RuntimeError("CC_FOR_BUILD must identify one native compiler")
    with tempfile.TemporaryDirectory(prefix="whp-gameblaster-") as name:
        binary = pathlib.Path(name) / "saa1099-test"
        source = ROOT / "tests/unit/gameblaster-saa1099-test.c"
        subprocess.run(
            [compiler[0], "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-pedantic", "-I", str(ROOT / "hw/audio"),
             str(source), "-o", str(binary)],
            check=True,
        )
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
