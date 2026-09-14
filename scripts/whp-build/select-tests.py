#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from collections.abc import Iterable, Sequence

STATE_VERSION = 1
STATE_FILE = '.whp-test-state.json'

FULL_CHECK_PATHS = {
    'Makefile',
    'meson.build',
    'meson_options.txt',
    'configure',
    'tests/Makefile.include',
    'tests/meson.build',
    'scripts/mtest2make.py',
    'scripts/whp-build/select-tests.py',
}

DOC_PREFIXES = (
    'docs/',
    'README',
    'LICENSE',
    'COPYING',
)

SOURCE_SUFFIXES = {
    '.c', '.h', '.inc', '.m', '.mm', '.py', '.rs', '.json', '.toml', '.yaml', '.yml',
}


def _has_target(configured_targets: set[str], arch: str) -> bool:
    return f'{arch}-softmmu' in configured_targets


def _suite_for_path(path: str, configured_targets: set[str]) -> str | None:
    normalized = pathlib.PurePosixPath(path).as_posix().lstrip('./')

    if normalized in FULL_CHECK_PATHS:
        return 'check'

    if normalized.startswith(DOC_PREFIXES):
        return None

    if normalized.startswith(('block/', 'include/block/', 'tests/qemu-iotests/')):
        return 'check-block'

    if normalized.startswith(('qapi/', 'scripts/qapi/', 'tests/qapi-schema/')):
        return 'check-qapi-schema'

    if normalized.startswith(('qobject/', 'include/qobject/', 'tests/unit/')):
        return 'check-unit'

    if normalized.startswith(('fpu/', 'include/fpu/', 'tests/fp/')):
        return 'check-softfloat'

    if normalized == 'scripts/decodetree.py' or normalized.startswith('tests/decode/'):
        return 'check-decodetree'

    if normalized.startswith('scripts/tracetool/'):
        return 'check-tracetool'

    if normalized.startswith('tests/qtest/'):
        return 'check-qtest'

    if normalized.startswith('tests/functional/'):
        return 'check-functional'

    if normalized.startswith('tests/tcg/'):
        return 'check-tcg'

    arch_prefixes = (
        ('ppc', ('hw/ppc/', 'target/ppc/', 'include/hw/ppc/', 'include/target/ppc/')),
        ('i386', ('hw/i386/', 'target/i386/', 'include/hw/i386/', 'include/target/i386/')),
        ('sparc', ('hw/sparc/', 'target/sparc/', 'include/hw/sparc/', 'include/target/sparc/')),
    )
    for arch, prefixes in arch_prefixes:
        if normalized.startswith(prefixes):
            return f'check-qtest-{arch}' if _has_target(configured_targets, arch) else None

    if pathlib.PurePosixPath(normalized).suffix in SOURCE_SUFFIXES:
        return 'check'

    return None


def select_test_targets(
    changed_paths: Iterable[str], configured_targets: Sequence[str]
) -> list[str]:
    """Map changed repository paths to the smallest safe QEMU check targets."""
    configured = set(configured_targets)
    selected: list[str] = []
    seen: set[str] = set()

    for path in changed_paths:
        suite = _suite_for_path(path, configured)
        if suite == 'check':
            return ['check']
        if suite is not None and suite not in seen:
            seen.add(suite)
            selected.append(suite)

    return selected


def _git(source_dir: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ['git', '-C', str(source_dir), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _head(source_dir: pathlib.Path) -> str:
    return _git(source_dir, 'rev-parse', 'HEAD').stdout.strip()


def _name_list(result: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in result.stdout.splitlines() if line]


def _dirty_paths(source_dir: pathlib.Path) -> list[str]:
    paths = set(
        _name_list(
            _git(source_dir, 'diff', '--name-only', '--diff-filter=ACMDRTUXB', 'HEAD')
        )
    )
    paths.update(
        _name_list(
            _git(source_dir, 'ls-files', '--others', '--exclude-standard')
        )
    )
    return sorted(paths)


def _path_digest(source_dir: pathlib.Path, relative: str) -> str:
    path = source_dir / relative
    try:
        stat = path.lstat()
    except FileNotFoundError:
        return 'deleted'

    digest = hashlib.sha256()
    digest.update(f'mode:{stat.st_mode:o}\0'.encode())
    if path.is_symlink():
        digest.update(b'symlink\0')
        digest.update(os.readlink(path).encode('utf-8', 'surrogateescape'))
    elif path.is_file():
        digest.update(b'file\0')
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(chunk)
    else:
        digest.update(b'other\0')
    return digest.hexdigest()


def _dirty_state(source_dir: pathlib.Path) -> dict[str, str]:
    return {
        path: _path_digest(source_dir, path)
        for path in _dirty_paths(source_dir)
    }


def _snapshot(source_dir: pathlib.Path, configured_targets: Sequence[str]) -> dict[str, object]:
    return {
        'version': STATE_VERSION,
        'head': _head(source_dir),
        'targets': sorted(set(configured_targets)),
        'dirty': _dirty_state(source_dir),
    }


def _read_state(build_dir: pathlib.Path) -> dict[str, object] | None:
    path = build_dir / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or state.get('version') != STATE_VERSION:
        return None
    if not isinstance(state.get('head'), str):
        return None
    if not isinstance(state.get('targets'), list) or not isinstance(state.get('dirty'), dict):
        return None
    return state


def _is_ancestor(source_dir: pathlib.Path, older: str, newer: str) -> bool:
    result = _git(
        source_dir, 'merge-base', '--is-ancestor', older, newer, check=False
    )
    return result.returncode == 0


def _committed_paths(source_dir: pathlib.Path, older: str, newer: str) -> list[str]:
    if older == newer:
        return []
    return _name_list(
        _git(
            source_dir,
            'diff',
            '--name-only',
            '--diff-filter=ACMDRTUXB',
            f'{older}..{newer}',
        )
    )


def _paths_changed_since_state(
    source_dir: pathlib.Path,
    previous: dict[str, object],
    current: dict[str, object],
) -> list[str]:
    previous_head = str(previous['head'])
    current_head = str(current['head'])
    previous_dirty = {
        str(path): str(digest)
        for path, digest in dict(previous['dirty']).items()
    }
    current_dirty = {
        str(path): str(digest)
        for path, digest in dict(current['dirty']).items()
    }

    candidates = set(_committed_paths(source_dir, previous_head, current_head))
    candidates.update(previous_dirty)
    candidates.update(current_dirty)

    changed: list[str] = []
    for path in sorted(candidates):
        before_dirty = previous_dirty.get(path)
        after_dirty = current_dirty.get(path)

        if before_dirty is not None and after_dirty == before_dirty:
            # The same dirty content was already validated.
            continue

        if before_dirty is not None and after_dirty is None:
            # A previously dirty file may merely have been committed. Avoid
            # rerunning its suite when the tested bytes are unchanged.
            if _path_digest(source_dir, path) == before_dirty:
                continue

        if before_dirty is None and after_dirty is None and previous_head == current_head:
            continue

        changed.append(path)

    return changed


def plan_changed_tests(
    source_dir: pathlib.Path,
    build_dir: pathlib.Path,
    configured_targets: Sequence[str],
) -> list[str]:
    """Return QEMU check targets needed since the last successful test state.

    Missing/corrupt state, non-linear history, target-set changes, or Git
    failures conservatively request the complete ``check`` suite.
    """
    try:
        current = _snapshot(source_dir, configured_targets)
        previous = _read_state(build_dir)
        if previous is None:
            return ['check']
        if previous.get('targets') != current.get('targets'):
            return ['check']
        if previous == current:
            return []
        if not _is_ancestor(source_dir, str(previous['head']), str(current['head'])):
            return ['check']
        changed = _paths_changed_since_state(source_dir, previous, current)
        return select_test_targets(changed, configured_targets)
    except (OSError, subprocess.SubprocessError, ValueError):
        return ['check']


def record_test_state(
    source_dir: pathlib.Path,
    build_dir: pathlib.Path,
    configured_targets: Sequence[str],
) -> None:
    """Atomically record the exact source/target state that just passed tests."""
    state = _snapshot(source_dir, configured_targets)
    build_dir.mkdir(parents=True, exist_ok=True)
    path = build_dir / STATE_FILE
    candidate = path.with_name(path.name + '.new')
    candidate.write_text(
        json.dumps(state, sort_keys=True, separators=(',', ':')) + '\n',
        encoding='utf-8',
    )
    os.replace(candidate, path)


def _targets(value: str) -> list[str]:
    return [target for target in value.split(',') if target]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('plan', 'record'))
    parser.add_argument('--source', required=True, type=pathlib.Path)
    parser.add_argument('--build', required=True, type=pathlib.Path)
    parser.add_argument('--targets', default='')
    args = parser.parse_args(argv)

    targets = _targets(args.targets)
    if args.action == 'plan':
        for target in plan_changed_tests(args.source, args.build, targets):
            print(target)
        return 0

    try:
        record_test_state(args.source, args.build, targets)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f'error: cannot record QEMU test state: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
