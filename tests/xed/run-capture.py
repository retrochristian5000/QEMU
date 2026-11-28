#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run the controlled i386 XED memory-capture guest, not arbitrary firmware."""

import argparse
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--guest", required=True, type=Path)
    parser.add_argument("--plugin", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--nm", default="nm")
    args = parser.parse_args()

    for path in (args.qemu, args.guest, args.plugin, args.reference):
        if not path.is_file():
            parser.error(f"Missing required build artifact: {path}")

    symbols = {}
    for line in subprocess.check_output(
            [args.nm, str(args.guest.resolve())], text=True).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] in {
                "xed_capture_start", "xed_capture_end"}:
            symbols[fields[2]] = int(fields[0], 16)
    if set(symbols) != {"xed_capture_start", "xed_capture_end"}:
        parser.error("Guest capture symbols missing")
    start = symbols["xed_capture_start"]
    end = symbols["xed_capture_end"]
    if not 0 <= start < end <= 0xffffffff or end - start > 4096:
        parser.error("Guest capture range is invalid")

    plugin = str(args.plugin.resolve())
    if "," in plugin:
        parser.error("Plugin path must not contain a comma")

    with tempfile.TemporaryDirectory(prefix="qemu-xed-") as directory:
        log = Path(directory) / "capture.log"
        subprocess.run([
            str(args.qemu.resolve()), "-accel", "tcg", "-M", "pc",
            "-cpu", "pentium_mmx", "-smp", "1", "-display", "none",
            "-monitor", "none", "-serial", "none", "-no-reboot",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x4",
            "-kernel", str(args.guest.resolve()),
            "-plugin", f"{plugin},start={start:x},end={end:x}",
            "-d", "plugin", "-D", str(log),
        ], check=True, timeout=60)

        records = log.read_text(encoding="utf-8").splitlines()
        if any(line.startswith("XEDCAPTURE_ERROR ") for line in records):
            raise RuntimeError("TCG reported an incomplete or invalid capture")
        rows = [line for line in records if line.startswith("XEDMEM ")]
        expected = [
            ("8b1488", "5008", "4", "r"),
            ("668b78fe", "5002", "2", "r"),
            ("678b28", "5000", "4", "r"),
            ("896804", "5008", "4", "w"),
        ]
        actual = [tuple(line.split()[1:5]) for line in rows]
        if actual != expected:
            raise RuntimeError(f"Unexpected TCG memory observations: {actual!r}")
        subprocess.run([
            str(args.reference.resolve()), "--agen", "legacy32", "32",
            "pentium_mmx",
        ], input="\n".join(rows) + "\n", text=True, check=True)
    print("TCG/XED memory comparison: four completed accesses matched")


if __name__ == "__main__":
    main()
