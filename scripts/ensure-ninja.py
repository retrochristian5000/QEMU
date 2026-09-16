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
import tempfile
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path('toolchains/ninja-builder')
SUBMODULE_DIR = ROOT / SUBMODULE_REL
NINJA_BOOTSTRAP_SCHEMA='5'


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
            stdout=sys.stderr,
            stderr=sys.stderr,
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
    requested = os.environ.get('CXX_FOR_BUILD')
    if requested:
        return requested

    # Ninja executes on the build machine, so on macOS it must not inherit
    # QEMU's target CXX. A self-built Clang targeting aarch64-apple-darwin does
    # not necessarily carry an Apple SDK sysroot and can fail through libc++
    # with headers such as <errno.h> missing. Prefer the SDK compiler for the
    # build-machine role unless CXX_FOR_BUILD explicitly overrides it.
    if platform.system() == 'Darwin' and shutil.which('xcrun'):
        candidate = run_text(['xcrun', '--sdk', 'macosx', '--find', 'clang++'])
        if candidate:
            return candidate

    requested = os.environ.get('CXX')
    if requested:
        return requested

    for name in ('c++', 'clang++', 'g++'):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError('a host C++17 compiler is required to bootstrap bundled Ninja')


def select_host_sdkroot() -> str:
    if platform.system() != 'Darwin':
        return ''
    if not shutil.which('xcrun'):
        raise RuntimeError('xcrun is required to locate the macOS SDK for bundled Ninja')
    sdkroot = run_text(['xcrun', '--sdk', 'macosx', '--show-sdk-path'])
    if not sdkroot:
        raise RuntimeError('xcrun did not return a macOS SDK path for bundled Ninja')
    return sdkroot


def compiler_supports_macos_arch(cxx: str, sdkroot: str, arch: str) -> bool:
    argv = shlex.split(cxx)
    if not argv or platform.system() != 'Darwin' or not sdkroot:
        return False

    with tempfile.TemporaryDirectory(prefix='whp-ninja-arch-') as tmp:
        output = pathlib.Path(tmp) / 'probe'
        completed = subprocess.run(
            [
                *argv,
                '-arch', arch,
                '-isysroot', sdkroot,
                '-x', 'c++', '-',
                '-o', str(output),
            ],
            input='int main() { return 0; }\n',
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0 and output.is_file()


def select_host_macos_arch(cxx: str, sdkroot: str) -> str:
    if platform.system() != 'Darwin':
        return ''

    requested = os.environ.get('NINJA_MACOS_ARCH', 'auto')
    if requested not in ('auto', 'arm64', 'arm64e', 'x86_64'):
        raise RuntimeError(
            'NINJA_MACOS_ARCH must be auto, arm64, arm64e, or x86_64: '
            f'{requested}'
        )

    machine = platform.machine().lower()
    if machine in ('arm64', 'aarch64'):
        if requested == 'auto':
            if compiler_supports_macos_arch(cxx, sdkroot, 'arm64e'):
                return 'arm64e'
            return 'arm64'
        if requested == 'arm64':
            return 'arm64'
        if requested == 'arm64e':
            if not compiler_supports_macos_arch(cxx, sdkroot, 'arm64e'):
                raise RuntimeError(
                    'requested Ninja arm64e bootstrap is unsupported by the '
                    'selected compiler and macOS SDK'
                )
            return 'arm64e'
        raise RuntimeError(
            f'requested Ninja macOS architecture is not native to Apple Silicon: {requested}'
        )

    if machine in ('x86_64', 'amd64'):
        if requested in ('auto', 'x86_64'):
            return 'x86_64'
        raise RuntimeError(
            f'requested Ninja macOS architecture is not native to x86_64: {requested}'
        )

    raise RuntimeError(f'unsupported macOS host architecture for Ninja bootstrap: {machine}')


def select_compiler_cache() -> str:
    explicit = os.environ.get('WHP_COMPILER_CACHE_CMD', '')
    if explicit:
        argv = shlex.split(explicit)
        if len(argv) != 1:
            raise RuntimeError('WHP_COMPILER_CACHE_CMD must name exactly one executable')
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if not path or not pathlib.Path(path).exists():
            raise RuntimeError(f'compiler cache is not executable: {candidate}')
        if pathlib.Path(path).name not in ('ccache', 'sccache'):
            raise RuntimeError(f'unsupported compiler cache command: {path}')
        return str(path)

    policy = os.environ.get('COMPILER_CACHE', 'auto')
    if policy not in ('auto', 'ccache', 'sccache', 'none'):
        raise RuntimeError(
            f'COMPILER_CACHE must be auto, ccache, sccache, or none: {policy}'
        )
    if policy == 'none':
        return ''

    names = ('ccache', 'sccache') if policy == 'auto' else (policy,)
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    if policy != 'auto':
        raise RuntimeError(f'requested compiler cache is not installed: {policy}')
    return ''


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


def marker_text(
    revision: str,
    cxx: str,
    cxx_version: str,
    sdkroot: str,
    macos_arch: str = '',
) -> str:
    return (
        f'NINJA_BOOTSTRAP_SCHEMA={NINJA_BOOTSTRAP_SCHEMA}\n'
        f'SOURCE_DIR={ROOT}\n'
        f'NINJA_GIT_COMMIT={revision}\n'
        f'HOST_SYSTEM={platform.system()}\n'
        f'HOST_MACHINE={platform.machine()}\n'
        f'PYTHON={pathlib.Path(sys.executable).resolve()}\n'
        f'CXX={cxx}\n'
        f'CXX_VERSION={cxx_version}\n'
        f'SDKROOT={sdkroot}\n'
        f'NINJA_MACOS_ARCH={macos_arch}\n'
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


def binary_has_macos_arch(path: pathlib.Path, arch: str) -> bool:
    if platform.system() != 'Darwin' or not arch:
        return True
    lipo = shutil.which('lipo')
    if not lipo:
        return False
    completed = subprocess.run(
        [lipo, '-archs', str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0 and arch in completed.stdout.split()


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


def bootstrap_environment(
    cxx: str,
    sdkroot: str,
    compiler_cache: str = '',
    compiler_cache_dir: pathlib.Path | None = None,
    macos_arch: str = '',
) -> dict[str, str]:
    bootstrap_env = os.environ.copy()
    # Ninja is a host build helper. Do not let ambient target/search-path state
    # choose headers, libraries, architectures, or CMake/pkg-config prefixes
    # before the platform wrapper has a chance to sanitize the main QEMU build.
    # Explicit host compiler, SDK, cache and archive-tool inputs are restored
    # below after this isolation boundary.
    for key in (
        'CC', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'AR', 'SDKROOT',
        'CCACHE_DIR', 'SCCACHE_DIR',
        'CPATH', 'C_INCLUDE_PATH', 'CPLUS_INCLUDE_PATH', 'OBJC_INCLUDE_PATH',
        'COMPILER_PATH', 'GCC_EXEC_PREFIX', 'LIBRARY_PATH',
        'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH',
        'DYLD_INSERT_LIBRARIES', 'CMAKE_PREFIX_PATH', 'CMAKE_LIBRARY_PATH',
        'CMAKE_INCLUDE_PATH', 'PKG_CONFIG_PATH', 'PKG_CONFIG_LIBDIR',
        'PKG_CONFIG_SYSROOT_DIR', 'ACLOCAL_PATH', 'ARCHFLAGS',
    ):
        bootstrap_env.pop(key, None)

    bootstrap_env['CXX'] = cxx
    if compiler_cache:
        cache_name = pathlib.Path(compiler_cache).name
        if cache_name not in ('ccache', 'sccache'):
            raise RuntimeError(f'unsupported compiler cache command: {compiler_cache}')
        bootstrap_env['CXX'] = f'{shlex.quote(compiler_cache)} {cxx}'
        if compiler_cache_dir is not None:
            if cache_name == 'ccache':
                bootstrap_env['CCACHE_DIR'] = str(compiler_cache_dir)
            else:
                bootstrap_env['SCCACHE_DIR'] = str(compiler_cache_dir)

    if sdkroot:
        flags = []
        if platform.system() == 'Darwin' and macos_arch:
            flags.extend(('-arch', macos_arch))
        flags.extend(('-isysroot', shlex.quote(sdkroot)))
        common_flags = ' '.join(flags)
        bootstrap_env['SDKROOT'] = sdkroot
        bootstrap_env['CXXFLAGS'] = common_flags
        link_flags = common_flags
        if platform.system() == 'Darwin':
            # Ninja is a build helper, not a QEMU deliverable. Optimize and
            # dead-strip the helper itself without leaking these flags into
            # QEMU, firmware, or cross-toolchain link commands.
            link_flags += ' -Wl,-O2 -Wl,-dead_strip'
        bootstrap_env['LDFLAGS'] = link_flags
    if os.environ.get('AR_FOR_BUILD'):
        bootstrap_env['AR'] = os.environ['AR_FOR_BUILD']
    return bootstrap_env


def ensure_bundled_ninja(qemu_build_dir: pathlib.Path) -> pathlib.Path:
    revision = ensure_ninja_source()
    cxx = select_host_cxx()
    sdkroot = select_host_sdkroot()
    macos_arch = select_host_macos_arch(cxx, sdkroot)
    compiler_cache = select_compiler_cache()
    cxx_version = compiler_version(cxx)
    expected_marker = marker_text(revision, cxx, cxx_version, sdkroot, macos_arch)

    host_tag = f'{platform.system().lower()}-{platform.machine().lower()}'
    host_tools_root = qemu_build_dir.parent / '.whp-host-tools'
    final_dir = host_tools_root / f'ninja-{host_tag}'
    marker = final_dir / '.whp-ninja-tool'
    binary = ninja_binary(final_dir)

    if (
        marker.is_file()
        and marker.read_text(encoding='utf-8') == expected_marker
        and binary_is_usable(binary)
        and binary_has_macos_arch(binary, macos_arch)
    ):
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

    compiler_cache_dir = None
    if compiler_cache:
        cache_name = pathlib.Path(compiler_cache).name
        compiler_cache_dir = (
            qemu_build_dir.parent / '.whp-compiler-cache' / f'{cache_name}-{host_tag}'
        )
        compiler_cache_dir.mkdir(parents=True, exist_ok=True)
    bootstrap_env = bootstrap_environment(
        cxx,
        sdkroot,
        compiler_cache,
        compiler_cache_dir,
        macos_arch,
    )

    print(
        f'Bootstrapping bundled Ninja {revision[:12]} with {cxx_version}',
        file=sys.stderr,
    )
    if sdkroot:
        print(f'Bundled Ninja macOS SDK: {sdkroot}', file=sys.stderr)
    if macos_arch:
        print(f'Bundled Ninja macOS arch: {macos_arch}', file=sys.stderr)
    if compiler_cache and compiler_cache_dir is not None:
        print(
            f'Bundled Ninja compiler cache: {compiler_cache} ({compiler_cache_dir})',
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
        if not binary_has_macos_arch(staged_binary, macos_arch):
            raise RuntimeError(
                f'bundled Ninja bootstrap produced the wrong macOS architecture: '
                f'expected {macos_arch or "native"}'
            )
        published_binary = staging / staged_binary.name
        shutil.copy2(staged_binary, published_binary)
        if not binary_is_usable(published_binary):
            raise RuntimeError(f'copied bundled Ninja binary is unusable: {published_binary}')
        if not binary_has_macos_arch(published_binary, macos_arch):
            raise RuntimeError(
                f'copied bundled Ninja has the wrong macOS architecture: '
                f'expected {macos_arch or "native"}'
            )
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
