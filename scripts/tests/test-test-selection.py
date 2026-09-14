#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SELECTOR = ROOT / 'scripts' / 'whp-build' / 'select-tests.py'


def load_selector():
    spec = importlib.util.spec_from_file_location('whp_select_tests', SELECTOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(repo: pathlib.Path, *args: str) -> str:
    result = subprocess.run(
        ['git', '-C', str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout.strip()


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


class SelectiveTestStateTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_selector()
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.repo = self.root / 'source'
        self.build = self.root / 'build'
        self.repo.mkdir()
        self.build.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.email', 'whp-tests@example.invalid')
        git(self.repo, 'config', 'user.name', 'WHP Tests')
        for relative, text in (
            ('block/qcow2.c', '/* block */\n'),
            ('qapi/machine.json', '{}\n'),
            ('docs/readme.rst', 'docs\n'),
        ):
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'baseline')
        self.targets = ['ppc-softmmu', 'i386-softmmu']

    def tearDown(self):
        self.temp.cleanup()

    def test_first_validation_is_full_then_unchanged_tree_runs_nothing(self):
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            ['check'],
        )
        self.mod.record_test_state(self.repo, self.build, self.targets)
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            [],
        )

    def test_dirty_known_change_runs_only_its_suite_and_can_be_recorded(self):
        self.mod.record_test_state(self.repo, self.build, self.targets)
        path = self.repo / 'block/qcow2.c'
        path.write_text('/* changed block */\n', encoding='utf-8')
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            ['check-block'],
        )
        self.mod.record_test_state(self.repo, self.build, self.targets)
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            [],
        )

    def test_committed_change_since_last_success_uses_selective_suite(self):
        self.mod.record_test_state(self.repo, self.build, self.targets)
        path = self.repo / 'qapi/machine.json'
        path.write_text('{"changed": true}\n', encoding='utf-8')
        git(self.repo, 'add', 'qapi/machine.json')
        git(self.repo, 'commit', '-qm', 'change qapi')
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            ['check-qapi-schema'],
        )

    def test_docs_only_change_runs_no_qemu_suite(self):
        self.mod.record_test_state(self.repo, self.build, self.targets)
        path = self.repo / 'docs/readme.rst'
        path.write_text('changed docs\n', encoding='utf-8')
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            [],
        )

    def test_configured_target_change_forces_full_validation(self):
        self.mod.record_test_state(self.repo, self.build, self.targets)
        self.assertEqual(
            self.mod.plan_changed_tests(
                self.repo, self.build, ['ppc-softmmu', 'i386-softmmu', 'sparc-softmmu']
            ),
            ['check'],
        )

    def test_untracked_content_change_invalidates_recorded_state(self):
        extra = self.repo / 'block/new-driver.c'
        extra.write_text('/* first */\n', encoding='utf-8')
        self.mod.record_test_state(self.repo, self.build, self.targets)
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            [],
        )
        extra.write_text('/* second */\n', encoding='utf-8')
        self.assertEqual(
            self.mod.plan_changed_tests(self.repo, self.build, self.targets),
            ['check-block'],
        )


if __name__ == '__main__':
    unittest.main()
