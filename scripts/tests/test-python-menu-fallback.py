#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'scripts' / 'whp-config' / 'config.py'
SCHEMA = ROOT / 'scripts' / 'whp-config' / 'menu-options.def'
SHELL_MENU = ROOT / 'scripts' / 'whp-config' / 'menuconfig.sh'
BUILD = ROOT / 'build.sh'


def load_config():
    spec = importlib.util.spec_from_file_location('whp_shell_menu_config', CONFIG)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def schema_rows():
    rows = []
    for raw in SCHEMA.read_text(encoding='utf-8').splitlines():
        if not raw or raw.startswith('#'):
            continue
        key, section, label, kind, default, choices, group = raw.split('|', 6)
        rows.append((
            key,
            section,
            label,
            kind,
            default,
            tuple(filter(None, choices.split(','))),
            group,
        ))
    return rows


config = load_config()
expected = [
    (
        option.key,
        option.section,
        option.label,
        option.kind,
        option.default,
        option.choices,
        option.group,
    )
    for option in config.OPTIONS
]
assert schema_rows() == expected, 'shell menu schema drifted from config.py'

python_option = config.OPTION_BY_KEY['BOOTSTRAP_PYTHON']
assert python_option.section == 'Host features'
assert python_option.kind == 'choice'
assert python_option.default == 'auto'
assert python_option.choices == ('auto', 'y', 'n')

build = BUILD.read_text(encoding='utf-8')
menu = build.index('if [ "${1:-}" = menuconfig ]; then')
bootstrap = build.index('PYTHON=$(/bin/sh "$SOURCE_DIR/scripts/bootstrap-python.sh")')
assert menu < bootstrap, 'menuconfig still depends on bootstrapping Python first'
assert 'WHP_MENUCONFIG_SHELL=' in build
assert 'BOOTSTRAP_PYTHON' in build
assert 'elif [ "$BOOTSTRAP_PYTHON" = 1 ]; then' in build
assert 'if [ "$BOOTSTRAP_PYTHON" = 0 ]; then' in build

subprocess.run(['/bin/sh', '-n', str(SHELL_MENU)], check=True)
print('WHP no-Python menuconfig fallback: verified')
