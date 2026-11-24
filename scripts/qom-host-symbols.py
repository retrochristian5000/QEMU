#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Generate the private Mach-O QOM-to-host symbol contract."""

import argparse
from pathlib import Path
import re
import subprocess


def read_symbols(nm, archive):
    """Return external definitions and strong undefined Mach-O symbols."""
    result = subprocess.run(
        [nm, "-P", "-g", archive], check=True, stdout=subprocess.PIPE
    )
    defined = set()
    undefined = set()
    for line in result.stdout.decode("utf-8").splitlines():
        fields = line.split()
        if len(fields) < 2 or len(fields[1]) != 1:
            continue
        name, kind = fields[:2]
        if not re.fullmatch(r"_[A-Za-z0-9_.$]+", name):
            continue
        if kind == "U":
            undefined.add(name)
        elif kind.isupper():
            defined.add(name)
    return defined, undefined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nm")
    parser.add_argument("host_archive")
    parser.add_argument("qom_archive")
    parser.add_argument("allow", type=Path)
    parser.add_argument("require", type=Path)
    parser.add_argument("relink", type=Path)
    args = parser.parse_args()

    host_defined, _ = read_symbols(args.nm, args.host_archive)
    qom_defined, qom_undefined = read_symbols(args.nm, args.qom_archive)
    symbols = sorted(host_defined & (qom_undefined - qom_defined))
    if "_register_module_init" not in symbols:
        parser.error("QOM host symbol contract lacks register_module_init; "
                     "check Mach-O nm output and archive contents")

    args.allow.write_text(
        "".join(f"-Wl,-U,{name}\n" for name in symbols), encoding="utf-8"
    )
    args.require.write_text(
        "".join(f"-Wl,-u,{name}\n" for name in symbols), encoding="utf-8"
    )
    # A generated compilation input makes Ninja relink QOM consumers if the
    # required host symbol set changes without a change in QOM's exports.
    args.relink.write_text(
        "/* Generated QOM host symbol contract; do not edit.\n"
        + "".join(f" * {name}\n" for name in symbols)
        + " */\ntypedef int QomHostLinkContract;\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
