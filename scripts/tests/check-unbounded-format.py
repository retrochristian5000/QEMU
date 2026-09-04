#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import re
import subprocess
import sys
from pathlib import Path

CALL_RE = re.compile(r"(?<![A-Za-z0-9_])(?:sprintf|vsprintf)\s*\(")
SOURCE_SUFFIXES = (".c", ".h", ".cc", ".cpp", ".c.inc", ".h.inc", ".m", ".mm")
EXCLUDED_PREFIXES = (
    "tests/",
    "subprojects/",
    "pc-bios/",
    "scripts/",
    "linux-headers/",
    "include/standard-headers/",
)


def strip_comments_and_literals(text: str) -> str:
    """Blank comments and literals while preserving newlines and offsets."""
    out = list(text)
    i = 0
    state = "code"
    quote = ""

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == "code":
            if ch == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                i += 2
                state = "block"
                continue
            if ch == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "line"
                continue
            if ch in "\"'":
                out[i] = " "
                quote = ch
                state = "literal"
        elif state == "block":
            if ch == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 2
                state = "code"
                continue
            if ch != "\n":
                out[i] = " "
        elif state == "line":
            if ch == "\n":
                state = "code"
            else:
                out[i] = " "
        else:
            if ch == "\\" and i + 1 < len(text):
                out[i] = " "
                if text[i + 1] != "\n":
                    out[i + 1] = " "
                i += 2
                continue
            if ch == quote:
                out[i] = " "
                state = "code"
                quote = ""
            elif ch != "\n":
                out[i] = " "
        i += 1

    return "".join(out)


def tracked_sources() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    paths = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        path = Path(raw.decode("utf-8", errors="surrogateescape"))
        name = path.as_posix()
        if name.startswith(EXCLUDED_PREFIXES):
            continue
        if name.endswith(SOURCE_SUFFIXES):
            paths.append(path)
    return paths


def main() -> int:
    hits = []
    for path in tracked_sources():
        text = path.read_text(encoding="utf-8", errors="surrogateescape")
        code = strip_comments_and_literals(text)
        lines = text.splitlines()
        for match in CALL_RE.finditer(code):
            line_no = code.count("\n", 0, match.start()) + 1
            source = lines[line_no - 1].strip() if line_no <= len(lines) else ""
            hits.append((path.as_posix(), line_no, source))

    if not hits:
        return 0

    print(
        "error: QEMU-owned production code uses unbounded sprintf()/vsprintf(); "
        "use snprintf()/vsnprintf().",
        file=sys.stderr,
    )
    for path, line_no, source in hits:
        print(f"{path}:{line_no}: {source}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
