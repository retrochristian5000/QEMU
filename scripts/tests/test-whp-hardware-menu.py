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
sys.path.insert(0, str(CONFIG_DIR))


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WhpHardwareMenuTests(unittest.TestCase):
    def test_audio_devices_live_under_generic_hardware_section(self):
        config = load_module(CONFIG_TOOL, 'whp_config_hardware')
        for key in (
            'I386_AUDIO_SB16',
            'I386_AUDIO_ADLIB',
            'I386_AUDIO_GUS',
            'I386_AUDIO_CS4231A',
            'I386_AUDIO_PCSPK',
            'I386_AUDIO_ES1370',
            'I386_AUDIO_AC97',
            'I386_AUDIO_CS4630',
            'I386_AUDIO_HDA',
        ):
            self.assertEqual(config.OPTION_BY_KEY[key].section, 'QEMU hardware')

    def test_es1370_groups_i386_and_ppc_target_choices(self):
        config = load_module(CONFIG_TOOL, 'whp_config_es1370_targets')
        self.assertIn('PPC_AUDIO_ES1370', config.OPTION_BY_KEY)
        i386 = config.OPTION_BY_KEY['I386_AUDIO_ES1370']
        ppc = config.OPTION_BY_KEY['PPC_AUDIO_ES1370']
        self.assertTrue(hasattr(i386, 'group'))
        self.assertEqual(i386.group, 'Ensoniq ES1370 (PCI)')
        self.assertEqual(ppc.group, i386.group)
        self.assertEqual(i386.label, 'i386')
        self.assertEqual(ppc.label, 'ppc')
        for option in (i386, ppc):
            self.assertEqual(option.kind, 'choice')
            self.assertEqual(option.default, 'auto')
            self.assertEqual(option.choices, ('auto', 'y', 'n'))

    def test_menu_dump_shows_one_es1370_group_with_two_targets(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = pathlib.Path(td) / '.whpconfig'
            config_path.write_text(
                'WHP_CONFIG_VERSION=2\n'
                'I386_AUDIO_ES1370=n\n'
                'PPC_AUDIO_ES1370=y\n',
                encoding='utf-8',
            )
            result = subprocess.run(
                [sys.executable, str(MENU_TOOL), str(config_path), '--dump'],
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertIn('QEMU hardware', result.stdout)
        self.assertEqual(result.stdout.count('Ensoniq ES1370 (PCI)'), 1)
        self.assertIn('<n>        i386', result.stdout)
        self.assertIn('<y>        ppc', result.stdout)

    def test_ppc_es1370_override_is_written_to_ppc_device_preset(self):
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
            script = f'''set -euo pipefail
source {CONFIGURE_BASH!s}
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
PPC_AUDIO_ES1370=n
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
        self.assertEqual(text.count('CONFIG_ES1370='), 1)
        self.assertIn('CONFIG_ES1370=n', text)

    def test_ppc_es1370_alone_selects_ppc_custom_preset(self):
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
PPC_AUDIO_ES1370=n
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
            self.assertIn('CONFIG_ES1370=n', preset.read_text(encoding='utf-8'))
            self.assertIn(
                '--with-devices-ppc=whp-user',
                (build_dir / 'configure-args.txt').read_text(encoding='utf-8'),
            )
            metadata = (build_dir / '.whp-config').read_text(encoding='utf-8')
            self.assertIn(
                'WHP_PPC_DEVICE_CONFIG_SIGNATURE=newworld=y;oldworld=y;es1370=n',
                metadata,
            )


if __name__ == '__main__':
    unittest.main()
