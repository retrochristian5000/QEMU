#!/usr/bin/env python3
"""Fail when Meson configuration logs contain Meson-level warnings."""

from __future__ import annotations

import pathlib
import re
import sys

DIAGNOSTIC_RE = re.compile(r"(?:^|:\s)(?:WARNING|DEPRECATION):\s")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: check-meson-warnings.py LOG [LOG ...]", file=sys.stderr)
        return 2

    diagnostics: list[tuple[pathlib.Path, int, str]] = []
    for name in argv:
        path = pathlib.Path(name)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            print(f"error: cannot read Meson log {path}: {exc}", file=sys.stderr)
            return 2
        for lineno, line in enumerate(lines, 1):
            if DIAGNOSTIC_RE.search(line):
                diagnostics.append((path, lineno, line))

    if diagnostics:
        print("error: Meson configuration emitted warning diagnostics:", file=sys.stderr)
        for path, lineno, line in diagnostics:
            print(f"{path}:{lineno}: {line}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
