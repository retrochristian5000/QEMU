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

CONFIG_VERSION = '3'
SUPPORTED_CONFIG_VERSIONS = {'1', '2', '3'}


class Option(NamedTuple):
    key: str
    section: str
    label: str
    kind: str
    default: str
    choices: Tuple[str, ...] = ()
    group: str = ''


AUDIO_HARDWARE = (
    ('GAMEBLASTER', 'Creative Music System / Game Blaster (ISA bus)',
     'CONFIG_GAMEBLASTER', ('CONFIG_ISA_BUS',)),
    ('SB16', 'Creative Sound Blaster 16 and compatible profiles (ISA bus)',
     'CONFIG_SB16', ('CONFIG_ISA_BUS',)),
    ('ADLIB', 'AdLib (ISA bus)', 'CONFIG_ADLIB', ('CONFIG_ISA_BUS',)),
    ('GUS', 'Gravis UltraSound (ISA bus)', 'CONFIG_GUS', ('CONFIG_ISA_BUS',)),
    ('CS4231A', 'Crystal CS4231A (ISA bus)', 'CONFIG_CS4231A', ('CONFIG_ISA_BUS',)),
    # PCSPK depends on I8254, and I8254 itself depends on ISA_BUS.
    ('PCSPK', 'PC speaker', 'CONFIG_PCSPK', ('CONFIG_ISA_BUS', 'CONFIG_I8254')),
    ('ES1370', 'Ensoniq ES1370 (PCI bus)', 'CONFIG_ES1370', ('CONFIG_PCI',)),
    ('AC97', "Intel AC'97 (PCI bus)", 'CONFIG_AC97', ('CONFIG_PCI',)),
    ('CS4630', 'Crystal CS4630 (PCI bus)', 'CONFIG_CS4630', ('CONFIG_PCI',)),
    ('HDA', 'Intel HD Audio (PCI bus)', 'CONFIG_HDA', ('CONFIG_PCI',)),
)


# The WHP launcher exposes these three system-emulator toggles. This is not
# a promise to build every target supported by upstream QEMU.
SYSTEM_EMULATOR_KEYS = (
    'BUILD_QEMU_SYSTEM_I386',
    'BUILD_QEMU_SYSTEM_PPC',
    'BUILD_QEMU_SYSTEM_SPARC',
)

# These settings are active only in the native LLVM bootstrap. Hiding the
# group does not discard existing values in user-owned configuration files.
NATIVE_LLVM_DETAIL_KEYS = (
    'NATIVE_LLVM_CXX_STANDARD',
    'NATIVE_LLVM_PCH',
    'NATIVE_LLVM_MACOS_ARCH',
    'NATIVE_LLVM_ENABLE_LLDB',
    'NATIVE_LLVM_VALIDATE_ASAN',
    'NATIVE_LLVM_ASAN_AUTO_DEBUG',
    'NATIVE_LLVM_LINK_JOBS',
    'NATIVE_LLVM_COMPILE_JOBS',
    'NATIVE_LLVM_TABLEGEN_JOBS',
)

VISIBILITY_PARENT_KEYS = frozenset({
    'BUILD_QEMU_SYSTEM_ALL', 'BOOTSTRAP_NATIVE_LLVM',
})

LLVM_JOB_KEYS = frozenset({
    'NATIVE_LLVM_LINK_JOBS',
    'NATIVE_LLVM_COMPILE_JOBS',
    'NATIVE_LLVM_TABLEGEN_JOBS',
})


OPTIONS = (
    Option('BUILD_QEMU_IMG', 'Build outputs', 'qemu-img', 'bool', 'y'),
    Option('BUILD_QEMU_SYSTEM_ALL', 'Build outputs',
           'Build all WHP-supported system emulators (i386, PPC, SPARC)',
           'bool', 'n', group='System emulators'),
    Option('BUILD_QEMU_SYSTEM_I386', 'Build outputs', 'qemu-system-i386',
           'bool', 'y', group='System emulators'),
    Option('BUILD_QEMU_SYSTEM_PPC', 'Build outputs', 'qemu-system-ppc',
           'bool', 'y', group='System emulators'),
    Option('BUILD_QEMU_SYSTEM_SPARC', 'Build outputs', 'qemu-system-sparc',
           'bool', 'n', group='System emulators'),
    Option('QEMU_X86_FAMILY_LINK', 'Build outputs',
           'Use x86_64 system binary for i386 alias (POSIX)', 'bool', 'n'),
    Option('QEMU_HOST_LTO', 'Host features', 'Link-time optimization', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('QEMU_HOST_LTO_MODE', 'Host features', 'LTO mode (ThinLTO or full)', 'choice', 'auto', ('auto', 'thin', 'full')),
    Option('QEMU_HOST_PGO', 'Host features', 'QEMU host profile-guided optimization', 'choice', 'off', ('off', 'on')),
    Option('QEMU_PGO_TRAIN_SCRIPT', 'Host features',
           'PGO training script (manual or executable path)', 'string', 'manual'),
    Option('QEMU_HOST_MODULES', 'Host features', 'Dynamic QEMU modules', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('QEMU_HOST_OPTIMIZATION', 'Host features', 'QEMU host optimization level', 'choice', '2', ('0', '1', '2', '3', 'g', 's')),
    Option('QEMU_HOST_CPU_TUNING', 'Host features', 'QEMU host CPU tuning flags', 'string', 'native'),
    Option('QEMU_C_STANDARD', 'Host features', 'QEMU C language standard', 'choice', 'gnu11', ('gnu11', 'gnu17', 'gnu23')),
    Option('QEMU_CXX_STANDARD', 'Host features', 'QEMU C++ language standard', 'choice', 'gnu++23', ('gnu++17', 'gnu++20', 'gnu++23', 'c++26')),
    Option('BOOTSTRAP_NATIVE_LLVM', 'Host features',
           'Bootstrap/use WHP native LLVM', 'bool', 'n',
           group='Native LLVM bootstrap'),
    Option('NATIVE_LLVM_CXX_STANDARD', 'Host features',
           'Native LLVM C++ language standard', 'choice', '23',
           ('17', '20', '23', '26'), 'Native LLVM bootstrap'),
    Option('NATIVE_LLVM_PCH', 'Host features', 'Native LLVM precompiled headers',
           'choice', 'auto', ('auto', 'y', 'n'), 'Native LLVM bootstrap'),
    Option('NATIVE_LLVM_MACOS_ARCH', 'Host features', 'Native LLVM executable ABI (macOS; not QEMU host)',
           'choice', 'auto', ('auto', 'arm64', 'arm64e', 'x86_64'), 'Native LLVM bootstrap'),
    Option('NATIVE_LLVM_ENABLE_LLDB', 'Host features', 'Build LLVM LLDB debugger',
           'choice', 'auto', ('auto', 'y', 'n'), 'Native LLVM bootstrap'),
    Option('NATIVE_LLVM_VALIDATE_ASAN', 'Host features',
           'Validate native LLVM ASan (macOS)', 'choice', 'auto',
           ('auto', 'y', 'n'), 'Native LLVM bootstrap'),
    Option('NATIVE_LLVM_ASAN_AUTO_DEBUG', 'Host features',
           'LLDB replay on LLVM ASan failures (macOS)', 'bool', 'n',
           group='Native LLVM bootstrap'),
    Option('NATIVE_LLVM_LINK_JOBS', 'Host features',
           'LLVM parallel linker jobs (auto or positive integer)',
           'string', 'auto', group='Native LLVM bootstrap'),
    Option('NATIVE_LLVM_COMPILE_JOBS', 'Host features',
           'LLVM compile job pool (auto, 0=unlimited, or positive integer)',
           'string', 'auto', group='Native LLVM bootstrap'),
    Option('NATIVE_LLVM_TABLEGEN_JOBS', 'Host features',
           'LLVM TableGen job pool (auto, 0=unlimited, or positive integer)',
           'string', 'auto', group='Native LLVM bootstrap'),
    Option('BOOTSTRAP_PYTHON', 'Host features', 'Bootstrap/use WHP Python', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_BASH', 'Host features', 'Bootstrap/use WHP Bash', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_AUTOMAKE', 'Host features', 'Bootstrap/use WHP Automake', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_AUTOCONF', 'Host features', 'Bootstrap/use WHP Autoconf', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_PERL', 'Host features', 'Bootstrap/use WHP Perl', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_GAWK', 'Host features', 'Bootstrap/use WHP Gawk', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_MAKE', 'Host features', 'Bootstrap/use WHP GNU Make', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_SED', 'Host features', 'Bootstrap/use WHP GNU sed', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_GIT', 'Host features', 'Bootstrap/use WHP Git', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_NINJA', 'Host features', 'Bootstrap/use WHP Ninja', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_CMAKE', 'Host features', 'Bootstrap/use WHP CMake', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_GLIB', 'Host features', 'Bootstrap/use WHP GLib (development)', 'choice', 'n', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_SDL', 'Host features', 'Bootstrap/use WHP SDL3', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_JACK', 'Host features', 'Bootstrap/use WHP JACK', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_ZLIB', 'Host features', 'Bootstrap/use WHP zlib', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_LIBTOOL', 'Host features', 'Bootstrap/use WHP Libtool', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('BOOTSTRAP_LIBISOFS', 'Host features', 'Bootstrap/use WHP libisofs', 'choice', 'auto', ('auto', 'y', 'n')),
    # The managed sccacher bootstrap is a cache provider, not a second
    # independent toggle. Legacy BOOTSTRAP_SCCACHE profiles migrate below.
    Option('COMPILER_CACHE', 'Host features', 'Compiler cache', 'choice',
           'auto', ('auto', 'ccache', 'sccache', 'managed-sccache', 'none')),
    Option('QEMU_HOST_LINKER', 'Host features', 'QEMU host linker (system = compiler default)', 'choice', 'auto', ('auto', 'system', 'lld', 'mold')),
    Option('BOOTSTRAP_MOLD', 'Host features', 'Managed mold bootstrap/use (Bash runner)', 'choice', 'auto', ('auto', 'y', 'n')),
    Option('WHP_MESON_PROVIDER', 'Host features', 'QEMU Meson provider', 'choice', 'fork', ('venv', 'fork')),
    Option('QEMU_FDT_MODE', 'Host features', 'QEMU libfdt provider', 'choice', 'auto', ('auto', 'system', 'internal', 'enabled', 'disabled')),
    Option('WHP_DTC_FETCH_MISSING', 'Host features', 'Prefetch missing pinned DTC checkout', 'bool', 'n'),
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
    Option('QEMU_TEST_SCOPE', 'Build behavior', 'QEMU test scope', 'choice', 'changed', ('changed', 'full')),
    Option('INSTALL_AFTER_BUILD', 'Build behavior', 'Install after build', 'bool', 'n'),
    Option('INSTALL_RUNTIME_BASH', 'Build behavior', 'Install managed Bash for host-side scripts', 'bool', 'n'),
    Option('MACOS_BUILD_POWER', 'Build behavior', 'macOS compile power profile', 'choice', 'balanced', ('eco', 'balanced', 'performance')),
    Option('CONFIG_MAC_NEWWORLD', 'QEMU machines', 'New World Macintosh', 'bool', 'y'),
    Option('CONFIG_MAC_OLDWORLD', 'QEMU machines', 'Old World Macintosh', 'bool', 'y'),
    *tuple(
        option
        for suffix, group, _, _ in AUDIO_HARDWARE
        for option in (
            Option(
                f'I386_AUDIO_{suffix}', 'QEMU hardware', 'i386', 'choice',
                'auto', ('auto', 'y', 'n'), group,
            ),
            Option(
                f'PPC_AUDIO_{suffix}', 'QEMU hardware', 'ppc', 'choice',
                'auto', ('auto', 'y', 'n'), group,
            ),
        )
    ),
)

OPTION_BY_KEY = {option.key: option for option in OPTIONS}
PORTABLE_BOOL_KEYS = {option.key for option in OPTIONS if option.kind == 'bool'}
RAW_CONFIG_KEYS = {'CONFIG_MAC_NEWWORLD', 'CONFIG_MAC_OLDWORLD'}
SHELL_BOOL_KEYS = PORTABLE_BOOL_KEYS - RAW_CONFIG_KEYS
SHELL_TRI_STATE_KEYS = {
    'NATIVE_LLVM_PCH',
    'NATIVE_LLVM_ENABLE_LLDB',
    'NATIVE_LLVM_VALIDATE_ASAN',
    'QEMU_HOST_LTO',
    'QEMU_HOST_MODULES',
    'BOOTSTRAP_PYTHON',
    'BOOTSTRAP_BASH',
    'BOOTSTRAP_AUTOMAKE',
    'BOOTSTRAP_AUTOCONF',
    'BOOTSTRAP_PERL',
    'BOOTSTRAP_GAWK',
    'BOOTSTRAP_MAKE',
    'BOOTSTRAP_SED',
    'BOOTSTRAP_GIT',
    'BOOTSTRAP_NINJA',
    'BOOTSTRAP_CMAKE',
    'BOOTSTRAP_GLIB',
    'BOOTSTRAP_SDL',
    'BOOTSTRAP_JACK',
    'BOOTSTRAP_ZLIB',
    'BOOTSTRAP_LIBTOOL',
    'BOOTSTRAP_LIBISOFS',
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
_KEY_RE = re.compile(r'[A-Z][A-Z0-9_]*\Z')
_DEVICE_CONFIG_LINE_RE = re.compile(
    r'\s*(CONFIG_[A-Z0-9_]+)\s*=\s*([yn])(?:\s*#.*)?\s*\Z'
)


class ConfigState:
    def __init__(self, values: Dict[str, str], unknown: Optional[Dict[str, str]] = None):
        self.values = values
        self.unknown = OrderedDict(unknown or {})


def default_values() -> Dict[str, str]:
    return {option.key: option.default for option in OPTIONS}


def visible_options(values: Dict[str, str]) -> Tuple[Option, ...]:
    """Hide individual emulator toggles under the all-targets switch.

    Their saved values are retained and take effect again when it is disabled.
    """
    hidden = set()
    if values.get('BUILD_QEMU_SYSTEM_ALL', 'n') == 'y':
        hidden.update(SYSTEM_EMULATOR_KEYS)
    if values.get('BOOTSTRAP_NATIVE_LLVM', 'n') != 'y':
        hidden.update(NATIVE_LLVM_DETAIL_KEYS)
    return tuple(option for option in OPTIONS if option.key not in hidden)


def validate_value(option: Option, value: str) -> None:
    if option.key in LLVM_JOB_KEYS:
        # auto inherits bootstrap defaults; TableGen/compile allow 0 to
        # disable their pool limit. Link jobs must always be positive.
        if value == 'auto':
            return
        if not re.fullmatch(r'(0|[1-9][0-9]*)', value):
            raise ValueError(f'{option.key} must be auto or a nonnegative integer')
        if option.key == 'NATIVE_LLVM_LINK_JOBS' and value == '0':
            raise ValueError('NATIVE_LLVM_LINK_JOBS must be auto or a positive integer')
        return
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



def validate_combinations(values: Dict[str, str]) -> None:
    """Reject conflicting menu choices before QEMU reaches build stages.

    Keep this host-neutral: platform-specific and guest configurations are
    evaluated by their actual toolchain adapters after menu validation.
    """
    if values['QEMU_TSAN'] == 'y' and (
        values['QEMU_ASAN'] == 'y' or values['QEMU_UBSAN'] == 'y'
    ):
        raise ValueError(
            'QEMU_TSAN=y cannot be combined with QEMU_ASAN=y or QEMU_UBSAN=y; '
            'disable ThreadSanitizer or the other sanitizers'
        )
    linker = values['QEMU_HOST_LINKER']
    if linker in ('system', 'lld') and values['BOOTSTRAP_MOLD'] == 'y':
        raise ValueError(
            f'QEMU_HOST_LINKER={linker} conflicts with BOOTSTRAP_MOLD=y; '
            'select auto or n for managed mold, or select mold or auto as linker'
        )
    if values['QEMU_HOST_LTO'] == 'n' and values['QEMU_HOST_LTO_MODE'] != 'auto':
        raise ValueError(
            f"QEMU_HOST_LTO_MODE={values['QEMU_HOST_LTO_MODE']} conflicts with "
            'QEMU_HOST_LTO=n; enable LTO or select LTO mode auto'
        )
    if (values['BOOTSTRAP_NATIVE_LLVM'] == 'y' and
            values['NATIVE_LLVM_ASAN_AUTO_DEBUG'] == 'y'):
        if values['NATIVE_LLVM_ENABLE_LLDB'] == 'n':
            raise ValueError(
                'NATIVE_LLVM_ASAN_AUTO_DEBUG=y needs NATIVE_LLVM_ENABLE_LLDB=y '
                'or auto; disable replay or enable LLDB'
            )
        if values['NATIVE_LLVM_VALIDATE_ASAN'] == 'n':
            raise ValueError(
                'NATIVE_LLVM_ASAN_AUTO_DEBUG=y needs ASan validation; '
                'set NATIVE_LLVM_VALIDATE_ASAN=auto or y'
            )


def load_config(path: pathlib.Path) -> ConfigState:
    values = default_values()
    unknown: OrderedDict[str, str] = OrderedDict()
    if not path.exists():
        return ConfigState(values, unknown)

    config_version: Optional[str] = None
    seen_options = set()
    legacy_target_list = None
    legacy_install_after_build = None
    legacy_bootstrap_sccache = None
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
        if key == 'INSTALL':
            if value not in ('y', 'n'):
                raise ValueError(f'{path}:{number}: INSTALL must be y or n')
            legacy_install_after_build = value
            continue
        if key == 'BOOTSTRAP_SCCACHE':
            if value not in ('y', 'n'):
                raise ValueError(
                    f'{path}:{number}: legacy BOOTSTRAP_SCCACHE must be y or n'
                )
            legacy_bootstrap_sccache = value
            continue
        option = OPTION_BY_KEY.get(key)
        if option is None:
            unknown[key] = value
            continue
        # Older configurations stored a compilation stage as the user policy.
        # Migrate in memory; never rewrite a user-owned file during loading.
        if key == 'QEMU_HOST_PGO' and value in ('generate', 'use'):
            value = 'on'
        validate_value(option, value)
        values[key] = value
        seen_options.add(key)

    if (
        legacy_install_after_build is not None
        and 'INSTALL_AFTER_BUILD' not in seen_options
    ):
        values['INSTALL_AFTER_BUILD'] = legacy_install_after_build

    if legacy_bootstrap_sccache == 'y':
        cache = values['COMPILER_CACHE']
        if cache not in ('auto', 'sccache', 'managed-sccache'):
            raise ValueError(
                f'{path}: BOOTSTRAP_SCCACHE=y conflicts with '
                f'COMPILER_CACHE={cache}; select a compatible cache provider'
            )
        values['COMPILER_CACHE'] = 'managed-sccache'

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
    elif config_version in ('1', '2'):
        print(
            f'warning: {path} uses WHP_CONFIG_VERSION={config_version}; '
            'portable defaults are migrated in memory',
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
    validate_combinations(state.values)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(render_config(state), encoding='utf-8')
    os.replace(temp, path)


def shell_assignments(state: ConfigState, environ: Dict[str, str]) -> str:
    # Environment overrides are per-run repairs, so validate the effective
    # settings instead of rejecting a saved profile already overridden.
    effective = dict(state.values)
    for key in ('QEMU_TSAN', 'QEMU_ASAN', 'QEMU_UBSAN',
                'QEMU_HOST_LTO', 'QEMU_HOST_LTO_MODE',
                'QEMU_HOST_LINKER', 'BOOTSTRAP_MOLD',
                'BOOTSTRAP_NATIVE_LLVM', 'NATIVE_LLVM_ENABLE_LLDB',
                'NATIVE_LLVM_VALIDATE_ASAN', 'NATIVE_LLVM_ASAN_AUTO_DEBUG'):
        if key in environ:
            raw = environ[key] or OPTION_BY_KEY[key].default
            effective[key] = {'1': 'y', '0': 'n'}.get(raw, raw)
            if key in ('QEMU_HOST_LINKER', 'BOOTSTRAP_MOLD'):
                validate_value(OPTION_BY_KEY[key], effective[key])
    validate_combinations(effective)
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


def validate_device_config_syntax(text: str, source: str = '<generated>') -> None:
    seen = set()
    for number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        match = _DEVICE_CONFIG_LINE_RE.fullmatch(raw_line)
        if match is None:
            raise ValueError(
                f'{source}:{number}: invalid QEMU device preset syntax: '
                f'{raw_line!r}; expected CONFIG_<UPPERCASE_SYMBOL>=y|n'
            )
        symbol = match.group(1)
        if symbol in seen:
            raise ValueError(
                f'{source}:{number}: duplicate QEMU device preset symbol: {symbol}'
            )
        seen.add(symbol)

def render_ppc_device_config(values: Dict[str, str], base: str) -> str:
    overridden = {'CONFIG_MAC_NEWWORLD', 'CONFIG_MAC_OLDWORLD'}
    ppc_values = []
    required_symbols: List[str] = []
    for suffix, _, symbol, requirements in AUDIO_HARDWARE:
        value = values.get(f'PPC_AUDIO_{suffix}', 'auto')
        ppc_values.append((symbol, value))
        if value != 'auto':
            overridden.add(symbol)
        if value == 'y':
            for requirement in requirements:
                if requirement not in required_symbols:
                    required_symbols.append(requirement)
                    overridden.add(requirement)

    kept_lines = []
    for line in base.splitlines():
        # Keep the Python menu path consistent with the Bash configure path:
        # Kconfig assignments can have whitespace around '='.  Match the
        # parsed symbol, not a literal 'CONFIG_NAME=' prefix, so an explicit
        # override cannot leave a conflicting indented base assignment.
        match = _DEVICE_CONFIG_LINE_RE.fullmatch(line)
        if match is not None and match.group(1) in overridden:
            continue
        kept_lines.append(line)
    prefix = '\n'.join(kept_lines)
    if prefix:
        prefix += '\n'
    result = (
        prefix
        + '# WHP user overrides generated from .whpconfig; do not edit.\n'
        + f"CONFIG_MAC_NEWWORLD={values['CONFIG_MAC_NEWWORLD']}\n"
        + f"CONFIG_MAC_OLDWORLD={values['CONFIG_MAC_OLDWORLD']}\n"
    )
    for requirement in required_symbols:
        result += f'{requirement}=y\n'
    for symbol, value in ppc_values:
        if value != 'auto':
            result += f'{symbol}={value}\n'
    validate_device_config_syntax(result, 'generated PPC device preset')
    return result


def write_ppc_device_config(base_path: pathlib.Path, path: pathlib.Path, state: ConfigState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = base_path.read_text(encoding='utf-8')
    content = render_ppc_device_config(state.values, base)
    if path.exists() and path.read_text(encoding='utf-8') == content:
        return
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(content, encoding='utf-8')
    os.replace(temp, path)


def sections(values: Optional[Dict[str, str]] = None) -> List[Tuple[str, List[Option]]]:
    result: List[Tuple[str, List[Option]]] = []
    source = OPTIONS if values is None else visible_options(values)
    for option in source:
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
