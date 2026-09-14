#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
BUILD_ENTRY = ROOT / 'build.sh'
BUILD_TARGETS = ROOT / 'scripts' / 'whp-build' / 'build-targets.bash'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_test_policy_config', CONFIG_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPolicyTests(unittest.TestCase):
    def test_full_regression_suite_is_opt_in_by_default(self):
        config = load_config_module()
        option = config.OPTION_BY_KEY['RUN_TESTS']
        self.assertEqual(option.section, 'Build behavior')
        self.assertEqual(option.kind, 'bool')
        self.assertEqual(option.default, 'n')
        self.assertEqual(config.default_values()['RUN_TESTS'], 'n')

    def test_public_build_entry_exports_config_policy(self):
        entry = BUILD_ENTRY.read_text(encoding='utf-8')
        config_index = entry.index(
            'WHP_CONFIG_ENV=$("$PYTHON" "$WHP_CONFIG_TOOL" --shell "$WHP_USER_CONFIG")'
        )
        eval_index = entry.index('eval "$WHP_CONFIG_ENV"')
        self.assertLess(config_index, eval_index)

    def test_explicit_full_suite_still_uses_qemu_make_check(self):
        targets = BUILD_TARGETS.read_text(encoding='utf-8')
        self.assertIn('RUN_TESTS=1 requires GNU Make', targets)
        self.assertIn('"$MAKE_CMD" -C "$BUILD_DIR" -j"$JOBS" check', targets)


if __name__ == '__main__':
    unittest.main()
