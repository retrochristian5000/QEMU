#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import sys
from typing import List

CORE_PATH = pathlib.Path(__file__).with_name('portable-build.py')
SELECTOR_PATH = pathlib.Path(__file__).with_name('select-tests.py')


def load_core():
    spec = importlib.util.spec_from_file_location('whp_portable_build_core', CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load portable build core: {CORE_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_selector():
    spec = importlib.util.spec_from_file_location('whp_select_tests', SELECTOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load QEMU test selector: {SELECTOR_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_jobs() -> None:
    value = os.environ.get('JOBS')
    if value is None or value == '':
        return
    if not value.isdecimal() or int(value) <= 0:
        raise ValueError(f'JOBS must be a positive integer when set: {value}')


def install_diagnostic_policy(core) -> None:
    original_build_plan = core.build_plan

    def build_plan(argv: List[str]):
        build_dir, prefix, configure_args, requested_targets, declines = \
            original_build_plan(argv)
        values = core.resolved_values()

        # The portable Python entry skips the Bash bootstrap graph entirely.
        # Fail closed when native LLVM was explicitly requested instead of
        # silently compiling QEMU with whichever system compiler is available.
        if values['BOOTSTRAP_NATIVE_LLVM'] == 'y':
            raise RuntimeError(
                'BOOTSTRAP_NATIVE_LLVM was explicitly requested, but the portable '
                'core does not run the native LLVM bootstrap'
            )

        if values['BUILD_QEMU_SYSTEM_SPARC'] == 'y':
            for index, arg in enumerate(configure_args):
                if arg.startswith('--target-list='):
                    targets = arg.split('=', 1)[1].split(',')
                    core.append_unique(targets, 'sparc-softmmu')
                    configure_args[index] = '--target-list=' + ','.join(targets)
                    break
                if arg == '--disable-system':
                    configure_args[index] = '--target-list=sparc-softmmu'
                    break

        if values['QEMU_TSAN'] == 'y' and (
            values['QEMU_ASAN'] == 'y' or values['QEMU_UBSAN'] == 'y'
        ):
            raise RuntimeError(
                'QEMU_TSAN cannot be combined with QEMU_ASAN or QEMU_UBSAN; '
                'QEMU does not support ThreadSanitizer together with the other sanitizers'
            )

        for key, feature in (
            ('QEMU_WERROR', 'werror'),
            ('QEMU_ASAN', 'asan'),
            ('QEMU_UBSAN', 'ubsan'),
            ('QEMU_TSAN', 'tsan'),
        ):
            core.optional_switch(configure_args, values[key], feature)

        return build_dir, prefix, configure_args, requested_targets, declines

    core.build_plan = build_plan


def install_test_policy(core) -> None:
    original_run_qemu_tests = core.run_qemu_tests

    def record_state(selector, build_dir: pathlib.Path, targets: List[str]) -> None:
        try:
            selector.record_test_state(core.ROOT, build_dir, targets)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            print(
                f'warning: QEMU tests passed but selective test state could not be recorded: {exc}',
                file=sys.stderr,
            )

    def run_qemu_tests(build_dir: pathlib.Path, jobs: str) -> None:
        values = core.resolved_values()
        scope = values.get('QEMU_TEST_SCOPE', 'changed')
        targets = core.previous_configured_targets(build_dir)
        selector = load_selector()

        if scope == 'full':
            print('WHP QEMU tests: check')
            original_run_qemu_tests(build_dir, jobs)
            record_state(selector, build_dir, targets)
            return
        if scope != 'changed':
            raise RuntimeError(
                f'QEMU_TEST_SCOPE must be changed or full: {scope}'
            )

        test_targets = selector.plan_changed_tests(core.ROOT, build_dir, targets)
        if test_targets:
            make = core.select_gnu_make()
            print(f"WHP QEMU tests: {' '.join(test_targets)}")
            subprocess.run(
                [*make, '-C', str(build_dir), f'-j{jobs}', *test_targets],
                check=True,
            )
        else:
            print('WHP QEMU tests: no affected suites; skipping unchanged tests.')
        record_state(selector, build_dir, targets)

    core.run_qemu_tests = run_qemu_tests


def main(argv: List[str]) -> int:
    try:
        validate_jobs()
        core = load_core()
        install_diagnostic_policy(core)
        install_test_policy(core)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return core.main(argv)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
