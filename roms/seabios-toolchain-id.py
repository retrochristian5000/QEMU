#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fingerprint the tools used by SeaBIOS without hashing large LLVM binaries."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys


def identify_file(path):
    try:
        resolved = path.resolve(strict=True)
        info = resolved.stat()
    except FileNotFoundError:
        return None

    identity = [str(resolved), info.st_dev, info.st_ino, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns, info.st_mode]
    # Hash small wrappers and revision markers; use metadata for large tools.
    # Avoid reading hundreds of megabytes of compiler data on every build.
    if resolved.is_file() and info.st_size <= 128 * 1024:
        identity.append(hashlib.sha256(resolved.read_bytes()).hexdigest())
    return identity


def fingerprint(cross_prefix, hostcc):
    compiler = cross_prefix + 'gcc' if cross_prefix else 'cc'
    tools = [compiler, *(cross_prefix + name for name in
                        ('cpp', 'as', 'ld', 'objcopy', 'objdump', 'strip'))]
    tools.extend(shlex.split(hostcc)[:1])
    identities = {}
    for tool in tools:
        selected = shutil.which(tool)
        if selected is None:
            identities[tool] = None
            continue
        # Preserve the invocation path: llvm-strip and llvm-objcopy can be
        # aliases of the same executable with different argv[0] semantics.
        path = Path(os.path.abspath(selected))
        identities[tool] = [str(path), identify_file(path)]
        prefix = path.parent.parent
        marker = prefix / '.whp-i386-toolchain'
        if marker.is_file():
            for dependency in (
                marker,
                prefix / 'libexec' / 'seabios-llvm-objdump.py',
                *(prefix / 'llvm' / 'bin' / name for name in
                  ('clang', 'ld.lld', 'llvm-objcopy', 'llvm-objdump',
                   'llvm-strip')),
                prefix / 'llvm' / '.whp-native-llvm',
            ):
                identities[str(dependency)] = identify_file(dependency)

    encoded = json.dumps(identities, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit('usage: seabios-toolchain-id.py CROSS_PREFIX HOSTCC')
    print(fingerprint(sys.argv[1], sys.argv[2]))
