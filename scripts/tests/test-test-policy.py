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
PORTABLE_CORE = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
PORTABLE_ENTRY = ROOT / 'scripts' / 'whp-build' / 'portable-build-entry.py'
SELECTOR = ROOT / 'scripts' / 'whp-build' / 'select-tests.py'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_test_policy_config', CONFIG_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestPolicyTests(unittest.TestCase):
    def test_regression_tests_default_to_changed_only(self):
        config = load_config_module()
        run_tests = config.OPTION_BY_KEY['RUN_TESTS']
        scope = config.OPTION_BY_KEY['QEMU_TEST_SCOPE']
        self.assertEqual(run_tests.section, 'Build behavior')
        self.assertEqual(run_tests.kind, 'bool')
        self.assertEqual(run_tests.default, 'y')
        self.assertEqual(scope.section, 'Build behavior')
        self.assertEqual(scope.kind, 'choice')
        self.assertEqual(scope.default, 'changed')
        self.assertEqual(scope.choices, ('changed', 'full'))
        defaults = config.default_values()
        self.assertEqual(defaults['RUN_TESTS'], 'y')
        self.assertEqual(defaults['QEMU_TEST_SCOPE'], 'changed')

    def test_public_build_entry_exports_config_policy(self):
        entry = BUILD_ENTRY.read_text(encoding='utf-8')
        config_index = entry.index(
            'WHP_CONFIG_ENV=$("$PYTHON" "$WHP_CONFIG_TOOL" --shell "$WHP_USER_CONFIG")'
        )
        eval_index = entry.index('eval "$WHP_CONFIG_ENV"')
        self.assertLess(config_index, eval_index)

    def test_changed_scope_uses_selector_and_records_success(self):
        targets = BUILD_TARGETS.read_text(encoding='utf-8')
        self.assertIn(str(SELECTOR.relative_to(ROOT)), targets)
        self.assertIn('QEMU_TEST_SCOPE', targets)
        self.assertIn(' plan ', targets)
        self.assertIn(' record ', targets)

    def test_portable_core_owns_same_selective_policy(self):
        core = PORTABLE_CORE.read_text(encoding='utf-8')
        entry = PORTABLE_ENTRY.read_text(encoding='utf-8')
        self.assertIn('select-tests.py', core)
        self.assertIn('QEMU_TEST_SCOPE', core)
        self.assertIn('plan_changed_tests', core)
        self.assertIn('record_test_state', core)
        self.assertNotIn('install_test_policy', entry)

    def test_explicit_full_scope_still_uses_qemu_make_check(self):
        targets = BUILD_TARGETS.read_text(encoding='utf-8')
        self.assertIn('RUN_TESTS=1 requires GNU Make', targets)
        self.assertIn('QEMU_TEST_SCOPE', targets)
        self.assertIn('check', targets)


if __name__ == '__main__':
    unittest.main()
