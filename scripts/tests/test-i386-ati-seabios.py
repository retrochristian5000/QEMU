#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import json
import pathlib
import select
import subprocess
import sys
import time


def read_json_line(proc: subprocess.Popen[str], timeout: float = 10.0) -> dict:
    assert proc.stdout is not None
    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        raise RuntimeError("timed out waiting for QMP response")
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr is not None else ""
        raise RuntimeError(f"QEMU exited while waiting for QMP: {stderr}")
    return json.loads(line)


def qmp(proc: subprocess.Popen[str], execute: str, arguments: dict | None = None) -> dict:
    assert proc.stdin is not None
    command = {"execute": execute}
    if arguments:
        command["arguments"] = arguments
    proc.stdin.write(json.dumps(command) + "\n")
    proc.stdin.flush()
    while True:
        reply = read_json_line(proc)
        if "event" in reply:
            continue
        return reply


def ppm_has_visible_pixels(path: pathlib.Path) -> bool:
    data = path.read_bytes()
    if not data.startswith(b"P6\n"):
        raise RuntimeError(f"unexpected screendump format in {path}")

    # QEMU's PPM writer emits a short ASCII header followed by RGB bytes.
    parts = data.split(b"\n", 3)
    if len(parts) != 4 or parts[2] != b"255":
        raise RuntimeError(f"malformed PPM header in {path}")
    pixels = parts[3]
    if not pixels:
        return False

    # A VGA text POST screen must contain pixels that differ from the dominant
    # background. Requiring at least two RGB values catches an all-black/all-one
    # colour surface without depending on a particular SeaBIOS banner string.
    first = pixels[:3]
    return any(pixels[i:i + 3] != first for i in range(3, len(pixels), 3))


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} /path/to/qemu-system-i386", file=sys.stderr)
        return 2

    binary = pathlib.Path(sys.argv[1]).resolve()
    if not binary.is_file():
        print(f"error: missing qemu-system-i386: {binary}", file=sys.stderr)
        return 2

    dump = pathlib.Path("build-ci/i386-ati-seabios.ppm").resolve()
    dump.parent.mkdir(parents=True, exist_ok=True)
    dump.unlink(missing_ok=True)

    cmd = [
        str(binary),
        "-machine", "pc",
        "-accel", "tcg,thread=single",
        "-m", "64M",
        "-display", "none",
        "-monitor", "none",
        "-serial", "none",
        "-parallel", "none",
        "-net", "none",
        "-boot", "menu=off",
        "-qmp", "stdio",
        "-device", "ati-vga",
    ]

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        greeting = read_json_line(proc)
        if "QMP" not in greeting:
            raise RuntimeError(f"unexpected QMP greeting: {greeting}")
        reply = qmp(proc, "qmp_capabilities")
        if "return" not in reply:
            raise RuntimeError(f"qmp_capabilities failed: {reply}")

        pci = qmp(proc, "query-pci")
        if "return" not in pci:
            raise RuntimeError(f"query-pci failed: {pci}")
        pci_text = json.dumps(pci["return"])
        if '"vendor": 4098' not in pci_text or '"device": 20550' not in pci_text:
            raise RuntimeError("ATI Rage 128 Pro (1002:5046) was not created")

        # Give SeaBIOS and its VGA option ROM enough virtual wall time to POST.
        time.sleep(2.0)
        shot = qmp(proc, "screendump", {"filename": str(dump)})
        if "return" not in shot:
            raise RuntimeError(f"screendump failed: {shot}")
        if not dump.is_file():
            raise RuntimeError("screendump did not create a PPM")
        if not ppm_has_visible_pixels(dump):
            raise RuntimeError("ATI VGA framebuffer stayed blank during SeaBIOS POST")
    finally:
        if proc.poll() is None:
            try:
                qmp(proc, "quit")
            except Exception:
                proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    print("i386 ATI SeaBIOS display: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
