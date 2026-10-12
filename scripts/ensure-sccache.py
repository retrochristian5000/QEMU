#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bootstrap the pinned WHP sccacher fork for local compiler caching."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE = pathlib.Path('toolchains/sccacher')
SCHEMA = 1


def call(argv, *, cwd=None, env=None, capture=False):
    process = subprocess.run(
        argv, cwd=cwd, env=env, text=True, check=False,
        stdout=subprocess.PIPE if capture else sys.stderr,
        stderr=subprocess.PIPE if capture else sys.stderr,
    )
    if process.returncode:
        detail = process.stderr.strip() if capture else ''
        raise RuntimeError(f'{argv[0]} failed ({process.returncode})' +
                           (f': {detail}' if detail else ''))
    return process.stdout.strip() if capture else ''


def pinned_source():
    line = call(['git', '-C', str(ROOT), 'ls-tree', 'HEAD', '--', str(SUBMODULE)],
                capture=True)
    fields = line.split()
    if len(fields) != 4 or fields[0] != '160000' or fields[1] != 'commit' or not re.fullmatch(r'[0-9a-f]{40}', fields[2]):
        raise RuntimeError('QEMU is missing the pinned sccacher gitlink')
    source = ROOT / SUBMODULE
    if (source / '.git').exists():
        dirty = call(['git', '-C', str(source), 'status', '--porcelain',
                      '--untracked-files=no'], capture=True)
        if dirty:
            raise RuntimeError('sccacher submodule has uncommitted changes; refusing checkout')
    current = ''
    if (source / '.git').exists():
        current = call(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture=True)
    if current != fields[2]:
        call(['git', '-C', str(ROOT), 'submodule', 'update', '--init',
              '--depth', '1', '--', str(SUBMODULE)])
    actual = call(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture=True)
    if actual != fields[2]:
        raise RuntimeError('sccacher checkout does not match the QEMU gitlink')
    if not (source / 'Cargo.toml').is_file() or not (source / 'Cargo.lock').is_file():
        raise RuntimeError('sccacher source must contain Cargo.toml and Cargo.lock')
    return source, actual


def build_jobs(environ):
    raw = environ.get('WHP_SCCACHE_BUILD_JOBS', '2')
    if not re.fullmatch(r'[1-9][0-9]*', raw):
        raise ValueError('WHP_SCCACHE_BUILD_JOBS must be a positive integer')
    return int(raw)


def cargo_environment(environ, target):
    env = dict(environ)
    for key in ('RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER',
                'CARGO_BUILD_RUSTC_WRAPPER', 'CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER',
                'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS', 'CARGO_BUILD_RUSTFLAGS'):
        env.pop(key, None)
    env.update({
        'CARGO_TARGET_DIR': str(target),
        'CARGO_PROFILE_RELEASE_LTO': 'false',
        'CARGO_PROFILE_RELEASE_CODEGEN_UNITS': '8',
        'CARGO_PROFILE_RELEASE_DEBUG': '0',
        'CARGO_INCREMENTAL': '0',
    })
    return env


def host_tools():
    cargo = shutil.which('cargo')
    rustc = shutil.which('rustc')
    if not cargo or not rustc:
        raise RuntimeError('BOOTSTRAP_SCCACHE=1 requires Cargo and Rust 1.91 or newer')
    version = call([rustc, '--version'], capture=True)
    match = re.match(r'^rustc (\d+)\.(\d+)\.(\d+)', version)
    if not match or tuple(map(int, match.groups())) < (1, 91, 0):
        raise RuntimeError('sccacher requires Rust 1.91.0 or newer: ' + version)
    return cargo, version, call([cargo, '--version'], capture=True)


def ensure(build_dir):
    source, revision = pinned_source()
    cargo, rust_version, cargo_version = host_tools()
    jobs = build_jobs(os.environ)
    host = f'{platform.system().lower()}-{platform.machine().lower()}'
    prefix = build_dir / 'toolchains' / 'sccache' / host
    executable = prefix / 'bin' / 'sccache'
    marker = prefix / '.whp-sccacher.json'
    identity = {'schema': SCHEMA, 'gitlink': revision, 'rustc': rust_version,
                'cargo': cargo_version, 'features': 'local-only',
                'profile': 'lto=false,codegen-units=8,debug=0'}
    if executable.is_file() and os.access(executable, os.X_OK) and marker.is_file():
        try:
            if json.loads(marker.read_text(encoding='utf-8')) == identity:
                call([str(executable), '--version'], capture=True)
                return executable
        except (ValueError, RuntimeError, OSError):
            pass
    target = build_dir / 'toolchain-work' / 'sccacher' / host
    target.mkdir(parents=True, exist_ok=True)
    print(f'WHP sccacher: building {revision} with {jobs} Cargo jobs', file=sys.stderr)
    call([cargo, 'build', '--locked', '--release', '--no-default-features',
          '--bin', 'sccache', '--jobs', str(jobs)], cwd=source,
         env=cargo_environment(os.environ, target))
    built = target / 'release' / 'sccache'
    if not built.is_file():
        raise RuntimeError('Cargo succeeded without producing the sccache executable')
    call([str(built), '--version'], capture=True)
    (prefix / 'bin').mkdir(parents=True, exist_ok=True)
    # Atomic replacements: never delete the previously working cache binary.
    with tempfile.TemporaryDirectory(prefix='whp-sccacher-', dir=prefix) as staging:
        staged_bin = pathlib.Path(staging) / 'sccache'
        staged_marker = pathlib.Path(staging) / 'marker'
        shutil.copy2(built, staged_bin)
        staged_marker.write_text(json.dumps(identity, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(staged_bin, executable)
        os.replace(staged_marker, marker)
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=pathlib.Path, required=True)
    args = parser.parse_args()
    try:
        path = ensure(args.build_dir.resolve())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'error: WHP sccacher: {exc}', file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
