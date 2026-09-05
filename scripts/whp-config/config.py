#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys
from collections import OrderedDict
from typing import Dict, List, NamedTuple, Optional, Tuple

CONFIG_VERSION = '2'
SUPPORTED_CONFIG_VERSIONS = {'1', '2'}


class Option(NamedTuple):
    key: str
    section: str
    label: str
    kind: str
    default: str
    choices: Tuple[str, ...] = ()


OPTIONS = (
    Option('BUILD_QEMU_IMG', 'Build outputs', 'qemu-img', 'bool', 'y'),
    Option('BUILD_QEMU_SYSTEM_I386', 'Build outputs', 'qemu-system-i386', 'bool', 'y'),
    Option('BUILD_QEMU_SYSTEM_PPC', 'Build outputs', 'qemu-system-ppc', 'bool', 'y'),
    Option('BUILD_QEMU_SYSTEM_SPARC', 'Build outputs', 'qemu-system-sparc', 'bool', 'n'),
    Option('QEMU_HOST_LTO', 'Host features', 'Link-time optimization', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('QEMU_HOST_OPTIMIZATION', 'Host features', 'QEMU host optimization level', 'choice', '3', ('0', '1', '2', '3', 'g', 's')),
    Option('QEMU_HOST_CPU_TUNING', 'Host features', 'QEMU host CPU tuning flags', 'string', 'native'),
    Option('BOOTSTRAP_NATIVE_LLVM', 'Host features', 'Bootstrap/use WHP native LLVM', 'bool', 'n'),
    Option('BOOTSTRAP_NINJA', 'Host features', 'Bootstrap/use WHP Ninja', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('COMPILER_CACHE', 'Host features', 'Compiler cache', 'choice', 'auto', ('auto', 'ccache', 'sccache', 'none')),
    Option('BOOTSTRAP_MOLD', 'Host features', 'Bootstrap/use WHP mold (ELF hosts)', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('MACOS_ENABLE_COCOA', 'Host features', 'Cocoa', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('MACOS_ENABLE_COREAUDIO', 'Host features', 'CoreAudio', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('MACOS_ENABLE_GTK', 'Host features', 'GTK', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('MACOS_ENABLE_PA', 'Host features', 'PulseAudio', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('QEMU_WERROR', 'Diagnostics', 'Treat compiler warnings as errors', 'bool', 'y'),
    Option('QEMU_ASAN', 'Diagnostics', 'AddressSanitizer', 'bool', 'n'),
    Option('QEMU_UBSAN', 'Diagnostics', 'UndefinedBehaviorSanitizer', 'bool', 'n'),
    Option('QEMU_TSAN', 'Diagnostics', 'ThreadSanitizer', 'bool', 'n'),
    Option('BUILD_OPENBIOS', 'Firmware', 'Build OpenBIOS', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_POWERPC_TOOLCHAIN', 'Firmware', 'Bootstrap PowerPC toolchain', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BUILD_SEABIOS', 'Firmware', 'Build SeaBIOS', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BUILD_SEABIOS_GRUB', 'Firmware', 'Build GRUB-loadable SeaBIOS', 'bool', 'n'),
    Option('BUILD_SEABIOS_HYBRID_ISO', 'Firmware', 'Build hybrid x86 UEFI SeaBIOS ISO', 'bool', 'n'),
    Option('BOOTSTRAP_I386_TOOLCHAIN', 'Firmware', 'Bootstrap i386 LLVM toolchain', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_WIN9X_TOOLCHAIN', 'Windows 9x cross-tools', 'Bootstrap i386-pc-win9x LLVM toolchain', 'bool', 'n'),
    Option('PREFIX', 'Build behavior', 'Install prefix', 'string', 'auto'),
    Option('WHP_INCREMENTAL_BUILD', 'Build behavior', 'Incremental builds', 'bool', 'y'),
    Option('RUN_TESTS', 'Build behavior', 'Run tests after build', 'bool', 'y'),
    Option('INSTALL', 'Build behavior', 'Install after build', 'bool', 'n'),
    Option('CONFIG_MAC_NEWWORLD', 'QEMU machines', 'New World Macintosh', 'bool', 'y'),
    Option('CONFIG_MAC_OLDWORLD', 'QEMU machines', 'Old World Macintosh', 'bool', 'y'),
)

OPTION_BY_KEY = {option.key: option for option in OPTIONS}
PORTABLE_BOOL_KEYS = {option.key for option in OPTIONS if option.kind == 'bool'}
RAW_CONFIG_KEYS = {'CONFIG_MAC_NEWWORLD', 'CONFIG_MAC_OLDWORLD'}
SHELL_BOOL_KEYS = PORTABLE_BOOL_KEYS - RAW_CONFIG_KEYS
SHELL_TRI_STATE_KEYS = {
    'QEMU_HOST_LTO',
    'BOOTSTRAP_NINJA',
    'BOOTSTRAP_MOLD',
    'MACOS_ENABLE_COCOA',
    'MACOS_ENABLE_COREAUDIO',
    'MACOS_ENABLE_GTK',
    'MACOS_ENABLE_PA',
    'BUILD_OPENBIOS',
    'BOOTSTRAP_POWERPC_TOOLCHAIN',
    'BUILD_SEABIOS',
    'BOOTSTRAP_I386_TOOLCHAIN',
}
_TARGET_LIST_RE = re.compile(r'^[A-Za-z0-9_.,+:/-]+$')
_KEY_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')


class ConfigState:
    def __init__(self, values: Dict[str, str], unknown: Optional[Dict[str, str]] = None):
        self.values = values
        self.unknown = OrderedDict(unknown or {})


def default_values() -> Dict[str, str]:
    return {option.key: option.default for option in OPTIONS}


def validate_value(option: Option, value: str) -> None:
    if option.kind == 'bool':
        if value not in ('y', 'n'):
            raise ValueError(f'{option.key} must be y or n')
        return
    if option.kind == 'choice':
        if value not in option.choices:
            raise ValueError(
                f"{option.key} must be one of: {', '.join(option.choices)}"
            )
        return
    if option.kind == 'string':
        if not value or any(character in value for character in ('\n', '\r', '\0')):
            raise ValueError(f'{option.key} contains an invalid line break or NUL')
        return
    raise ValueError(f'unsupported option type for {option.key}')


def load_config(path: pathlib.Path) -> ConfigState:
    values = default_values()
    unknown: OrderedDict[str, str] = OrderedDict()
    if not path.exists():
        return ConfigState(values, unknown)

    config_version: Optional[str] = None
    seen_options = set()
    legacy_target_list = None
    for number, raw_line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(f'{path}:{number}: expected KEY=VALUE')
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f'{path}:{number}: invalid option name: {key}')
        if key == 'WHP_CONFIG_VERSION':
            config_version = value
            if value not in SUPPORTED_CONFIG_VERSIONS:
                raise ValueError(
                    f'{path}:{number}: unsupported WHP_CONFIG_VERSION={value}'
                )
            continue
        if key == 'QEMU_TARGET_LIST':
            if not value or not _TARGET_LIST_RE.fullmatch(value):
                raise ValueError(
                    f'{path}:{number}: QEMU_TARGET_LIST contains unsupported characters'
                )
            legacy_target_list = value
            continue
        option = OPTION_BY_KEY.get(key)
        if option is None:
            unknown[key] = value
            continue
        validate_value(option, value)
        values[key] = value
        seen_options.add(key)

    if legacy_target_list is not None:
        legacy_targets = set(legacy_target_list.split(','))
        legacy_outputs = {
            'BUILD_QEMU_SYSTEM_I386': 'i386-softmmu',
            'BUILD_QEMU_SYSTEM_PPC': 'ppc-softmmu',
            'BUILD_QEMU_SYSTEM_SPARC': 'sparc-softmmu',
        }
        for key, target in legacy_outputs.items():
            if key not in seen_options:
                values[key] = 'y' if target in legacy_targets else 'n'

    if path.stat().st_size and config_version is None:
        print(
            f'warning: {path} has no WHP_CONFIG_VERSION; treating it as version 1',
            file=sys.stderr,
        )
    elif config_version == '1':
        print(
            f'warning: {path} uses WHP_CONFIG_VERSION=1; portable defaults are migrated in memory',
            file=sys.stderr,
        )
    for key in unknown:
        print(f'warning: saved option {key} is no longer recognized', file=sys.stderr)
    return ConfigState(values, unknown)


def render_config(state: ConfigState) -> str:
    lines = [
        '# WHP QEMU portable user configuration',
        '# This file is user-owned and is not rewritten by repository updates.',
        f'WHP_CONFIG_VERSION={CONFIG_VERSION}',
        '',
    ]
    previous_section = None
    for option in OPTIONS:
        if option.section != previous_section:
            if previous_section is not None:
                lines.append('')
            lines.append(f'# {option.section}')
            previous_section = option.section
        value = state.values[option.key]
        validate_value(option, value)
        lines.append(f'{option.key}={value}')
    if state.unknown:
        lines.extend(['', '# Preserved settings not recognized by this checkout'])
        for key, value in state.unknown.items():
            lines.append(f'{key}={value}')
    return '\n'.join(lines) + '\n'


def save_config(path: pathlib.Path, state: ConfigState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(render_config(state), encoding='utf-8')
    os.replace(temp, path)


def shell_assignments(state: ConfigState, environ: Dict[str, str]) -> str:
    lines: List[str] = []
    for option in OPTIONS:
        key = option.key
        if key in environ:
            continue
        value = state.values[key]
        if value == 'auto':
            continue
        if key in SHELL_BOOL_KEYS or key in SHELL_TRI_STATE_KEYS:
            value = '1' if value == 'y' else '0'
        quoted = "'" + value.replace("'", "'\"'\"'") + "'"
        lines.append(f'{key}={quoted}')
        lines.append(f'export {key}')
    return '\n'.join(lines) + ('\n' if lines else '')


def render_ppc_device_config(values: Dict[str, str], base: str) -> str:
    overridden = {'CONFIG_MAC_NEWWORLD', 'CONFIG_MAC_OLDWORLD'}
    kept_lines = []
    for line in base.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(key + '=') for key in overridden):
            continue
        kept_lines.append(line)
    prefix = '\n'.join(kept_lines)
    if prefix:
        prefix += '\n'
    return (
        prefix
        + '# WHP user overrides generated from .whpconfig; do not edit.\n'
        + f"CONFIG_MAC_NEWWORLD={values['CONFIG_MAC_NEWWORLD']}\n"
        + f"CONFIG_MAC_OLDWORLD={values['CONFIG_MAC_OLDWORLD']}\n"
    )


def write_ppc_device_config(base_path: pathlib.Path, path: pathlib.Path, state: ConfigState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = base_path.read_text(encoding='utf-8')
    content = render_ppc_device_config(state.values, base)
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(content, encoding='utf-8')
    os.replace(temp, path)


def sections() -> List[Tuple[str, List[Option]]]:
    result: List[Tuple[str, List[Option]]] = []
    for option in OPTIONS:
        if not result or result[-1][0] != option.section:
            result.append((option.section, []))
        result[-1][1].append(option)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--shell', metavar='CONFIG')
    group.add_argument('--write-ppc-devices', nargs=3, metavar=('CONFIG', 'BASE', 'OUTPUT'))
    group.add_argument('--dump-menu', action='store_true')
    args = parser.parse_args(argv)

    try:
        if args.shell:
            state = load_config(pathlib.Path(args.shell))
            sys.stdout.write(shell_assignments(state, dict(os.environ)))
            return 0
        if args.write_ppc_devices:
            config_path, base_path, output_path = args.write_ppc_devices
            state = load_config(pathlib.Path(config_path))
            write_ppc_device_config(pathlib.Path(base_path), pathlib.Path(output_path), state)
            return 0
        if args.dump_menu:
            for section, options in sections():
                print(section)
                for option in options:
                    print(f'  {option.key}={option.default}')
            return 0
    except (OSError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
