#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'


def load_bootstrap_module():
    spec = importlib.util.spec_from_file_location('whp_ensure_ninja_test', BOOTSTRAP)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NinjaMacOSHostCompilerTests(unittest.TestCase):
    def test_darwin_ignores_target_cxx_when_build_cxx_is_unset(self):
        mod = load_bootstrap_module()

        def fake_which(name: str):
            if name == 'xcrun':
                return '/usr/bin/xcrun'
            return None

        with mock.patch.dict(os.environ, {'CXX': '/tmp/target-clang++'}, clear=True), \
             mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.shutil, 'which', side_effect=fake_which), \
             mock.patch.object(mod, 'run_text', return_value='/usr/bin/clang++'):
            self.assertEqual(mod.select_host_cxx(), '/usr/bin/clang++')

    def test_explicit_build_cxx_remains_authoritative_on_darwin(self):
        mod = load_bootstrap_module()
        with mock.patch.dict(
            os.environ,
            {'CXX_FOR_BUILD': '/opt/host-clang++', 'CXX': '/tmp/target-clang++'},
            clear=True,
        ), mock.patch.object(mod.platform, 'system', return_value='Darwin'):
            self.assertEqual(mod.select_host_cxx(), '/opt/host-clang++')


if __name__ == '__main__':
    unittest.main()
