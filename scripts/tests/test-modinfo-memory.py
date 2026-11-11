#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline regression tests for QEMU modinfo generation memory bounds."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / 'scripts' / (name + '.py'))
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {name}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModinfoMemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.collect = load_script('modinfo-collect')
        cls.generate = load_script('modinfo-generate')

    def test_stream_db_handles_chunks_strings_and_duplicate_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'compile_commands.json'
            huge = 'a' * (100 * 1024) + ' braces {"inside": [true]} \\ end'
            entries = [
                {'output': 'ignore.o', 'file': 'ignore.c',
                 'command': 'cc -c ignore.c', 'arguments': [huge]},
                {'output': 'want.o', 'file': 'old.c', 'command': 'cc -c old.c'},
                {'output': 'want.o', 'file': 'new.c', 'command': 'cc -c new.c'},
                {'output': 'other.o', 'file': 'other.c', 'command': 'cc -c other.c'},
            ]
            path.write_text(json.dumps(entries, indent=2), encoding='utf-8')
            selected = self.collect.find_compile_commands({'want.o'}, path)
            self.assertEqual(list(selected), ['want.o'])
            self.assertEqual(selected['want.o']['file'], 'new.c')
            self.assertEqual(
                self.collect.find_compile_commands({'absent.o'}, path), {})

    def test_stream_db_rejects_incomplete_json(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'compile_commands.json'
            path.write_text('[{"output":"x.o",', encoding='utf-8')
            with self.assertRaises(ValueError):
                self.collect.find_compile_commands({'x.o'}, path)

    def test_preprocessor_output_filtered_incrementally(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            compiler = folder / 'mock-compiler.py'
            compiler.write_text(
                "for _ in range(20000):\n"
                "    print('irrelevant preprocessing output')\n"
                "print('MODINFO_START obj \"test\" MODINFO_END')\n",
                encoding='utf-8')
            db = [{
                'output': 'test.o', 'file': 'device.c',
                'command': (
                    f'{shlex.quote(sys.executable)} '
                    f'{shlex.quote(str(compiler))} -c device.c -o test.o')
            }]
            (folder / 'compile_commands.json').write_text(
                json.dumps(db), encoding='utf-8')
            saved = Path.cwd()
            stream = io.StringIO()
            try:
                os.chdir(folder)
                with contextlib.redirect_stdout(stream):
                    self.collect.main(['test.o'])
            finally:
                os.chdir(saved)
            output = stream.getvalue()
            self.assertIn('MODINFO_START obj "test" MODINFO_END', output)
            self.assertNotIn('irrelevant preprocessing output', output)

    def test_generator_accepts_single_pass_file_iterator(self):
        lines = iter([
            'MODINFO_START obj "device" MODINFO_END\n',
            'MODINFO_START dep "dependency" MODINFO_END\n',
        ])
        result = self.generate.parse_modinfo('test', lines, set())
        self.assertEqual(result['objs'], [' "device"'])
        self.assertEqual(result['dep_names'], {'dependency'})
        self.assertIsNone(self.generate.parse_modinfo(
            'test', iter(['MODINFO_START kconfig MISSING MODINFO_END']), set()))

    def test_no_whole_file_capture_regression(self):
        source = (ROOT / 'scripts/modinfo-collect.py').read_text(
            encoding='utf-8')
        self.assertNotIn('compile_commands_json = json.load(f)', source)
        self.assertIn('subprocess.Popen(', source)
        self.assertNotIn('stdout=subprocess.PIPE,\n                                universal_newlines', source)


if __name__ == '__main__':
    unittest.main()
