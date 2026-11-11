#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
from typing import List

CORE_PATH = pathlib.Path(__file__).with_name('portable-build.py')
I386_AUDIO_KEYS = (
    'I386_AUDIO_GAMEBLASTER',
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
    'PPC_AUDIO_GAMEBLASTER',
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


def add_portable_host_linker(values, configure_args: List[str]) -> None:
    """Select a host linker without assuming an ELF/Mach-O/COFF OS mapping."""
    selected = values['QEMU_HOST_LINKER']
    mold_policy = values['BOOTSTRAP_MOLD']
    if mold_policy == 'y':
        raise RuntimeError(
            'BOOTSTRAP_MOLD=y requires the Bash toolchain bootstrap; '
            'portable builds can use an installed mold via QEMU_HOST_LINKER=mold'
        )
    if selected == 'auto':
        return

    for variable in ('CC', 'CXX', 'OBJC', 'CFLAGS', 'CXXFLAGS',
                     'OBJCFLAGS', 'CPPFLAGS', 'LDFLAGS'):
        tokens = shlex.split(os.environ.get(variable, ''))
        for token in tokens:
            if token.startswith('-fuse-ld='):
                requested = token.split('=', 1)[1]
                if requested != selected and not (
                    selected == 'system' and requested == 'ld'
                ):
                    raise RuntimeError(
                        f'QEMU_HOST_LINKER={selected} conflicts with {variable}: {token}'
                    )
            elif token.startswith('--ld-path'):
                raise RuntimeError(
                    f'QEMU_HOST_LINKER={selected} conflicts with {variable}: {token}'
                )
    if selected == 'system':
        return

    flag = f'-fuse-ld={selected}'
    extra_flags = shlex.split(os.environ.get('LDFLAGS', ''))
    with tempfile.TemporaryDirectory(prefix='whp-linker-') as directory:
        for variable, default, extension, language in (
            ('CC', 'cc', '.c', 'c'),
            ('CXX', 'c++', '.cpp', 'c++'),
        ):
            compiler = shlex.split(os.environ.get(variable, default))
            if not compiler:
                raise RuntimeError(f'{variable} is empty during linker probe')
            source = pathlib.Path(directory) / ('probe' + extension)
            source.write_text(
                'int main(void) { return 0; }\n' if language == 'c'
                else 'int main() { return 0; }\n',
                encoding='utf-8',
            )
            output = pathlib.Path(directory) / (
                'probe-' + variable + ('.exe' if os.name == 'nt' else '')
            )
            cmd = [*compiler, '-x', language, str(source), flag,
                   *extra_flags, '-o', str(output)]
            try:
                result = subprocess.run(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, check=False,
                )
            except OSError as exc:
                raise RuntimeError(
                    f'{variable} cannot execute the {selected} linker probe: {exc}'
                ) from exc
            if result.returncode != 0:
                raise RuntimeError(
                    f'{variable} cannot link with {selected}: {result.stderr.strip()}'
                )
            try:
                subprocess.run([str(output)], check=True, timeout=10,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(
                    f'{selected} produced an unusable {variable} host executable: {exc}'
                ) from exc
    configure_args.append(f'--extra-ldflags={flag}')


def install_diagnostic_policy(core) -> None:
    original_build_plan = core.build_plan

    def build_plan(argv: List[str]):
        build_dir, prefix, configure_args, requested_targets, declines = \
            original_build_plan(argv)
        values = core.resolved_values()
        add_portable_host_linker(values, configure_args)

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
