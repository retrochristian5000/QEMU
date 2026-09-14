#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import sys
from typing import List

CORE_PATH = pathlib.Path(__file__).with_name('portable-build.py')
I386_AUDIO_KEYS = (
    'I386_AUDIO_SB16',
    'I386_AUDIO_ADLIB',
    'I386_AUDIO_GUS',
    'I386_AUDIO_CS4231A',
    'I386_AUDIO_PCSPK',
    'I386_AUDIO_ES1370',
    'I386_AUDIO_AC97',
    'I386_AUDIO_CS4630',
    'I386_AUDIO_HDA',
)
PPC_AUDIO_KEYS = (
    'PPC_AUDIO_SB16',
    'PPC_AUDIO_ADLIB',
    'PPC_AUDIO_GUS',
    'PPC_AUDIO_CS4231A',
    'PPC_AUDIO_PCSPK',
    'PPC_AUDIO_ES1370',
    'PPC_AUDIO_AC97',
    'PPC_AUDIO_CS4630',
    'PPC_AUDIO_HDA',
)
HARDWARE_KEYS = I386_AUDIO_KEYS + PPC_AUDIO_KEYS


def load_core():
    spec = importlib.util.spec_from_file_location('whp_portable_build_core', CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load portable build core: {CORE_PATH}')
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

        if any(values[key] != 'auto' for key in HARDWARE_KEYS):
            raise RuntimeError(
                'custom QEMU hardware filtering requires the Bash feature adapter; '
                'core QEMU remains buildable with tracked per-architecture defaults'
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


def main(argv: List[str]) -> int:
    try:
        validate_jobs()
        core = load_core()
        install_diagnostic_policy(core)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return core.main(argv)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
