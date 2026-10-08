#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Prepare Clang's host-only QEMU PGO input without touching source or firmware."""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile


def profile_tool(compiler: str) -> list[str]:
    explicit = os.environ.get('LLVM_PROFDATA')
    if explicit is not None:
        selected = shlex.split(explicit)
        if not selected or not shutil.which(selected[0]):
            raise RuntimeError('LLVM_PROFDATA does not name an available executable')
        return selected

    tokens = shlex.split(compiler)
    command = tokens[0] if tokens else 'clang'
    if pathlib.Path(command).name in ('ccache', 'sccache') and len(tokens) > 1:
        command = tokens[1]
    resolved = shutil.which(command)
    version = re.search(r'-(\d+), pathlib.Path(command).name)
    names = ([f'llvm-profdata-{version.group(1)}'] if version else []) + ['llvm-profdata']
    if resolved:
        for name in names:
            local = pathlib.Path(resolved).parent / name
            if local.is_file() and os.access(local, os.X_OK):
                return [str(local)]
    for name in names:
        found = shutil.which(name)
        if found:
            return [found]
    if platform.system() == 'Darwin' and shutil.which('xcrun'):
        probe = subprocess.run(
            ['xcrun', '--find', 'llvm-profdata'], capture_output=True, text=True,
            check=False,
        )
        if probe.returncode == 0 and pathlib.Path(probe.stdout.strip()).is_file():
            return [probe.stdout.strip()]
    raise RuntimeError(
        'Clang PGO needs llvm-profdata to merge raw profiles. '
        'Select the matching LLVM tool with LLVM_PROFDATA or install it.'
    )


def prepare_use(build_dir: pathlib.Path, compiler: str) -> str:
    if not build_dir.is_dir():
        raise RuntimeError(f'QEMU build directory does not exist: {build_dir}')
    profile = build_dir / 'default.profdata'
    raw_dir = build_dir / 'pgo-raw'
    raw = sorted(p for p in raw_dir.glob('*.profraw') if p.is_file() and p.stat().st_size)
    existing = profile.is_file() and profile.stat().st_size > 0

    if existing and (not raw or max(p.stat().st_mtime_ns for p in raw) <= profile.stat().st_mtime_ns):
        return f'QEMU PGO: using existing indexed profile: {profile}'
    if not raw:
        raise RuntimeError(
            'QEMU_HOST_PGO=use requires actual training data. No nonempty '
            f'{profile} or {raw_dir}/*.profraw found. First build with '
            'QEMU_HOST_PGO=generate, run representative TCG workloads with '
            'LLVM_PROFILE_FILE set to the pgo-raw directory, then select use.'
        )

    tool = profile_tool(compiler)
    # Generate to a temporary path: never replace an existing known-good
    # profile with a partial or failed merge.
    with tempfile.TemporaryDirectory(prefix='.whp-pgo-', dir=build_dir) as tmp:
        candidate = pathlib.Path(tmp) / 'default.profdata'
        subprocess.run([*tool, 'merge', '--failure-mode=any',
                        f'-output={candidate}', *(str(path) for path in raw)],
                       check=True)
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise RuntimeError('llvm-profdata did not produce a nonempty indexed profile')
        subprocess.run([*tool, 'show', str(candidate)], check=True,
                       stdout=subprocess.DEVNULL)
        os.replace(candidate, profile)
    return f'QEMU PGO: merged {len(raw)} raw profiles into {profile}'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True, type=pathlib.Path)
    parser.add_argument('--compiler', default='clang')
    args = parser.parse_args()
    try:
        print(prepare_use(args.build_dir, args.compiler))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'error: PGO profile preparation failed: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
, pathlib.Path(command).name)
    names = ([f'llvm-profdata-{version.group(1)}'] if version else []) + ['llvm-profdata']
    if resolved:
        for name in names:
            local = pathlib.Path(resolved).parent / name
            if local.is_file() and os.access(local, os.X_OK):
                return [str(local)]
    for name in names:
        found = shutil.which(name)
        if found:
            return [found]
    if platform.system() == 'Darwin' and shutil.which('xcrun'):
        probe = subprocess.run(
            ['xcrun', '--find', 'llvm-profdata'], capture_output=True, text=True,
            check=False,
        )
        if probe.returncode == 0 and pathlib.Path(probe.stdout.strip()).is_file():
            return [probe.stdout.strip()]
    raise RuntimeError(
        'Clang PGO needs llvm-profdata to merge raw profiles. '
        'Select the matching LLVM tool with LLVM_PROFDATA or install it.'
    )


def prepare_use(build_dir: pathlib.Path, compiler: str) -> str:
    if not build_dir.is_dir():
        raise RuntimeError(f'QEMU build directory does not exist: {build_dir}')
    profile = build_dir / 'default.profdata'
    raw_dir = build_dir / 'pgo-raw'
    raw = sorted(p for p in raw_dir.glob('*.profraw') if p.is_file() and p.stat().st_size)
    existing = profile.is_file() and profile.stat().st_size > 0

    if existing and (not raw or max(p.stat().st_mtime_ns for p in raw) <= profile.stat().st_mtime_ns):
        return f'QEMU PGO: using existing indexed profile: {profile}'
    if not raw:
        raise RuntimeError(
            'QEMU_HOST_PGO=use requires actual training data. No nonempty '
            f'{profile} or {raw_dir}/*.profraw found. First build with '
            'QEMU_HOST_PGO=generate, run representative TCG workloads with '
            'LLVM_PROFILE_FILE set to the pgo-raw directory, then select use.'
        )

    tool = profile_tool(compiler)
    # Generate to a temporary path: never replace an existing known-good
    # profile with a partial or failed merge.
    with tempfile.TemporaryDirectory(prefix='.whp-pgo-', dir=build_dir) as tmp:
        candidate = pathlib.Path(tmp) / 'default.profdata'
        subprocess.run([*tool, 'merge', '--failure-mode=any',
                        f'-output={candidate}', *(str(path) for path in raw)],
                       check=True)
        if not candidate.is_file() or candidate.stat().st_size == 0:
            raise RuntimeError('llvm-profdata did not produce a nonempty indexed profile')
        subprocess.run([*tool, 'show', str(candidate)], check=True,
                       stdout=subprocess.DEVNULL)
        os.replace(candidate, profile)
    return f'QEMU PGO: merged {len(raw)} raw profiles into {profile}'


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True, type=pathlib.Path)
    parser.add_argument('--compiler', default='clang')
    args = parser.parse_args()
    try:
        print(prepare_use(args.build_dir, args.compiler))
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'error: PGO profile preparation failed: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
