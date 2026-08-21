#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import sys
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path('toolchains/ninja-builder')
SUBMODULE_DIR = ROOT / SUBMODULE_REL
NINJA_BOOTSTRAP_SCHEMA='2'


def run_text(command: List[str], cwd: pathlib.Path | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"command failed: {' '.join(command)}{': ' + detail if detail else ''}")
    return completed.stdout.strip()


def git_checkout_available() -> bool:
    return shutil.which('git') is not None and (ROOT / '.git').exists()


def archive_source_signature() -> str:
    digest = hashlib.sha256()
    if not (SUBMODULE_DIR / 'configure.py').is_file():
        raise RuntimeError(
            f'bundled Ninja source is unavailable: {SUBMODULE_DIR}; '
            'initialize toolchains/ninja-builder or use a Git checkout'
        )
    for path in sorted(SUBMODULE_DIR.rglob('*')):
        if not path.is_file() or '.git' in path.parts or 'build' in path.parts:
            continue
        digest.update(str(path.relative_to(SUBMODULE_DIR)).encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return f'archive-{digest.hexdigest()}'


def ensure_ninja_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    expected_line = run_text(
        ['git', '-C', str(ROOT), 'ls-tree', 'HEAD', '--', str(SUBMODULE_REL)]
    )
    fields = expected_line.split()
    if len(fields) < 3 or fields[1] != 'commit':
        raise RuntimeError(f'Ninja gitlink is not registered in QEMU: {SUBMODULE_REL}')
    expected_revision = fields[2]

    current_revision = ''
    if (SUBMODULE_DIR / '.git').exists():
        try:
            current_revision = run_text(['git', '-C', str(SUBMODULE_DIR), 'rev-parse', 'HEAD'])
        except RuntimeError:
            current_revision = ''

    if current_revision != expected_revision:
        subprocess.run(
            [
                'git', '-C', str(ROOT), 'submodule', 'update', '--init', '--depth', '1',
                str(SUBMODULE_REL),
            ],
            check=True,
        )
        current_revision = run_text(['git', '-C', str(SUBMODULE_DIR), 'rev-parse', 'HEAD'])

    if current_revision != expected_revision:
        raise RuntimeError(
            'bundled Ninja checkout does not match the QEMU gitlink: '
            f'{current_revision} != {expected_revision}'
        )

    dirty = run_text(
        ['git', '-C', str(SUBMODULE_DIR), 'status', '--porcelain', '--untracked-files=no']
    )
    if dirty:
        raise RuntimeError(
            'bundled Ninja submodule has tracked changes; commit them in the Ninja fork '
            'and update the QEMU gitlink'
        )
    return expected_revision


def select_host_cxx() -> str:
    requested = os.environ.get('CXX_FOR_BUILD') or os.environ.get('CXX')
    if requested:
        return requested

    if platform.system() == 'Darwin' and shutil.which('xcrun'):
        candidate = run_text(['xcrun', '--sdk', 'macosx', '--find', 'clang++'])
        if candidate:
            return candidate

    for name in ('c++', 'clang++', 'g++'):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError('a host C++17 compiler is required to bootstrap bundled Ninja')


def compiler_version(command: str) -> str:
    argv = shlex.split(command)
    if not argv:
        raise RuntimeError('empty host C++ compiler command')
    executable = shutil.which(argv[0]) if not pathlib.Path(argv[0]).is_absolute() else argv[0]
    if not executable or not pathlib.Path(executable).exists():
        raise RuntimeError(f'host C++ compiler is not executable: {argv[0]}')
    completed = subprocess.run(
        [*argv, '--version'],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    first = completed.stdout.splitlines()[0] if completed.stdout else ''
    if completed.returncode != 0 or not first:
        raise RuntimeError(f'could not identify host C++ compiler: {command}')
    return first


def marker_text(revision: str, cxx: str, cxx_version: str) -> str:
    return (
        f'NINJA_BOOTSTRAP_SCHEMA={NINJA_BOOTSTRAP_SCHEMA}\n'
        f'SOURCE_DIR={ROOT}\n'
        f'NINJA_GIT_COMMIT={revision}\n'
        f'HOST_SYSTEM={platform.system()}\n'
        f'HOST_MACHINE={platform.machine()}\n'
        f'PYTHON={pathlib.Path(sys.executable).resolve()}\n'
        f'CXX={cxx}\n'
        f'CXX_VERSION={cxx_version}\n'
    )


def ninja_binary(directory: pathlib.Path) -> pathlib.Path:
    for name in ('ninja', 'ninja.exe'):
        candidate = directory / name
        if candidate.is_file():
            return candidate
    return directory / ('ninja.exe' if os.name == 'nt' else 'ninja')


def binary_is_usable(path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    try:
        completed = subprocess.run(
            [str(path), '--version'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return False
    return completed.returncode == 0


def atomic_install(staging: pathlib.Path, final: pathlib.Path) -> None:
    backup = final.with_name(final.name + f'.old.{os.getpid()}')
    shutil.rmtree(backup, ignore_errors=True)
    if final.exists():
        final.rename(backup)
    try:
        staging.rename(final)
    except Exception:
        if not final.exists() and backup.exists():
            backup.rename(final)
        raise
    shutil.rmtree(backup, ignore_errors=True)


def copy_ninja_source(destination: pathlib.Path) -> None:
    # configure.py can regenerate lexer/parser sources when re2c is installed.
    # Build from an isolated source copy so optional host tools can never dirty
    # the pinned Ninja submodule.
    shutil.copytree(
        SUBMODULE_DIR,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns('.git', 'build', 'build.ninja', 'ninja', 'ninja.exe'),
    )


def ensure_bundled_ninja(qemu_build_dir: pathlib.Path) -> pathlib.Path:
    revision = ensure_ninja_source()
    cxx = select_host_cxx()
    cxx_version = compiler_version(cxx)
    expected_marker = marker_text(revision, cxx, cxx_version)

    host_tag = f'{platform.system().lower()}-{platform.machine().lower()}'
    host_tools_root = qemu_build_dir.parent / '.whp-host-tools'
    final_dir = host_tools_root / f'ninja-{host_tag}'
    marker = final_dir / '.whp-ninja-tool'
    binary = ninja_binary(final_dir)

    if marker.is_file() and marker.read_text(encoding='utf-8') == expected_marker and binary_is_usable(binary):
        print(f'Reused bundled Ninja: {binary}', file=sys.stderr)
        return binary.resolve()

    host_tools_root.mkdir(parents=True, exist_ok=True)
    staging = host_tools_root / f'{final_dir.name}.new.{os.getpid()}'
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    staged_source = staging / 'source'
    bootstrap_dir = staging / 'bootstrap'
    copy_ninja_source(staged_source)
    bootstrap_dir.mkdir()

    bootstrap_env = os.environ.copy()
    for key in ('CC', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'AR'):
        bootstrap_env.pop(key, None)
    bootstrap_env['CXX'] = cxx
    if os.environ.get('AR_FOR_BUILD'):
        bootstrap_env['AR'] = os.environ['AR_FOR_BUILD']

    print(
        f'Bootstrapping bundled Ninja {revision[:12]} with {cxx_version}',
        file=sys.stderr,
    )
    try:
        subprocess.run(
            [sys.executable, str(staged_source / 'configure.py'), '--bootstrap'],
            cwd=bootstrap_dir,
            env=bootstrap_env,
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=True,
        )
        staged_binary = ninja_binary(bootstrap_dir)
        if not binary_is_usable(staged_binary):
            raise RuntimeError(f'bundled Ninja bootstrap did not produce a usable binary: {staged_binary}')
        published_binary = staging / staged_binary.name
        shutil.copy2(staged_binary, published_binary)
        if not binary_is_usable(published_binary):
            raise RuntimeError(f'copied bundled Ninja binary is unusable: {published_binary}')
        shutil.rmtree(staged_source)
        shutil.rmtree(bootstrap_dir)
        (staging / '.whp-ninja-tool').write_text(expected_marker, encoding='utf-8')
        atomic_install(staging, final_dir)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    binary = ninja_binary(final_dir)
    print(f'Bundled Ninja ready: {binary}', file=sys.stderr)
    return binary.resolve()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--build-dir', required=True)
    args = parser.parse_args()

    try:
        path = ensure_bundled_ninja(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f'error: bundled Ninja bootstrap failed: {exc}', file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
