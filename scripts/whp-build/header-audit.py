#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit a selected QEMU dependency's headers and link interface.

This is a post-bootstrap diagnostic, not a replacement for Meson's feature-
conditional dependency graph or the native compiler/SDK seed checks.
"""

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


PACKAGE_NAME = re.compile(r"^[A-Za-z0-9_.+-]+$")
HEADER_NAME = re.compile(r"^[A-Za-z0-9_./+-]+$")
SYMBOL_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class AuditError(Exception):
    pass


def command(value, label):
    """Preserve an executable pathname with spaces or parse a command line."""
    if not value:
        raise AuditError(f"{label} selection is empty")
    if os.path.isfile(value) and os.access(value, os.X_OK):
        return [value]
    try:
        parts = shlex.split(value)
    except ValueError as exc:
        raise AuditError(f"invalid {label} selection: {exc}") from exc
    if not parts:
        raise AuditError(f"{label} selection is empty")
    return parts


def run(argv, stage):
    try:
        result = subprocess.run(argv, capture_output=True, text=True, check=False)
    except OSError as exc:
        raise AuditError(f"{stage}: cannot execute {argv[0]}: {exc}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise AuditError(f"{stage}: exited {result.returncode}"
                         + (f"\n{detail}" if detail else ""))
    return result.stdout.strip()


def flags(value, label):
    try:
        return shlex.split(value)
    except ValueError as exc:
        raise AuditError(f"{label} has invalid quoting: {exc}") from exc


def audit(args):
    if not PACKAGE_NAME.fullmatch(args.package):
        raise AuditError("package must be one pkg-config module name")
    if (not HEADER_NAME.fullmatch(args.header)
            or ".." in args.header.split("/")):
        raise AuditError("header must be a safe relative include path")
    if args.function and not SYMBOL_NAME.fullmatch(args.function):
        raise AuditError("function must be a C identifier")

    pkg = command(args.pkg_config, "pkg-config")
    cc = command(args.cc, "C compiler")
    ver_arg = [f"--atleast-version={args.min_version}"] if args.min_version else []
    run([*pkg, *ver_arg, "--exists", args.package], "pkg-config discovery/version")
    version = run([*pkg, "--modversion", args.package], "pkg-config version")
    cflags = flags(run([*pkg, "--cflags", args.package], "pkg-config C flags"),
                   "pkg-config C flags")
    libflags = flags(run([*pkg, "--libs", args.package], "pkg-config linker flags"),
                     "pkg-config linker flags")
    if args.static:
        libflags = flags(run([*pkg, "--static", "--libs", args.package],
                             "pkg-config static linker flags"),
                         "pkg-config static linker flags")

    # The caller supplies the artifact compiler, not CC_FOR_BUILD. Respect
    # effective flags rather than pretending a seed compiler proves QEMU's ABI.
    compile_flags = flags(os.environ.get("CPPFLAGS", ""), "CPPFLAGS")
    compile_flags += flags(os.environ.get("CFLAGS", ""), "CFLAGS")
    link_flags = flags(os.environ.get("LDFLAGS", ""), "LDFLAGS")
    sysroot = ["-isysroot", args.sdkroot] if sys.platform == "darwin" and args.sdkroot else []

    # Optional zero-argument function check forces a library reference.
    # Without it, link flags are checked but no particular symbol is proven.
    body = (f"int main(void) {{ return {args.function}() == 0; }}\n"
            if args.function else "int main(void) { return 0; }\n")
    source_text = f"#include <{args.header}>\n" + body
    with tempfile.TemporaryDirectory(prefix="whp-qemu-header-") as temp:
        base = Path(temp)
        source = base / "probe.c"
        obj = base / "probe.o"
        output = base / "probe"
        source.write_text(source_text, encoding="utf-8")
        run([*cc, *sysroot, *compile_flags, *cflags, "-c", str(source),
             "-o", str(obj)], "header compile")
        run([*cc, *sysroot, str(obj), "-o", str(output), *link_flags,
             *libflags], "dependency link")

    print(f"PASS header dependency: {args.package} {version}; "
          f"{args.header}; compiler={cc[0]}; "
          f"symbol={'checked' if args.function else 'not requested'}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, help="pkg-config module")
    parser.add_argument("--header", required=True, help="C header relative to an include root")
    parser.add_argument("--function", help="zero-argument function to reference at link time")
    parser.add_argument("--min-version", help="pkg-config minimum module version")
    parser.add_argument("--static", action="store_true", help="use static pkg-config link flags")
    parser.add_argument("--cc", default=os.environ.get("CC", "cc"),
                        help="QEMU artifact compiler or command (default: CC)")
    parser.add_argument("--pkg-config", default=os.environ.get("PKG_CONFIG", "pkg-config"),
                        help="selected pkg-config executable (default: PKG_CONFIG)")
    parser.add_argument("--sdkroot", default=os.environ.get("SDKROOT", ""),
                        help="selected macOS SDK path")
    args = parser.parse_args(argv)
    try:
        audit(args)
    except AuditError as exc:
        print(f"FAIL header dependency {args.package} ({args.header}): {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
