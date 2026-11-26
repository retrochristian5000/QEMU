#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Smoke-test the startup-only macOS TCG scheduling option."""

from qemu_test import QemuSystemTest


class TcgHostQosTest(QemuSystemTest):

    def check_startup(self, mode, qos):
        self.require_accelerator('tcg')
        self.set_machine('pc')
        self.vm.add_args('-accel', f'tcg,thread={mode},host-qos={qos}',
                         '-nodefaults', '-S', '-m', '64M')
        self.vm.launch()
        self.assertEqual(self.vm.cmd('query-status')['running'], False)

    def test_single_inherit(self):
        self.check_startup('single', 'off')

    def test_single_foreground(self):
        self.check_startup('single', 'on')

    def test_multi_foreground(self):
        self.check_startup('multi', 'on')


if __name__ == '__main__':
    TcgHostQosTest.main()
