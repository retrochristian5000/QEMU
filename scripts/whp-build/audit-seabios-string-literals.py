#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Inventory emitted SeaBIOS assembly literals; do not claim ROM savings."""

import ast
import pathlib
import re
import sys
from collections import defaultdict

LITERAL = re.compile(
    r'^\s*\.(?:asciz|string|ascii)\s+("(?:\\.|[^"\\])*")\s*(?:[#;].*)?$'
)


def emitted_literals(assembly):
    """Yield bytes from unambiguous single-string assembler directives."""
    for line in assembly.splitlines():
        match = LITERAL.fullmatch(line)
        if match is None:
            continue
        try:
            value = ast.literal_eval("b" + match.group(1))
        except (SyntaxError, ValueError):
            continue
        yield value


def summarize(paths):
    """Return reports and overlap candidates, not presumed linked-ROM bytes."""
    reports = []
    appearances = defaultdict(set)
    for mode, path in paths:
        data = pathlib.Path(path).read_text(encoding="utf-8")
        strings = list(emitted_literals(data))
        reports.append((mode, len(strings), sum(len(s) + 1 for s in strings)))
        for value in strings:
            appearances[value].add(mode)

    repeated = [(data, modes) for data, modes in appearances.items()
                if len(modes) > 1 and len(data) >= 4]
    repeated.sort(key=lambda item: (-len(item[0]), item[0]))
    return reports, repeated


def main(argv):
    if len(argv) != 4:
        print("usage: audit-seabios-string-literals.py "
              "CCODE16.s CODE32SEG.s CCODE32FLAT.s", file=sys.stderr)
        return 2
    modes = ("16bit", "32seg", "32flat")
    try:
        reports, repeated = summarize(zip(modes, argv[1:]))
    except (OSError, UnicodeError) as exc:
        print("ROM literal audit: %s" % exc, file=sys.stderr)
        return 1

    print("ROM literal audit: emitted assembly directives (not retained ROM)")
    for mode, count, size in reports:
        print("  %-7s directives=%d estimated-bytes=%d" %
              (mode, count, size))
    print("ROM literal audit: %d cross-mode literal matches; "
          "sharing is not assumed safe" % len(repeated))
    for value, modes in repeated[:8]:
        preview = repr(value[:55])
        print("  bytes=%d modes=%s text=%s" %
              (len(value) + 1, ",".join(sorted(modes)), preview))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
