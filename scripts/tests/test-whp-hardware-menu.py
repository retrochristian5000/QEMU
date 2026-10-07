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
MINIKCONF = ROOT / 'scripts' / 'minikconf.py'
PPC_KCONFIG = ROOT / 'hw' / 'ppc' / 'Kconfig'
ISA_KCONFIG = ROOT / 'hw' / 'isa' / 'Kconfig'
AUDIO_KCONFIG = ROOT / 'hw' / 'audio' / 'Kconfig'
TIMER_KCONFIG = ROOT / 'hw' / 'timer' / 'Kconfig'
PPC_PREP = ROOT / 'hw' / 'ppc' / 'prep.c'
I82378 = ROOT / 'hw' / 'isa' / 'i82378.c'
sys.path.insert(0, str(CONFIG_DIR))

AUDIO_DEVICES = {
    'SB16': ('Sound Blaster 16 (ISA bus)', 'CONFIG_SB16'),
    'ADLIB': ('AdLib (ISA bus)', 'CONFIG_ADLIB'),
    'GUS': ('Gravis UltraSound (ISA bus)', 'CONFIG_GUS'),
    'CS4231A': ('Crystal CS4231A (ISA bus)', 'CONFIG_CS4231A'),
    'PCSPK': ('PC speaker', 'CONFIG_PCSPK'),
    'ES1370': ('Ensoniq ES1370 (PCI bus)', 'CONFIG_ES1370'),
    'AC97': ("Intel AC'97 (PCI bus)", 'CONFIG_AC97'),
    'CS4630': ('Crystal CS4630 (PCI bus)', 'CONFIG_CS4630'),
    'HDA': ('Intel HD Audio (PCI bus)', 'CONFIG_HDA'),
}

PPC_AUDIO_REQUIREMENTS = {
    'SB16': ('CONFIG_ISA_BUS',),
    'ADLIB': ('CONFIG_ISA_BUS',),
    'GUS': ('CONFIG_ISA_BUS',),
    'CS4231A': ('CONFIG_ISA_BUS',),
    'PCSPK': ('CONFIG_ISA_BUS', 'CONFIG_I8254'),
    'ES1370': ('CONFIG_PCI',),
    'AC97': ('CONFIG_PCI',),
    'CS4630': ('CONFIG_PCI',),
    'HDA': ('CONFIG_PCI',),
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

    def test_all_tracked_device_presets_parse_with_qemu_minikconf(self):
        minikconf = load_module(MINIKCONF, 'whp_qemu_minikconf_all_presets')
        presets = sorted((ROOT / 'configs/devices').glob('*/*.mak'))
        self.assertTrue(presets)
        for preset in presets:
            with self.subTest(preset=preset.relative_to(ROOT)):
                data = minikconf.KconfigData()
                with preset.open('rt', encoding='utf-8') as stream:
                    minikconf.KconfigParser.parse(stream, data)
    def test_config_prefix_validator_rejects_malformed_assignments(self):
        config = load_module(CONFIG_TOOL, 'whp_config_prefix_syntax')
        config.validate_device_config_syntax(
            '  # comment\n CONFIG_GOOD = y # trailing comment\nCONFIG_OTHER=n\n',
            'valid-preset',
        )
        malformed = {
            'CONFIG_=y\n': 'invalid QEMU device preset syntax',
            'CONFIG_lower=y\n': 'invalid QEMU device preset syntax',
            'CONFIG_BAD=1\n': 'invalid QEMU device preset syntax',
            'CONFIG_BAD\n': 'invalid QEMU device preset syntax',
            'CONFIG_DUP=y\nCONFIG_DUP=n\n': 'duplicate QEMU device preset symbol',
        }
        for text, message in malformed.items():
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, message):
                    config.validate_device_config_syntax(text, 'bad-preset')

    def test_bash_config_prefix_validator_reports_line_and_symbol(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            valid = root / 'valid.mak'
            invalid = root / 'invalid.mak'
            duplicate = root / 'duplicate.mak'
            valid.write_text(
                ' # comment\n CONFIG_FOO = y # comment\nCONFIG_BAR=n\n',
                encoding='utf-8',
            )
            invalid.write_text('CONFIG_FOO=y\nCONFIG_bad=y\n', encoding='utf-8')
            duplicate.write_text(
                'CONFIG_FOO=y\nCONFIG_FOO=n\n',
                encoding='utf-8',
            )
            script = f'''set -euo pipefail
source {CONFIGURE_BASH!s}
whp_configure_validate_device_config "$1"
'''
            subprocess.run(
                ['bash', '-c', script, '_', str(valid)],
                text=True,
                capture_output=True,
                check=True,
            )
            bad = subprocess.run(
                ['bash', '-c', script, '_', str(invalid)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn(f'{invalid}:2', bad.stderr)
            self.assertIn('CONFIG_bad=y', bad.stderr)
            dup = subprocess.run(
                ['bash', '-c', script, '_', str(duplicate)],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(dup.returncode, 0)
            self.assertIn(f'{duplicate}:2', dup.stderr)
            self.assertIn('CONFIG_FOO', dup.stderr)

    def test_generated_ppc_preset_is_accepted_by_qemu_minikconf(self):
        config = load_module(CONFIG_TOOL, 'whp_config_minikconf_contract')
        minikconf = load_module(MINIKCONF, 'whp_qemu_minikconf_contract')
        values = config.default_values()
        for suffix in AUDIO_DEVICES:
            values[f'PPC_AUDIO_{suffix}'] = 'y'
        generated = config.render_ppc_device_config(
            values,
            (ROOT / 'configs/devices/ppc-softmmu/default.mak').read_text(
                encoding='utf-8'
            ),
        )
        with tempfile.TemporaryDirectory() as td:
            preset = pathlib.Path(td) / 'whp-user.mak'
            preset.write_text(generated, encoding='utf-8')
            data = minikconf.KconfigData()
            with (ROOT / 'Kconfig').open('rt', encoding='utf-8') as stream:
                minikconf.KconfigParser.parse(stream, data)
            with preset.open('rt', encoding='utf-8') as stream:
                minikconf.KconfigParser.parse(stream, data)
            data.do_cmdline_assignment('CONFIG_PPC', True)
            data.do_cmdline_assignment('CONFIG_TARGET_BIG_ENDIAN', True)
            resolved = data.compute_config()
        for _, symbol in AUDIO_DEVICES.values():
            self.assertTrue(resolved[symbol.removeprefix('CONFIG_')], symbol)

    def test_ppc_audio_requirements_match_qemu_kconfig(self):        audio_kconfig = AUDIO_KCONFIG.read_text(encoding='utf-8')
        timer_kconfig = TIMER_KCONFIG.read_text(encoding='utf-8')
        config = load_module(CONFIG_TOOL, 'whp_config_ppc_requirement_table')
        table = {
            suffix: requirements
            for suffix, _, _, requirements in config.AUDIO_HARDWARE
        }
        self.assertEqual(table, PPC_AUDIO_REQUIREMENTS)

        for suffix, (_, symbol) in AUDIO_DEVICES.items():
            block = kconfig_block(audio_kconfig, symbol.removeprefix('CONFIG_'))
            direct = PPC_AUDIO_REQUIREMENTS[suffix][-1]
            self.assertIn(
                f"depends on {direct.removeprefix('CONFIG_')}",
                block,
                suffix,
            )
        self.assertIn(
            'depends on ISA_BUS',
            kconfig_block(timer_kconfig, 'I8254'),
        )

    def test_ppc_enabled_audio_adds_minimum_kconfig_requirements(self):
        config = load_module(CONFIG_TOOL, 'whp_config_ppc_requirements')
        base = (
            'CONFIG_ISA_BUS=n\n'
            'CONFIG_I8254=n\n'
            'CONFIG_PCI=n\n'
            'CONFIG_PCI_DEVICES=n\n'
            'CONFIG_MAC_NEWWORLD=y\n'
            'CONFIG_MAC_OLDWORLD=y\n'
        )
        representative = {
            'SB16': ('CONFIG_ISA_BUS',),
            'PCSPK': ('CONFIG_ISA_BUS', 'CONFIG_I8254'),
            'HDA': ('CONFIG_PCI',),
        }
        for suffix, requirements in representative.items():
            values = config.default_values()
            values[f'PPC_AUDIO_{suffix}'] = 'y'
            rendered = config.render_ppc_device_config(values, base)
            for requirement in requirements:
                self.assertIn(f'{requirement}=y', rendered)
                self.assertEqual(rendered.count(requirement + '='), 1)
            _, device_symbol = AUDIO_DEVICES[suffix]
            self.assertIn(f'{device_symbol}=y', rendered)
            self.assertIn('CONFIG_PCI_DEVICES=n', rendered)

    def test_ppc_disabled_audio_does_not_force_bus_requirements(self):
        config = load_module(CONFIG_TOOL, 'whp_config_ppc_no_requirements')
        values = config.default_values()
        values['PPC_AUDIO_SB16'] = 'n'
        rendered = config.render_ppc_device_config(
            values,
            'CONFIG_MAC_NEWWORLD=y\nCONFIG_MAC_OLDWORLD=y\n',
        )
        self.assertIn('CONFIG_SB16=n', rendered)
        self.assertNotIn('CONFIG_ISA_BUS=', rendered)
        self.assertNotIn('CONFIG_I8254=', rendered)
        self.assertNotIn('CONFIG_PCI=', rendered)

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

    def test_ppc_bash_preset_adds_audio_requirements(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            base = td_path / 'default.mak'
            output = td_path / 'whp-user.mak'
            base.write_text(
                'CONFIG_ISA_BUS=n\n'
                'CONFIG_I8254=n\n'
                'CONFIG_PCI=n\n'
                'CONFIG_PCI_DEVICES=n\n'
                'CONFIG_MAC_NEWWORLD=y\n'
                'CONFIG_MAC_OLDWORLD=y\n',
                encoding='utf-8',
            )
            script = f'''set -euo pipefail
source {CONFIGURE_BASH!s}
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
PPC_AUDIO_SB16=y
PPC_AUDIO_PCSPK=y
PPC_AUDIO_HDA=y
whp_configure_write_ppc_device_config "$1" "$2"
'''
            subprocess.run(
                ['bash', '-c', script, '_', str(base), str(output)],
                text=True,
                capture_output=True,
                check=True,
            )
            text = output.read_text(encoding='utf-8')

        for symbol in (
            'CONFIG_ISA_BUS', 'CONFIG_I8254', 'CONFIG_PCI',
            'CONFIG_SB16', 'CONFIG_PCSPK', 'CONFIG_HDA',
        ):
            self.assertEqual(text.count(symbol + '='), 1)
            self.assertIn(f'{symbol}=y', text)
        self.assertIn('CONFIG_PCI_DEVICES=n', text)

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
