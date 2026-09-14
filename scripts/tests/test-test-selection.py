#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELECTOR = ROOT / 'scripts' / 'whp-build' / 'select-tests.py'


def load_selector():
    spec = importlib.util.spec_from_file_location('whp_select_tests', SELECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SelectiveTestMappingTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_selector()
        self.targets = ['ppc-softmmu', 'i386-softmmu']

    def test_block_change_runs_only_block_suite(self):
        self.assertEqual(
            self.mod.select_test_targets(['block/qcow2.c'], self.targets),
            ['check-block'],
        )

    def test_qapi_change_runs_only_schema_suite(self):
        self.assertEqual(
            self.mod.select_test_targets(['qapi/machine.json'], self.targets),
            ['check-qapi-schema'],
        )

    def test_ppc_change_runs_only_ppc_qtests(self):
        self.assertEqual(
            self.mod.select_test_targets(['hw/ppc/mac_newworld.c'], self.targets),
            ['check-qtest-ppc'],
        )

    def test_i386_change_runs_only_i386_qtests(self):
        self.assertEqual(
            self.mod.select_test_targets(['target/i386/tcg/fpu_helper.c'], self.targets),
            ['check-qtest-i386'],
        )

    def test_arch_suite_is_skipped_when_target_is_not_configured(self):
        self.assertEqual(
            self.mod.select_test_targets(['hw/ppc/mac_newworld.c'], ['i386-softmmu']),
            [],
        )

    def test_specialized_generators_select_their_own_suites(self):
        self.assertEqual(
            self.mod.select_test_targets(
                ['scripts/decodetree.py', 'scripts/tracetool/__init__.py'],
                self.targets,
            ),
            ['check-decodetree', 'check-tracetool'],
        )

    def test_docs_only_change_runs_no_qemu_regression_suite(self):
        self.assertEqual(
            self.mod.select_test_targets(['docs/system/target-ppc.rst'], self.targets),
            [],
        )

    def test_test_infrastructure_change_falls_back_to_full_check(self):
        self.assertEqual(
            self.mod.select_test_targets(['tests/meson.build'], self.targets),
            ['check'],
        )

    def test_unknown_source_change_falls_back_to_full_check(self):
        self.assertEqual(
            self.mod.select_test_targets(['audio/audio.c'], self.targets),
            ['check'],
        )

    def test_multiple_known_changes_are_deduplicated_in_stable_order(self):
        self.assertEqual(
            self.mod.select_test_targets(
                ['qobject/qdict.c', 'block/qcow2.c', 'qobject/qjson.c'],
                self.targets,
            ),
            ['check-unit', 'check-block'],
        )


if __name__ == '__main__':
    unittest.main()
