#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> int:
    config = load_module('whp_config_c_standard_test', CONFIG_TOOL)
    portable = load_module('whp_portable_c_standard_test', PORTABLE_BUILD_TOOL)

    option = config.OPTION_BY_KEY.get('QEMU_C_STANDARD')
    require(option is not None, 'QEMU_C_STANDARD is missing from menuconfig')
    require(option.section == 'Host features', 'QEMU_C_STANDARD is not a Host features option')
    require(option.kind == 'choice', 'QEMU_C_STANDARD must be a choice')
    require(option.default == 'gnu11', 'QEMU_C_STANDARD default must remain gnu11 during migration')
    require(option.choices == ('gnu11', 'gnu17', 'gnu23'), 'QEMU_C_STANDARD choices are incorrect')

    original = os.environ.get('QEMU_C_STANDARD')
    try:
        os.environ['QEMU_C_STANDARD'] = 'gnu23'
        values = portable.resolved_values()
        require(values['QEMU_C_STANDARD'] == 'gnu23', 'gnu23 environment override was not resolved')
    finally:
        if original is None:
            os.environ.pop('QEMU_C_STANDARD', None)
        else:
            os.environ['QEMU_C_STANDARD'] = original

    # The production build-plan path must translate the resolved setting into
    # Meson's built-in c_std option. This helper is intentionally small so the
    # contract can be tested without running configure or compiling QEMU.
    for standard in option.choices:
        args = portable.qemu_c_standard_configure_args({'QEMU_C_STANDARD': standard})
        expected = f'-Dc_std={standard}'
        require(args == [expected], f'{standard} did not produce exactly {expected}')
        require(
            not any(arg.startswith('--extra-cflags=-std=') for arg in args),
            'C standard must not be injected through --extra-cflags',
        )

    try:
        config.validate_value(option, 'gnu99')
    except ValueError:
        pass
    else:
        raise SystemExit('invalid QEMU_C_STANDARD=gnu99 was accepted')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
