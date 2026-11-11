#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts' / 'whp-build' / 'seabios-llvm-objdump.py'


def parse_like_layoutrom(output: str):
    sections = {}
    symbols = {}
    state = None
    reloc_section = None
    for line in output.splitlines():
        if line == 'Sections:':
            state = 'section'
            continue
        if line == 'SYMBOL TABLE:':
            state = 'symbol'
            continue
        if line.startswith('RELOCATION RECORDS FOR ['):
            reloc_section = line[24:-2]
            if reloc_section.startswith('.debug_'):
                state = None
                continue
            if reloc_section not in sections:
                raise AssertionError(f'missing section map entry for {reloc_section}')
            state = 'reloc'
            continue
        if state == 'section':
            fields = line.split()
            if len(fields) != 7 or not fields[-1].startswith('2**'):
                continue
            _idx, name, size, _vma, _lma, _fileoff, align = fields
            sections[name] = {
                'size': int(size, 16),
                'align': 2 ** int(align[3:]),
                'relocs': [],
            }
        elif state == 'symbol':
            parts = line[17:].split() if len(line) >= 17 else []
            if len(parts) == 3:
                section, _size, name = parts
                symbols[name] = section
            elif len(parts) == 4 and parts[2] == '.hidden':
                section, _size, _hidden, name = parts
                symbols[name] = section
        elif state == 'reloc':
            fields = line.split()
            if len(fields) == 3:
                _offset, reloc_type, _symbol = fields
                sections[reloc_section]['relocs'].append(reloc_type)
    return sections, symbols


class SeaBiosObjdumpAbiTests(unittest.TestCase):
    def test_helper_exists(self):
        self.assertTrue(HELPER.is_file())

    def test_live_thr_output_matches_layoutrom_contract(self):
        clang = shutil.which('clang')
        llvm_objdump = shutil.which('llvm-objdump')
        if not clang or not llvm_objdump:
            self.skipTest('clang/llvm-objdump are unavailable')

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

            self.assertIn(
                'Idx Name          Size      VMA       LMA       File off  Algn',
                output.splitlines(),
            )
            sections, symbols = parse_like_layoutrom(output)
            self.assertEqual(sections['.text.probe']['align'], 16)
            self.assertEqual(symbols['probe'], '.text.probe')
            self.assertIn('R_386_PC32', sections['.text.probe']['relocs'])
            self.assertIn('R_386_32', output)


if __name__ == '__main__':
    unittest.main()
