#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts' / 'whp-build' / 'seabios-llvm-objdump.py'


def load_helper():
    spec = importlib.util.spec_from_file_location('seabios_llvm_objdump', HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {HELPER}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SeaBiosObjdumpAbiTests(unittest.TestCase):
    def test_helper_exists(self):
        self.assertTrue(HELPER.is_file())

    def test_live_thr_output_matches_layoutrom_contract(self):
        clang = shutil.which('clang')
        llvm_objdump = shutil.which('llvm-objdump')
        if not clang or not llvm_objdump:
            self.skipTest('clang/llvm-objdump are unavailable')

        helper = load_helper()
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = pathlib.Path(tmp)
            source = tmpdir / 'probe.c'
            obj = tmpdir / 'probe.o'
            source.write_text(
                'extern int extfn(int);\n'
                'extern int extdata;\n'
                'int *probe_ptr = &extdata;\n'
                'int probe(int value) { return extfn(value) + extdata; }\n',
                encoding='utf-8',
            )
            subprocess.run([
                clang, '--target=i386-none-elf', '-m32', '-ffreestanding',
                '-fno-pic', '-fno-pie', '-ffunction-sections', '-fdata-sections',
                '-c', str(source), '-o', str(obj),
            ], check=True)

            output = subprocess.check_output([
                'python3', str(HELPER), llvm_objdump, '-thr', str(obj),
            ], text=True)

            lines = output.splitlines()
            self.assertIn('Idx Name          Size      VMA       LMA       File off  Algn', lines)
            text_line = next(line for line in lines if '.text.probe' in line)
            fields = text_line.split()
            self.assertEqual(len(fields), 7)
            self.assertEqual(fields[-1], '2**4')
            self.assertIn('SYMBOL TABLE:', output)
            self.assertIn('RELOCATION RECORDS FOR [.text.probe]:', output)
            self.assertIn('R_386_PC32', output)
            self.assertIn('R_386_32', output)

            sections, symbols = helper.parse_seabios_objdump(output.splitlines())
            self.assertEqual(sections['.text.probe'].align, 16)
            self.assertEqual(symbols['probe'].section, '.text.probe')
            self.assertIn('R_386_PC32', sections['.text.probe'].reloc_types)


if __name__ == '__main__':
    unittest.main()
