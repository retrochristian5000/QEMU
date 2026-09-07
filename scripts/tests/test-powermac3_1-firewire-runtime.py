#!/usr/bin/env python3
"""Verify the live PowerMac3,1 PCI tree contains its TSB12LV23."""

import json
from pathlib import Path
import subprocess
import sys

if len(sys.argv) != 2:
    raise SystemExit(f"usage: {Path(sys.argv[0]).name} QEMU-SYSTEM-PPC")

binary = sys.argv[1]
commands = "\n".join(
    (
        '{"execute":"qmp_capabilities"}',
        '{"execute":"query-pci"}',
        '{"execute":"quit"}',
        "",
    )
)

proc = subprocess.run(
    [
        binary,
        "-machine", "powermac3_1",
        "-display", "none",
        "-monitor", "none",
        "-serial", "none",
        "-nodefaults",
        "-S",
        "-qmp", "stdio",
    ],
    input=commands,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    timeout=20,
    check=False,
)

if proc.returncode != 0:
    print(proc.stdout, file=sys.stderr)
    print(proc.stderr, file=sys.stderr)
    raise SystemExit(f"qemu-system-ppc exited with status {proc.returncode}")

responses = []
for line in proc.stdout.splitlines():
    try:
        responses.append(json.loads(line))
    except json.JSONDecodeError:
        continue

pci_reply = next(
    (item["return"] for item in responses
     if isinstance(item, dict) and isinstance(item.get("return"), list)),
    None,
)
if pci_reply is None:
    print(proc.stdout, file=sys.stderr)
    raise SystemExit("query-pci returned no PCI topology")

matches = []

def walk(value):
    if isinstance(value, dict):
        ident = value.get("id")
        if isinstance(ident, dict) and ident.get("vendor") == 0x104c \
                and ident.get("device") == 0x8019:
            matches.append(value)
        for child in value.values():
            walk(child)
    elif isinstance(value, list):
        for child in value:
            walk(child)

walk(pci_reply)

if len(matches) != 1:
    print(json.dumps(pci_reply, indent=2), file=sys.stderr)
    raise SystemExit(f"expected one TSB12LV23, found {len(matches)}")

dev = matches[0]
if dev.get("slot") != 0x0a or dev.get("function") != 0:
    raise SystemExit(
        f"TSB12LV23 is at {dev.get('slot')}:{dev.get('function')}, expected 10:0"
    )

regions = dev.get("regions", [])
bar_sizes = {region.get("size") for region in regions if isinstance(region, dict)}
for size in (0x800, 0x4000):
    if size not in bar_sizes:
        raise SystemExit(
            f"TSB12LV23 missing {size:#x}-byte BAR; live sizes={sorted(bar_sizes)}"
        )

print("PowerMac3,1 live TSB12LV23 PCI topology: verified")
