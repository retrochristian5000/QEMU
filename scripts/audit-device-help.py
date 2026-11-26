#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Report missing descriptions from a configured QEMU device inventory."""

import argparse
import pathlib
import re
import subprocess
import sys

DEVICE = re.compile(r'^name "([^"]+)"(?:,|$)')
DESCRIPTION = re.compile(r', desc "([^"]*)"(?=,|$)')


def scan_inventory(output):
    devices = {}
    category = "Uncategorized"
    for line in output.splitlines():
        line = line.strip()
        if line.endswith(" devices:"):
            category = line[:-len(" devices:")]
            continue
        match = DEVICE.match(line)
        if not match:
            continue
        name = match.group(1)
        desc = DESCRIPTION.search(line)
        if name not in devices:
            devices[name] = (desc.group(1).strip() if desc else "", category)
    if not devices:
        raise ValueError("No QEMU device entries found in help output")
    return devices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--binary", type=pathlib.Path,
                        help="locally built QEMU system executable")
    source.add_argument("--input", type=pathlib.Path,
                        help="previously captured -device help output")
    parser.add_argument("--strict", action="store_true",
                        help="return failure if any descriptions are missing")
    args = parser.parse_args()

    try:
        if args.binary:
            result = subprocess.run(
                [str(args.binary.resolve()), "-device", "help"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                timeout=60, check=True,
            )
            output = result.stdout
        else:
            output = args.input.read_text(encoding="utf-8")
        devices = scan_inventory(output)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"error: unable to audit device help: {exc}", file=sys.stderr)
        return 2

    missing = [(name, category) for name, (desc, category) in devices.items()
               if not desc]
    print(f"Unique devices: {len(devices)}")
    print(f"Descriptions present: {len(devices) - len(missing)}")
    print(f"Descriptions missing: {len(missing)}")
    for name, category in sorted(missing, key=lambda item: (item[1], item[0])):
        print(f"{category}: {name}")
    return int(args.strict and bool(missing))


if __name__ == "__main__":
    sys.exit(main())
