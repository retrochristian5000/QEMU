#!/usr/bin/env python3
"""Guard qemu-nbd against redundant direct includes."""

from pathlib import Path


source = Path("qemu-nbd.c").read_text(encoding="utf-8")

redundant_headers = (
    "#include <getopt.h>",
    '#include "qobject/qstring.h"',
)

for header in redundant_headers:
    if header in source:
        raise SystemExit(f"redundant qemu-nbd header is still present: {header}")

print("qemu-nbd include hygiene: ok")
