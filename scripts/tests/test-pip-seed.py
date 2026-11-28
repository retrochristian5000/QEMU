#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline regression checks for the interpreter-bound pip seed."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / 'seeds/pip.sh'


class PipSeedTests(unittest.TestCase):
    def invoke(self, *args, **env):
        return subprocess.run(
            ['/bin/sh', str(SEED), *args],
            env={**os.environ, 'PYTHON': sys.executable, **env},
            text=True, capture_output=True, check=False,
        )

    def test_syntax_and_marker(self):
        subprocess.run(['/bin/sh', '-n', str(SEED)], check=True)
        result = self.invoke('--whp-pip-adapter-probe')
        self.assertEqual(result.stdout.strip(), 'whp-qemu-pip-seed-adapter')

    def test_invalid_interpreter_is_not_replaced(self):
        for candidate in ('/bin/false', str(SEED), str(ROOT / 'seeds/python.sh')):
            with self.subTest(candidate=candidate):
                result = self.invoke('--check', PYTHON=candidate)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(result.stdout)

    def test_missing_pip_in_venv(self):
        with tempfile.TemporaryDirectory() as directory:
            venv = Path(directory) / 'venv with spaces'
            subprocess.run([sys.executable, '-m', 'venv', '--without-pip',
                            str(venv)], check=True)
            candidate = venv / 'bin/python'
            result = self.invoke('--python', str(candidate), '--check')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('pip unavailable for', result.stderr)

    def test_pip_matches_selected_python(self):
        expected = subprocess.run(
            [sys.executable, '-I', '-B', '-m', 'pip', '--version'],
            text=True, capture_output=True, check=False,
        )
        if expected.returncode:
            self.skipTest('selected test interpreter has no isolated pip')
        with tempfile.TemporaryDirectory() as directory:
            fake = Path(directory) / 'pip'
            fake.write_text('#!/bin/sh\nexit 99\n', encoding='utf-8')
            fake.chmod(0o755)
            result = self.invoke('--version', PATH=directory + os.pathsep +
                                 os.environ.get('PATH', ''))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, expected.stdout)
        result = self.invoke('--print-python')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(Path(result.stdout.strip()), Path(sys.executable))
        result = self.invoke('whp-invalid-pip-command')
        self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
