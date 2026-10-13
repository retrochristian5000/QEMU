#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import os
import pathlib
import re
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
_TARGET_CPU_QUOTED_RE = re.compile(r'"-target-cpu"\s+"([A-Za-z0-9_.+-]+)"')
_TARGET_CPU_PLAIN_RE = re.compile(
    r'(?:^|\s)-target-cpu\s+([A-Za-z0-9_.+-]+)', re.MULTILINE
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


def compiler_accepts(command: str, language: str, flags: Sequence[str],
                     target_flags: Sequence[str] = ()) -> bool:
    cmd = _command(command)
    with tempfile.TemporaryDirectory(prefix='whp-host-cpu-') as td:
        source = pathlib.Path(td) / 'probe.c'
        output = pathlib.Path(td) / 'probe.o'
        source.write_text('int main(void) { return 0; }\n', encoding='utf-8')
        result = subprocess.run(
            [*cmd, *target_flags, *flags, '-x', language, '-c', str(source), '-o', str(output)],
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
    target_flags: Sequence[str] = (),
) -> bool:
    if not compiler_accepts(cc, 'c', flags, target_flags):
        return False
    if not compiler_accepts(cxx, 'c++', flags, target_flags):
        return False
    if objc and not compiler_accepts(objc, 'objective-c', flags, target_flags):
        return False
    return True


def compiler_native_cpu(command: str, language: str = 'c',
                        target_flags: Sequence[str] = ()) -> Optional[str]:
    """Return Clang's concrete host CPU name without enabling it for codegen."""
    cmd = _command(command)
    result = subprocess.run(
        [
            *cmd,
            *target_flags,
            '-mcpu=native',
            '-###',
            '-x',
            language,
            '-c',
            '-',
            '-o',
            os.devnull,
        ],
        input='int whp_native_cpu_probe(void) { return 0; }\n',
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    output = f'{result.stderr}\n{result.stdout}'
    match = _TARGET_CPU_QUOTED_RE.search(output)
    if match is None:
        match = _TARGET_CPU_PLAIN_RE.search(output)
    if match is None:
        return None
    return match.group(1)


def native_candidates(host_arch: str) -> Tuple[Tuple[str, ...], ...]:
    arch = host_arch.lower()
    if arch in ('arm64', 'aarch64'):
        # Keep native ARM64 builds on the portable ISA baseline.  -mcpu=native
        # enables host ISA extensions, while -mtune only changes scheduling and
        # cost modelling.  A concrete tune CPU is substituted earlier when the
        # active Clang exposes one through -mcpu=native -###.
        return (('-mtune=native',),)
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
    target_flags: Sequence[str] = (),
) -> List[str]:
    requested = value.strip()
    if requested == 'portable':
        return []
    if requested == 'native':
        arch = host_arch.lower()
        if arch in ('arm64', 'aarch64'):
            native_cpu = compiler_native_cpu(cc, target_flags=target_flags)
            if native_cpu:
                concrete_tune = (f'-mtune={native_cpu}',)
                if compilers_accept(concrete_tune, cc, cxx, objc, target_flags):
                    return list(concrete_tune)
        for candidate in native_candidates(host_arch):
            if compilers_accept(candidate, cc, cxx, objc, target_flags):
                return list(candidate)
        return []

    flags = parse_custom_flags(requested)
    if not compilers_accept(flags, cc, cxx, objc, target_flags):
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
    parser.add_argument('--target-flag', action='append', default=[],
                        help='one managed target/SDK flag per occurrence')
    args = parser.parse_args(argv)
    # Never allow arbitrary compiler overrides through the managed target-flag
    # channel. Each macOS build has one selected arch, SDK and deployment target.
    target = args.target_flag
    if target and not (
        len(target) == 5
        and target[0] == '-arch'
        and target[1] in ('arm64', 'arm64e', 'x86_64')
        and target[2] == '-isysroot'
        and bool(target[3])
        and re.fullmatch(r'-mmacosx-version-min=[0-9]+(?:\.[0-9]+){1,2}',
                         target[4])
    ):
        parser.error('invalid managed Darwin target flags')
    try:
        flags = resolve_cpu_tuning(
            args.value, args.host_arch, args.cc, args.cxx, args.objc,
            args.target_flag
        )
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(' '.join(flags))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
