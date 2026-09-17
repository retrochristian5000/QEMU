#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
NATIVE_LLVM_BOOTSTRAP = ROOT / 'scripts' / 'bootstrap-native-clang.bash'


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
    config = load_module('whp_config_cpp_standard_test', CONFIG_TOOL)
    portable = load_module('whp_portable_cpp_standard_test', PORTABLE_BUILD_TOOL)

    qemu_option = config.OPTION_BY_KEY.get('QEMU_CPP_STANDARD')
    require(qemu_option is not None, 'QEMU_CPP_STANDARD is missing from menuconfig')
    require(qemu_option.section == 'Host features',
            'QEMU_CPP_STANDARD is not a Host features option')
    require(qemu_option.kind == 'choice', 'QEMU_CPP_STANDARD must be a choice')
    require(qemu_option.default == 'gnu++23',
            'QEMU_CPP_STANDARD default must remain gnu++23 during migration')
    require(
        qemu_option.choices == ('gnu++17', 'gnu++20', 'gnu++23', 'c++26'),
        'QEMU_CPP_STANDARD choices are incorrect',
    )

    llvm_option = config.OPTION_BY_KEY.get('NATIVE_LLVM_CPP_STANDARD')
    require(llvm_option is not None,
            'NATIVE_LLVM_CPP_STANDARD is missing from menuconfig')
    require(llvm_option.section == 'Host features',
            'NATIVE_LLVM_CPP_STANDARD is not a Host features option')
    require(llvm_option.kind == 'choice',
            'NATIVE_LLVM_CPP_STANDARD must be a choice')
    require(llvm_option.default == '17',
            'NATIVE_LLVM_CPP_STANDARD default must remain 17 during migration')
    require(llvm_option.choices == ('17', '20', '23', '26'),
            'NATIVE_LLVM_CPP_STANDARD choices are incorrect')

    original_qemu = os.environ.get('QEMU_CPP_STANDARD')
    original_llvm = os.environ.get('NATIVE_LLVM_CPP_STANDARD')
    try:
        os.environ['QEMU_CPP_STANDARD'] = 'c++26'
        os.environ['NATIVE_LLVM_CPP_STANDARD'] = '26'
        values = portable.resolved_values()
        require(values['QEMU_CPP_STANDARD'] == 'c++26',
                'C++26 QEMU environment override was not resolved')
        require(values['NATIVE_LLVM_CPP_STANDARD'] == '26',
                'C++26 LLVM environment override was not resolved')
    finally:
        if original_qemu is None:
            os.environ.pop('QEMU_CPP_STANDARD', None)
        else:
            os.environ['QEMU_CPP_STANDARD'] = original_qemu
        if original_llvm is None:
            os.environ.pop('NATIVE_LLVM_CPP_STANDARD', None)
        else:
            os.environ['NATIVE_LLVM_CPP_STANDARD'] = original_llvm

    for standard in qemu_option.choices:
        args = portable.qemu_cpp_standard_configure_args(
            {'QEMU_CPP_STANDARD': standard}
        )
        expected = f'-Dcpp_std={standard}'
        require(args == [expected],
                f'{standard} did not produce exactly {expected}')
        require(
            not any(arg.startswith('--extra-cxxflags=-std=') for arg in args),
            'C++ standard must not be injected through --extra-cxxflags',
        )

    for option, invalid in ((qemu_option, 'gnu++14'), (llvm_option, '14')):
        try:
            config.validate_value(option, invalid)
        except ValueError:
            pass
        else:
            raise SystemExit(f'invalid {option.key}={invalid} was accepted')

    bootstrap = NATIVE_LLVM_BOOTSTRAP.read_text(encoding='utf-8')
    require('NATIVE_LLVM_CPP_STANDARD' in bootstrap,
            'native LLVM bootstrap does not consume NATIVE_LLVM_CPP_STANDARD')
    require('compiler_supports_cxx_standard' in bootstrap,
            'native LLVM bootstrap lacks a C++ standard compiler probe')
    require('-DCMAKE_CXX_STANDARD=' in bootstrap,
            'native LLVM bootstrap does not pass CMAKE_CXX_STANDARD')
    require('CMAKE_CXX_STANDARD=' in bootstrap,
            'native LLVM rebuild marker does not record CMAKE_CXX_STANDARD')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
