#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import pathlib
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Sequence, Tuple

_ALLOWED_PREFIXES = ('-march=', '-mcpu=', '-mtune=')
_ALLOWED_VALUE_CHARS = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.,+:/=-'
)


def parse_custom_flags(value: str) -> List[str]:
    try:
        flags = shlex.split(value)
    except ValueError as exc:
        raise ValueError(f'invalid QEMU host CPU tuning: {exc}') from exc
    if not flags:
        raise ValueError('QEMU host CPU tuning cannot be empty')
    for flag in flags:
        if not flag.startswith(_ALLOWED_PREFIXES):
            raise ValueError(
                f'unsupported QEMU host CPU tuning token: {flag}; '
                'only -march=, -mcpu=, and -mtune= are accepted'
            )
        cpu_value = flag.split('=', 1)[1]
        if not cpu_value or any(ch not in _ALLOWED_VALUE_CHARS for ch in cpu_value):
            raise ValueError(f'invalid QEMU host CPU tuning value: {cpu_value}')
    return flags


def _command(command: str) -> List[str]:
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ValueError(f'invalid compiler command {command!r}: {exc}') from exc
    if not parts:
        raise ValueError('compiler command cannot be empty')
    executable = shutil.which(parts[0])
    if executable is None and not pathlib.Path(parts[0]).is_file():
        raise ValueError(f'compiler command is unavailable: {command}')
    return parts


def compiler_accepts(command: str, language: str, flags: Sequence[str]) -> bool:
    cmd = _command(command)
    with tempfile.TemporaryDirectory(prefix='whp-host-cpu-') as td:
        source = pathlib.Path(td) / 'probe.c'
        output = pathlib.Path(td) / 'probe.o'
        source.write_text('int main(void) { return 0; }\n', encoding='utf-8')
        result = subprocess.run(
            [*cmd, *flags, '-x', language, '-c', str(source), '-o', str(output)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0


def compilers_accept(
    flags: Sequence[str],
    cc: str,
    cxx: str,
    objc: Optional[str] = None,
) -> bool:
    if not compiler_accepts(cc, 'c', flags):
        return False
    if not compiler_accepts(cxx, 'c++', flags):
        return False
    if objc and not compiler_accepts(objc, 'objective-c', flags):
        return False
    return True


def native_candidates(host_arch: str) -> Tuple[Tuple[str, ...], ...]:
    arch = host_arch.lower()
    if arch in ('arm64', 'aarch64'):
        return (
            ('-mcpu=native',),
            ('-mtune=native',),
        )
    if arch in ('x86_64', 'amd64'):
        return (
            ('-march=native', '-mtune=native'),
            ('-march=native',),
            ('-mtune=native',),
        )
    return (
        ('-mcpu=native',),
        ('-march=native', '-mtune=native'),
        ('-march=native',),
        ('-mtune=native',),
    )


def resolve_cpu_tuning(
    value: str,
    host_arch: str,
    cc: str,
    cxx: str,
    objc: Optional[str] = None,
) -> List[str]:
    requested = value.strip()
    if requested == 'portable':
        return []
    if requested == 'native':
        for candidate in native_candidates(host_arch):
            if compilers_accept(candidate, cc, cxx, objc):
                return list(candidate)
        return []

    flags = parse_custom_flags(requested)
    if not compilers_accept(flags, cc, cxx, objc):
        raise ValueError(
            f'active QEMU host compilers reject CPU tuning: {requested}'
        )
    return flags


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--value', required=True)
    parser.add_argument('--host-arch', required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--cxx', default='c++')
    parser.add_argument('--objc')
    args = parser.parse_args(argv)
    try:
        flags = resolve_cpu_tuning(
            args.value, args.host_arch, args.cc, args.cxx, args.objc
        )
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(' '.join(flags))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
