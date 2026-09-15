#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
CONFIG_TOOL = CONFIG_DIR / 'config.py'
MENU_TOOL = CONFIG_DIR / 'menuconfig.py'
CONFIGURE_BASH = ROOT / 'scripts' / 'whp-build' / 'configure.bash'
PPC_KCONFIG = ROOT / 'hw' / 'ppc' / 'Kconfig'
ISA_KCONFIG = ROOT / 'hw' / 'isa' / 'Kconfig'
PPC_PREP = ROOT / 'hw' / 'ppc' / 'prep.c'
I82378 = ROOT / 'hw' / 'isa' / 'i82378.c'
sys.path.insert(0, str(CONFIG_DIR))

AUDIO_DEVICES = {
    'SB16': ('Sound Blaster 16 (ISA)', 'CONFIG_SB16'),
    'ADLIB': ('AdLib (ISA)', 'CONFIG_ADLIB'),
    'GUS': ('Gravis UltraSound (ISA)', 'CONFIG_GUS'),
    'CS4231A': ('Crystal CS4231A (ISA)', 'CONFIG_CS4231A'),
    'PCSPK': ('PC speaker', 'CONFIG_PCSPK'),
    'ES1370': ('Ensoniq ES1370 (PCI)', 'CONFIG_ES1370'),
    'AC97': ("Intel AC'97 (PCI)", 'CONFIG_AC97'),
    'CS4630': ('Crystal CS4630 (PCI)', 'CONFIG_CS4630'),
    'HDA': ('Intel HD Audio (PCI)', 'CONFIG_HDA'),
}


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def kconfig_block(text: str, symbol: str) -> str:
    marker = f'config {symbol}\n'
    block = text.split(marker, 1)[1]
    return block.split('\nconfig ', 1)[0]


class WhpHardwareMenuTests(unittest.TestCase):
    def test_all_audio_devices_group_i386_and_ppc_choices(self):
        config = load_module(CONFIG_TOOL, 'whp_config_hardware')
        for suffix, (group, _) in AUDIO_DEVICES.items():
            i386_key = f'I386_AUDIO_{suffix}'
            ppc_key = f'PPC_AUDIO_{suffix}'
            self.assertIn(i386_key, config.OPTION_BY_KEY)
            self.assertIn(ppc_key, config.OPTION_BY_KEY)
            i386 = config.OPTION_BY_KEY[i386_key]
            ppc = config.OPTION_BY_KEY[ppc_key]
            self.assertEqual(i386.section, 'QEMU hardware')
            self.assertEqual(ppc.section, 'QEMU hardware')
            self.assertEqual(i386.group, group)
            self.assertEqual(ppc.group, group)
            self.assertEqual(i386.label, 'i386')
            self.assertEqual(ppc.label, 'ppc')
            for option in (i386, ppc):
                self.assertEqual(option.kind, 'choice')
                self.assertEqual(option.default, 'auto')
                self.assertEqual(option.choices, ('auto', 'y', 'n'))

    def test_menu_dump_shows_each_device_once_with_two_targets(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = pathlib.Path(td) / '.whpconfig'
            config_path.write_text(
                'WHP_CONFIG_VERSION=2\n'
                'I386_AUDIO_SB16=n\n'
                'PPC_AUDIO_SB16=y\n'
                'I386_AUDIO_HDA=y\n'
                'PPC_AUDIO_HDA=n\n',
                encoding='utf-8',
            )
            result = subprocess.run(
                [sys.executable, str(MENU_TOOL), str(config_path), '--dump'],
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertIn('QEMU hardware', result.stdout)
        for group, _ in AUDIO_DEVICES.values():
            self.assertEqual(result.stdout.count(group), 1)
        self.assertIn('<n>        i386', result.stdout)
        self.assertIn('<y>        ppc', result.stdout)

    def test_ppc_auto_preserves_upstream_audio_defaults(self):
        config = load_module(CONFIG_TOOL, 'whp_config_ppc_auto')
        values = config.default_values()
        base_lines = ['# PPC defaults']
        for _, symbol in AUDIO_DEVICES.values():
            base_lines.append(f'{symbol}=y')
        base_lines.extend(('CONFIG_MAC_NEWWORLD=y', 'CONFIG_MAC_OLDWORLD=y'))
        rendered = config.render_ppc_device_config(values, '\n'.join(base_lines) + '\n')
        for _, symbol in AUDIO_DEVICES.values():
            self.assertIn(f'{symbol}=y', rendered)
            self.assertEqual(rendered.count(symbol + '='), 1)

    def test_ppc_audio_overrides_are_written_to_ppc_device_preset(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            base = td_path / 'default.mak'
            output = td_path / 'whp-user.mak'
            base.write_text(
                '# PPC defaults\n'
                'CONFIG_MAC_NEWWORLD=y\n'
                'CONFIG_MAC_OLDWORLD=y\n',
                encoding='utf-8',
            )
            assignments = '\n'.join(
                f'PPC_AUDIO_{suffix}=n' for suffix in AUDIO_DEVICES
            )
            script = f'''set -euo pipefail
source {CONFIGURE_BASH!s}
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
{assignments}
whp_configure_write_ppc_device_config "$1" "$2"
'''
            subprocess.run(
                ['bash', '-c', script, '_', str(base), str(output)],
                text=True,
                capture_output=True,
                check=True,
            )
            text = output.read_text(encoding='utf-8')

        self.assertIn('CONFIG_MAC_NEWWORLD=y', text)
        self.assertIn('CONFIG_MAC_OLDWORLD=y', text)
        for _, symbol in AUDIO_DEVICES.values():
            self.assertEqual(text.count(symbol + '='), 1)
            self.assertIn(f'{symbol}=n', text)

    def test_ppc_audio_hard_dependencies_are_optional(self):
        prep_kconfig = kconfig_block(PPC_KCONFIG.read_text(encoding='utf-8'), 'PREP')
        i82378_kconfig = kconfig_block(ISA_KCONFIG.read_text(encoding='utf-8'), 'I82378')
        prep_source = PPC_PREP.read_text(encoding='utf-8')
        i82378_source = I82378.read_text(encoding='utf-8')

        self.assertIn('imply CS4231A', prep_kconfig)
        self.assertNotIn('select CS4231A', prep_kconfig)
        self.assertIn('imply PCSPK', i82378_kconfig)
        self.assertNotIn('select PCSPK', i82378_kconfig)
        self.assertIn('isa_dev = isa_try_new("cs4231a");', prep_source)
        self.assertIn('pcspk = isa_try_new(TYPE_PC_SPEAKER);', i82378_source)

    def test_ppc_audio_choice_alone_selects_ppc_custom_preset(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            source_dir = td_path / 'source'
            build_dir = td_path / 'build'
            device_dir = source_dir / 'configs' / 'devices' / 'ppc-softmmu'
            device_dir.mkdir(parents=True)
            build_dir.mkdir()
            (device_dir / 'default.mak').write_text(
                '# PPC defaults\n'
                'CONFIG_MAC_NEWWORLD=y\n'
                'CONFIG_MAC_OLDWORLD=y\n',
                encoding='utf-8',
            )
            configure = source_dir / 'configure'
            configure.write_text(
                '#!/bin/sh\n'
                'printf "%s\\n" "$@" > configure-args.txt\n'
                'touch build.ninja\n',
                encoding='utf-8',
            )
            configure.chmod(0o755)

            script = f'''set -euo pipefail
SOURCE_DIR="$1"
BUILD_DIR="$2"
HOST_OS=Linux
PROCESS_ARCH=x86_64
PHYSICAL_ARCH=x86_64
HOST_ARCH=x86_64
ROSETTA_TRANSLATED=0
MACOS_ALLOW_ROSETTA=0
MACOS_VERIFY_TOOLCHAIN=0
MACOS_ALLOW_NONCLANG=0
MACOS_ALLOW_COMPILER_CONFIG=0
MACOS_COMPILER_MANIFEST=disabled
MACOS_COMPILER_MANIFEST_SIGNATURE=disabled
MACOS_LTO_MANIFEST=disabled
MACOS_LTO_MANIFEST_SIGNATURE=disabled
CC_FOR_BUILD=cc
CXX_FOR_BUILD=c++
OBJC_FOR_BUILD=cc
STRIP_FOR_BUILD=strip
PKG_CONFIG_FOR_BUILD=pkg-config
CFLAGS=
MAKE_CMD=make
NINJA_CMD=ninja
QEMU_HOST_LTO=auto
BUILD_OPENBIOS=0
OPENBIOS_CROSS_COMPILE=
BOOTSTRAP_POWERPC_TOOLCHAIN=0
POWERPC_TOOLCHAIN_DIR="$2/powerpc"
QEMU_TARGET_LIST=ppc-softmmu
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
PPC_AUDIO_HDA=n
configure_args=(--target-list=ppc-softmmu)
source {CONFIGURE_BASH!s}
whp_configure_build
'''
            subprocess.run(
                ['bash', '-c', script, '_', str(source_dir), str(build_dir)],
                text=True,
                capture_output=True,
                check=True,
            )

            preset = device_dir / 'whp-user.mak'
            self.assertTrue(preset.is_file())
            self.assertIn('CONFIG_HDA=n', preset.read_text(encoding='utf-8'))
            self.assertIn(
                '--with-devices-ppc=whp-user',
                (build_dir / 'configure-args.txt').read_text(encoding='utf-8'),
            )
            metadata = (build_dir / '.whp-config').read_text(encoding='utf-8')
            self.assertIn('hda=n', metadata)


if __name__ == '__main__':
    unittest.main()
