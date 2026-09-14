#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
MENU_TOOL = ROOT / 'scripts' / 'whp-config' / 'menuconfig.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
PORTABLE_ENTRY_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build-entry.py'
CONFIGURE_BASH = ROOT / 'scripts' / 'whp-build' / 'configure.bash'

AUDIO_OPTIONS = {
    'I386_AUDIO_SB16': ('Sound Blaster 16 (ISA)', 'CONFIG_SB16'),
    'I386_AUDIO_ADLIB': ('AdLib (ISA)', 'CONFIG_ADLIB'),
    'I386_AUDIO_GUS': ('Gravis UltraSound (ISA)', 'CONFIG_GUS'),
    'I386_AUDIO_CS4231A': ('Crystal CS4231A (ISA)', 'CONFIG_CS4231A'),
    'I386_AUDIO_PCSPK': ('PC speaker', 'CONFIG_PCSPK'),
    'I386_AUDIO_ES1370': ('Ensoniq ES1370 (PCI)', 'CONFIG_ES1370'),
    'I386_AUDIO_AC97': ("Intel AC'97 (PCI)", 'CONFIG_AC97'),
    'I386_AUDIO_CS4630': ('Crystal CS4630 (PCI)', 'CONFIG_CS4630'),
    'I386_AUDIO_HDA': ('Intel HD Audio (PCI)', 'CONFIG_HDA'),
}


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WhpI386AudioMenuTests(unittest.TestCase):
    def test_audio_options_are_target_scoped_tristates(self):
        config = load_module(CONFIG_TOOL, 'whp_config_i386_audio')
        for key, (label, _) in AUDIO_OPTIONS.items():
            option = config.OPTION_BY_KEY[key]
            self.assertEqual(option.section, 'QEMU i386 audio hardware')
            self.assertEqual(option.label, label)
            self.assertEqual(option.kind, 'choice')
            self.assertEqual(option.default, 'auto')
            self.assertEqual(option.choices, ('auto', 'y', 'n'))

    def test_auto_preserves_qemu_defaults_and_explicit_values_export_raw(self):
        config = load_module(CONFIG_TOOL, 'whp_config_i386_audio_shell')
        values = config.default_values()
        assignments = config.shell_assignments(config.ConfigState(values), {})
        for key in AUDIO_OPTIONS:
            self.assertNotIn(f'{key}=', assignments)

        values['I386_AUDIO_SB16'] = 'n'
        values['I386_AUDIO_HDA'] = 'y'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertIn("I386_AUDIO_SB16='n'", assignments)
        self.assertIn("I386_AUDIO_HDA='y'", assignments)

    def test_menu_dump_exposes_sound_blaster_and_audio_section(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = pathlib.Path(td) / '.whpconfig'
            config_path.write_text(
                'WHP_CONFIG_VERSION=2\nI386_AUDIO_SB16=n\n',
                encoding='utf-8',
            )
            result = subprocess.run(
                [sys.executable, str(MENU_TOOL), str(config_path), '--dump'],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
        self.assertIn('QEMU i386 audio hardware', result.stdout)
        self.assertIn('<n>        Sound Blaster 16 (ISA)', result.stdout)
        self.assertIn('<auto>     Intel HD Audio (PCI)', result.stdout)

    def test_kconfig_preset_contains_only_explicit_audio_overrides(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            base = td_path / 'default.mak'
            output = td_path / 'whp-user.mak'
            base.write_text(
                '# repository defaults\n'
                'CONFIG_TEST_DEVICES=n\n'
                'CONFIG_SB16=y\n'
                'CONFIG_HDA=n\n',
                encoding='utf-8',
            )
            script = f'''set -euo pipefail
source {CONFIGURE_BASH!s}
I386_AUDIO_SB16=n
I386_AUDIO_HDA=y
whp_configure_write_i386_audio_config "$1" "$2"
whp_configure_i386_audio_signature
'''
            result = subprocess.run(
                ['bash', '-c', script, '_', str(base), str(output)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            text = output.read_text(encoding='utf-8')

        self.assertIn('CONFIG_TEST_DEVICES=n', text)
        self.assertEqual(text.count('CONFIG_SB16='), 1)
        self.assertEqual(text.count('CONFIG_HDA='), 1)
        self.assertIn('CONFIG_SB16=n', text)
        self.assertIn('CONFIG_HDA=y', text)
        self.assertNotIn('CONFIG_ADLIB=', text)
        self.assertEqual(
            result.stdout.strip(),
            'sb16=n;adlib=auto;gus=auto;cs4231a=auto;pcspk=auto;'
            'es1370=auto;ac97=auto;cs4630=auto;hda=y',
        )

    def test_configure_keeps_i386_preset_for_meson_regeneration(self):
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            source_dir = td_path / 'source'
            build_dir = td_path / 'build'
            device_dir = source_dir / 'configs' / 'devices' / 'i386-softmmu'
            device_dir.mkdir(parents=True)
            build_dir.mkdir()
            (device_dir / 'default.mak').write_text(
                '# i386 defaults\nCONFIG_TEST_DEVICES=n\n',
                encoding='utf-8',
            )
            configure = source_dir / 'configure'
            configure.write_text(
                '#!/bin/sh\n'
                'count=0\n'
                'test ! -f configure-count.txt || read count < configure-count.txt\n'
                'count=$((count + 1))\n'
                'printf "%s\\n" "$count" > configure-count.txt\n'
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
QEMU_TARGET_LIST=i386-softmmu
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
I386_AUDIO_SB16=n
configure_args=(--target-list=i386-softmmu)
source {CONFIGURE_BASH!s}
whp_configure_build
'''
            preset = device_dir / 'whp-user.mak'
            for run in range(2):
                subprocess.run(
                    ['bash', '-c', script, '_', str(source_dir), str(build_dir)],
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                if run == 0:
                    self.assertTrue(preset.is_file())
                    preset.unlink()

            self.assertTrue(preset.is_file())
            self.assertIn('CONFIG_SB16=n', preset.read_text(encoding='utf-8'))
            self.assertEqual(
                (build_dir / 'configure-count.txt').read_text(encoding='utf-8').strip(),
                '1',
            )
            self.assertIn(
                '--with-devices-i386=whp-user',
                (build_dir / 'configure-args.txt').read_text(encoding='utf-8'),
            )

    def test_portable_entry_rejects_unhandled_audio_override(self):
        portable = load_module(PORTABLE_BUILD_TOOL, 'whp_portable_i386_audio')
        entry = load_module(PORTABLE_ENTRY_TOOL, 'whp_portable_entry_i386_audio')
        self.assertEqual(set(entry.I386_AUDIO_KEYS), set(AUDIO_OPTIONS))
        entry.install_diagnostic_policy(portable)

        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            config_path = td_path / '.whpconfig'
            build_dir = td_path / 'build'
            config_path.write_text(
                'WHP_CONFIG_VERSION=2\n'
                'BUILD_QEMU_SYSTEM_PPC=n\n'
                'BUILD_QEMU_SYSTEM_I386=y\n'
                'I386_AUDIO_SB16=n\n',
                encoding='utf-8',
            )
            with mock.patch.object(portable, 'USER_CONFIG', config_path), \
                 mock.patch.dict(os.environ, {'BUILD_DIR': str(build_dir)}, clear=False):
                with self.assertRaisesRegex(RuntimeError, 'i386 audio hardware filtering'):
                    portable.build_plan([])


if __name__ == '__main__':
    unittest.main()
