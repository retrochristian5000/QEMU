#!/usr/bin/env python3
"""Compile and execute the standalone TriMedia compressed-packet C regression."""
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKT = ROOT / "target" / "trimedia"
TEST = ROOT / "scripts" / "tests" / "trimedia-packet-layout-test.c"

with tempfile.TemporaryDirectory(prefix="trimedia-packet-") as tmp:
    scratch = Path(tmp)
    shim = scratch / "qemu"
    shim.mkdir()
    (shim / "osdep.h").write_text("#include <string.h>\n", encoding="utf-8")
    cmd = shlex.split(os.environ.get("CC", "cc")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I" + str(scratch), "-I" + str(PKT),
        str(PKT / "packet.c"), str(TEST),
        "-o", str(scratch / "packet-layout-test"),
    ]
    subprocess.run(cmd, check=True)
    subprocess.run([str(scratch / "packet-layout-test")], check=True)
