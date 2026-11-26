#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'


def load_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SeaBiosConfigTests(unittest.TestCase):
    def test_seabios_options_are_firmware_tristates(self):
        mod = load_module()
        build = mod.OPTION_BY_KEY['BUILD_SEABIOS']
        bootstrap = mod.OPTION_BY_KEY['BOOTSTRAP_I386_TOOLCHAIN']
        self.assertEqual(build.section, 'Firmware')
        self.assertEqual(build.kind, 'choice')
        self.assertEqual(build.default, 'auto')
        self.assertEqual(build.choices, ('auto', 'y', 'n'))
        self.assertEqual(bootstrap.section, 'Firmware')
        self.assertEqual(bootstrap.kind, 'choice')
        self.assertEqual(bootstrap.default, 'auto')
        self.assertEqual(bootstrap.choices, ('auto', 'y', 'n'))

    def test_explicit_seabios_settings_export_as_shell_booleans(self):
        mod = load_module()
        values = mod.default_values()
        values['BUILD_SEABIOS'] = 'y'
        values['BOOTSTRAP_I386_TOOLCHAIN'] = 'n'
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("BUILD_SEABIOS='1'", assignments)
        self.assertIn("BOOTSTRAP_I386_TOOLCHAIN='0'", assignments)

    def test_auto_seabios_settings_are_not_exported(self):
        mod = load_module()
        assignments = mod.shell_assignments(mod.ConfigState(mod.default_values()), {})
        self.assertNotIn('BUILD_SEABIOS=', assignments)
        self.assertNotIn('BOOTSTRAP_I386_TOOLCHAIN=', assignments)

    def test_seabios_auto_selects_i386_and_x86_64_but_not_8086_target(self):
        # Build-selection contract: an x86_64-only (including deduplicated
        # i386 alias) build must not fall back to QEMU's shipped stock ROM.
        sources = (ROOT / 'scripts/whp-build/prepare-sources.bash').read_text(
            encoding='utf-8')
        self.assertIn(
            '*,i386-softmmu,*|*,x86_64-softmmu,*) BUILD_SEABIOS=1 ;;',
            sources)
        self.assertNotIn('*,x86-softmmu,*) BUILD_SEABIOS=1 ;;', sources)

        meson = (ROOT / 'pc-bios/meson.build').read_text(encoding='utf-8')
        self.assertIn(
            "build_by_default: 'i386-softmmu' in target_dirs or "
            "'x86_64-softmmu' in target_dirs,",
            meson)
        self.assertNotIn("'x86-softmmu' in target_dirs", meson)

        grub = (ROOT / 'scripts/whp-build/prepare-seabios-grub.bash').read_text(
            encoding='utf-8')
        self.assertIn('*,i386-softmmu,*|*,x86_64-softmmu,*)', grub)

        # The 8086 and 8088 boards require a user-specified <=64KiB BIOS.
        original_x86 = (ROOT / 'hw/i386/x86-16bit.c').read_text(
            encoding='utf-8')
        self.assertIn('if (!machine->firmware)', original_x86)
        self.assertIn('X86_16BIT_ROM_SIZE (64 * KiB)', original_x86)

    def test_seabios_cross_toolchain_remains_i386_not_x86_64(self):
        build = (ROOT / 'scripts/whp-build/configure-seabios.bash').read_text(
            encoding='utf-8')
        self.assertIn('i386-none-elf', build)
        self.assertIn('SEABIOS_CROSS_COMPILE', build)
        firmware = (ROOT / 'roms/config.seabios-256k').read_text(
            encoding='utf-8')
        self.assertIn('CONFIG_ROM_SIZE=256', firmware)

    def test_128k_clang_size_profile_is_target_scoped(self):
        makefile = (ROOT / 'roms' / 'Makefile').read_text(encoding='utf-8')
        self.assertIn(
            'build-seabios-config-seabios-128k: export '
            'SEABIOS_CLANG_SIZE_OPT ?= OzSegmented',
            makefile,
        )
        self.assertNotIn(
            'build-seabios-config-seabios-256k: export '
            'SEABIOS_CLANG_SIZE_OPT',
            makefile,
        )
        self.assertNotIn(
            'build-seabios-config-seabios-microvm: export '
            'SEABIOS_CLANG_SIZE_OPT',
            makefile,
        )

    def test_pc_bios_uses_ata_dma_but_isapc_stays_conservative(self):
        normal = (ROOT / 'roms' / 'config.seabios-256k').read_text(encoding='utf-8')
        isapc = (ROOT / 'roms' / 'config.seabios-128k').read_text(encoding='utf-8')
        self.assertIn('CONFIG_ATA_DMA=y', normal)
        self.assertIn('CONFIG_ATA_DMA=n', isapc)

    def test_clang_profile_change_invalidates_cached_firmware(self):
        with tempfile.TemporaryDirectory(prefix='whp-seabios-profile-') as tmp:
            root = pathlib.Path(tmp)
            roms = root / 'roms'
            firmware = roms / 'seabios'
            firmware.mkdir(parents=True)
            shutil.copyfile(ROOT / 'roms' / 'Makefile', roms / 'Makefile')
            (roms / 'config.seabios-128k').write_text(
                'CONFIG_ROM_SIZE=128\n', encoding='utf-8')

            (firmware / 'Makefile').write_text(
                'all: $(OUT)bios.bin\n'
                'oldnoconfig:\n\t@:\n'
                '$(OUT)bios.bin: payload\n'
                '\t@mkdir -p $(dir $@)\n'
                '\t@printf "%s\\n%s\\n" '
                '"$(SEABIOS_CLANG_SIZE_OPT)" "$(CROSS_PREFIX)" > $@\n',
                encoding='utf-8')
            (firmware / 'payload').write_text('source\n', encoding='utf-8')
            for cmd in (
                ('init', '-q'),
                ('config', 'user.name', 'WHP Test'),
                ('config', 'user.email', 'whp@example.invalid'),
                ('add', '.'),
                ('commit', '-qm', 'fake firmware'),
            ):
                subprocess.run(['git', *cmd], cwd=firmware, check=True)

            output = root / 'build/firmware/seabios/seabios-128k/bios.bin'

            def build(profile, cross_prefix='', elf_split='0', inline_profile='Default'):
                result = subprocess.run(
                    ['make', 'build-seabios-config-seabios-128k',
                     'SEABIOS_CLANG_SIZE_OPT=' + profile,
                     'SEABIOS_CROSS_PREFIX=' + cross_prefix,
                     'SEABIOS_CLANG_ELF_SPLIT=' + elf_split,
                     'SEABIOS_CLANG_INLINE_PROFILE=' + inline_profile],
                    cwd=roms, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0,
                                 result.stdout + result.stderr)

            build('OzSegmented')
            self.assertEqual(output.read_text(), 'OzSegmented\n\n')
            stamp = output.parent / '.whp-seabios-source'
            self.assertIn('clang_elf_split=0', stamp.read_text().splitlines())
            self.assertEqual(list(output.parent.glob('.whp-seabios-source.new.*')), [])
            self.assertFalse((roms / 'mp').exists())
            output.write_text('preserve incremental build\n')
            build('OzSegmented')
            self.assertEqual(output.read_text(), 'preserve incremental build\n')
            build('Oz16Only')
            self.assertEqual(output.read_text(), 'Oz16Only\n\n')
            build('Os')
            self.assertEqual(output.read_text(), 'Os\n\n')
            build('Os', 'alternate-')
            self.assertEqual(output.read_text(), 'Os\nalternate-\n')
            output.write_text('stale before ELF split\n')
            build('Os', 'alternate-', '1')
            self.assertEqual(output.read_text(), 'Os\nalternate-\n')
            self.assertIn('clang_elf_split=1', stamp.read_text().splitlines())
            output.write_text('preserve ELF split incremental build\n')
            build('Os', 'alternate-', '1')
            self.assertEqual(output.read_text(), 'preserve ELF split incremental build\n')
            build('Os', 'alternate-', '1', 'CompactFlat')
            self.assertEqual(output.read_text(), 'Os\nalternate-\n')
            self.assertIn('clang_inline_profile=CompactFlat', stamp.read_text().splitlines())
            self.assertEqual(list(output.parent.glob('.whp-seabios-source.new.*')), [])

    def test_new_firmware_revision_replaces_stale_make_dependencies(self):
        with tempfile.TemporaryDirectory(prefix='whp-seabios-revision-') as tmp:
            root = pathlib.Path(tmp)
            roms = root / 'roms'
            firmware = roms / 'seabios'
            firmware.mkdir(parents=True)
            (root / 'pc-bios').mkdir()
            shutil.copyfile(ROOT / 'roms' / 'Makefile', roms / 'Makefile')
            (roms / 'config.vga-cirrus').write_text('CONFIG_VGA_CIRRUS=y\n')

            def git(*args):
                subprocess.run(['git', *args], cwd=firmware, check=True)

            def build():
                result = subprocess.run(
                    ['make', 'seavgabios-cirrus', 'SEABIOS_CROSS_PREFIX='],
                    cwd=roms, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            git('init', '-q')
            git('config', 'user.name', 'WHP Test')
            git('config', 'user.email', 'whp@example.invalid')
            (firmware / 'Makefile').write_text(
                'all: $(OUT)vgabios.bin\n'
                'oldnoconfig:\n\t@:\n'
                '$(OUT)vgabios.bin: payload\n'
                '\tcp payload $@\n'
                '\t@if test -f old.h; then printf "%s: old.h\\n" "$@" > $(OUT)pin.d; fi\n'
                '-include $(OUT)pin.d\n'
            )
            (firmware / 'old.h').touch()
            (firmware / 'payload').write_text('old firmware\n')
            git('add', '.')
            git('commit', '-qm', 'old firmware')
            build()
            output = root / 'pc-bios' / 'vgabios-cirrus.bin'
            cache = root / 'build' / 'firmware' / 'seabios' / 'vga-cirrus'
            self.assertEqual(output.read_text(), 'old firmware\n')
            dependency = cache / 'pin.d'
            self.assertIn('old.h', dependency.read_text())
            before = dependency.read_text() + '# Retained when the cache is reused.\n'
            dependency.write_text(before)
            build()
            self.assertEqual(dependency.read_text(), before)

            other_variant = cache.parent / 'seabios-128k'
            other_variant.mkdir()
            other_output = other_variant / 'bios.bin'
            other_output.write_text('other variant\n')
            git('rm', '-q', 'old.h')
            (firmware / 'payload').write_text('new firmware\n')
            git('commit', '-qam', 'new firmware')
            build()
            self.assertEqual(output.read_text(), 'new firmware\n')
            self.assertFalse(dependency.exists())
            self.assertEqual(other_output.read_text(), 'other variant\n')


if __name__ == '__main__':
    unittest.main()
