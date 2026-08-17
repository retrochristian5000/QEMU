#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import sys
from typing import Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
USER_CONFIG = ROOT / '.whpconfig'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load WHP configuration tool: {CONFIG_TOOL}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_bool(name: str, value: str) -> str:
    lowered = value.lower()
    if lowered in ('1', 'y', 'yes', 'true', 'on'):
        return 'y'
    if lowered in ('0', 'n', 'no', 'false', 'off'):
        return 'n'
    raise ValueError(f'{name} must be y/n or 1/0')


def normalize_choice(name: str, value: str, choices: Tuple[str, ...]) -> str:
    lowered = value.lower()
    if lowered == 'auto' and 'auto' in choices:
        return 'auto'
    if lowered in ('1', 'y', 'yes', 'true', 'on') and 'y' in choices:
        return 'y'
    if lowered in ('0', 'n', 'no', 'false', 'off') and 'n' in choices:
        return 'n'
    if value in choices:
        return value
    raise ValueError(f"{name} must be one of: {', '.join(choices)}")


def resolved_values() -> Dict[str, str]:
    mod = load_config_module()
    state = mod.load_config(USER_CONFIG)
    values = dict(state.values)
    for option in mod.OPTIONS:
        raw = os.environ.get(option.key)
        if raw is None:
            continue
        if option.kind == 'bool':
            values[option.key] = normalize_bool(option.key, raw)
        elif option.kind == 'choice':
            values[option.key] = normalize_choice(option.key, raw, option.choices)
        else:
            mod.validate_value(option, raw)
            values[option.key] = raw
    return values


def default_prefix(build_dir: pathlib.Path) -> pathlib.Path:
    home = os.environ.get('HOME')
    if home:
        home_path = pathlib.Path(home).expanduser()
        if home_path.is_dir() and os.access(home_path, os.W_OK):
            return home_path / '.local' / 'whp-qemu'
    return build_dir / 'install'


def optional_switch(args: List[str], value: str, feature: str) -> None:
    if value == 'y':
        args.append(f'--enable-{feature}')
    elif value == 'n':
        args.append(f'--disable-{feature}')


def select_runner() -> List[str]:
    requested_ninja = os.environ.get('NINJA_CMD') or os.environ.get('NINJA')
    if requested_ninja:
        return shlex.split(requested_ninja)
    for name in ('ninja', 'ninja-build'):
        path = shutil.which(name)
        if path:
            return [path]

    requested_make = os.environ.get('MAKE_CMD') or os.environ.get('MAKE')
    if requested_make:
        return shlex.split(requested_make)
    for name in ('gmake', 'make'):
        path = shutil.which(name)
        if path:
            return [path]
    raise RuntimeError('neither Ninja nor Make is available to run the QEMU build')


def build_plan(argv: List[str]) -> Tuple[pathlib.Path, pathlib.Path, List[str], List[str], List[str]]:
    values = resolved_values()
    build_dir = pathlib.Path(os.environ.get('BUILD_DIR', str(ROOT / 'build' / 'whp-portable'))).expanduser()
    prefix_value = values['PREFIX']
    prefix = default_prefix(build_dir) if prefix_value == 'auto' else pathlib.Path(prefix_value).expanduser()

    targets: List[str] = []
    if values['BUILD_QEMU_SYSTEM_PPC'] == 'y':
        targets.append('ppc-softmmu')
    if values['BUILD_QEMU_SYSTEM_I386'] == 'y':
        targets.append('i386-softmmu')

    configure_args: List[str] = [f'--prefix={prefix}']
    if targets:
        configure_args.append(f"--target-list={','.join(targets)}")
    else:
        configure_args.append('--disable-system')

    configure_args.append('--enable-tools' if values['BUILD_QEMU_IMG'] == 'y' else '--disable-tools')
    optional_switch(configure_args, values['QEMU_HOST_LTO'], 'lto')
    optional_switch(configure_args, values['MACOS_ENABLE_GTK'], 'gtk')
    optional_switch(configure_args, values['MACOS_ENABLE_PA'], 'pa')

    if platform.system() == 'Darwin':
        optional_switch(configure_args, values['MACOS_ENABLE_COCOA'], 'cocoa')
        optional_switch(configure_args, values['MACOS_ENABLE_COREAUDIO'], 'coreaudio')

    custom_macs = values['CONFIG_MAC_NEWWORLD'] != 'y' or values['CONFIG_MAC_OLDWORLD'] != 'y'
    if custom_macs:
        raise RuntimeError(
            'custom PowerPC Mac device filtering requires the Bash feature adapter; '
            'core QEMU remains buildable with the tracked PPC defaults'
        )

    declines: List[str] = []
    if values['BUILD_OPENBIOS'] == 'y':
        raise RuntimeError('OpenBIOS was explicitly requested, but the Bash firmware adapter is unavailable')
    if values['BOOTSTRAP_POWERPC_TOOLCHAIN'] == 'y':
        raise RuntimeError('PowerPC toolchain bootstrap was explicitly requested, but the Bash firmware adapter is unavailable')
    if values['BUILD_OPENBIOS'] == 'auto' and 'ppc-softmmu' in targets:
        declines.append('OpenBIOS:auto:bash-unavailable')

    requested_targets = argv[:] if argv else ['all']
    return build_dir, prefix, configure_args, requested_targets, declines


def print_plan(build_dir: pathlib.Path, prefix: pathlib.Path, configure_args: List[str], targets: List[str], declines: List[str]) -> None:
    print(f'BUILD_DIR={build_dir}')
    print(f'PREFIX={prefix}')
    for arg in configure_args:
        print(f'CONFIGURE_ARG={arg}')
    for target in targets:
        print(f'BUILD_TARGET={target}')
    for decline in declines:
        print(f'OPTIONAL_DECLINE={decline}')


def main(argv: List[str]) -> int:
    if sys.version_info < (3, 9):
        print('error: Python 3.9 or newer is required by QEMU', file=sys.stderr)
        return 2

    try:
        build_dir, prefix, configure_args, requested_targets, declines = build_plan(argv)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    if os.environ.get('WHP_PORTABLE_PROBE_ONLY') == '1':
        print_plan(build_dir, prefix, configure_args, requested_targets, declines)
        return 0

    for decline in declines:
        print(f'WHP optional feature skipped: {decline}', file=sys.stderr)

    build_dir.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run([str(ROOT / 'configure'), *configure_args], cwd=build_dir, check=True)
        runner = select_runner()
        jobs = os.environ.get('JOBS') or str(os.cpu_count() or 1)
        runner_name = pathlib.Path(runner[0]).name
        if runner_name.startswith('ninja'):
            build_command = [*runner, '-C', str(build_dir), '-j', jobs, *requested_targets]
        else:
            build_command = [*runner, '-C', str(build_dir), f'-j{jobs}', *requested_targets]
        subprocess.run(build_command, check=True)

        values = resolved_values()
        if values['INSTALL'] == 'y':
            if runner_name.startswith('ninja'):
                subprocess.run([*runner, '-C', str(build_dir), 'install'], check=True)
            else:
                subprocess.run([*runner, '-C', str(build_dir), 'install'], check=True)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f'error: core QEMU build failed: {exc}', file=sys.stderr)
        return 1

    manifest = build_dir / '.whp-build-artifacts'
    with manifest.open('w', encoding='utf-8') as handle:
        handle.write('SCHEMA=2\n')
        handle.write('PORTABLE_CORE=1\n')
        handle.write(f'SOURCE_DIR={ROOT}\n')
        handle.write(f'BUILD_DIR={build_dir}\n')
        handle.write(f'PREFIX={prefix}\n')
        handle.write(f'REQUESTED_TARGETS={" ".join(requested_targets)}\n')
        for decline in declines:
            handle.write(f'OPTIONAL_DECLINE={decline}\n')
    print(f'build artifact manifest: {manifest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
