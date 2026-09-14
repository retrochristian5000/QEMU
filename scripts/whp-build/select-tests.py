#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
from collections.abc import Iterable, Sequence


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
    """Map changed repository paths to the smallest safe QEMU check targets.

    A single unclassified source/build change escalates the batch to ``check``.
    Documentation and non-source metadata can safely select no QEMU regression
    suite. Architecture-specific suites are omitted when that target was not
    configured in the current build tree.
    """
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
