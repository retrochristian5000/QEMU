#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import sys
import unittest
from typing import Optional


ROOT = pathlib.Path(__file__).resolve().parents[2]
MINIKCONF = ROOT / 'scripts' / 'minikconf.py'
PCMCIA_KCONFIG = ROOT / 'hw' / 'pcmcia' / 'Kconfig'
PCMCIA_MESON = ROOT / 'hw' / 'pcmcia' / 'meson.build'


def load_minikconf():
    name = 'whp_pcmcia_minikconf'
    spec = importlib.util.spec_from_file_location(name, MINIKCONF)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def resolved_pcmcia_config(*, pci: bool, pci_devices: bool,
                           i82092aa: Optional[bool] = None):
    minikconf = load_minikconf()
    data = minikconf.KconfigData()

    # These symbols are declared outside hw/pcmcia/Kconfig in the full QEMU
    # graph.  Declare only the external leaves needed to solve this section.
    for name in ('PCI', 'PCI_DEVICES', 'SERIAL'):
        var = data.do_var(name)
        data.do_declaration(var)

    with PCMCIA_KCONFIG.open('rt', encoding='utf-8') as stream:
        minikconf.KconfigParser.parse(stream, data)

    data.do_cmdline_assignment('CONFIG_PCI', pci)
    data.do_cmdline_assignment('CONFIG_PCI_DEVICES', pci_devices)
    if i82092aa is not None:
        data.do_cmdline_assignment('CONFIG_I82092AA', i82092aa)

    return data.compute_config()


class PcmciaConfigTests(unittest.TestCase):
    def test_pcmcia_kconfig_uses_supported_minikconf_grammar(self):
        text = PCMCIA_KCONFIG.read_text(encoding='utf-8')
        self.assertNotRegex(text, r'(?m)^\s*help\s*$')
        self.assertIn('config PCMCIA\n    bool', text)
        self.assertIn(
            'config PCMCIA_MODEM\n'
            '    bool\n'
            '    default y if PCMCIA\n'
            '    depends on PCMCIA\n'
            '    select SERIAL',
            text,
        )
        self.assertIn(
            'config I82092AA\n'
            '    bool\n'
            '    default y if PCI_DEVICES\n'
            '    depends on PCI\n'
            '    select PCMCIA',
            text,
        )

    def test_pcmcia_meson_has_only_real_source_rules(self):
        text = PCMCIA_MESON.read_text(encoding='utf-8')
        self.assertNotIn('\\n', text)
        self.assertEqual(
            [line for line in text.splitlines() if line],
            [
                "system_ss.add(when: 'CONFIG_PCMCIA', if_true: files('pcmcia.c'))",
                "system_ss.add(when: 'CONFIG_I82092AA', if_true: files('i82092.c'))",
                "system_ss.add(when: 'CONFIG_PCMCIA_MODEM', if_true: files('worldport.c'))",
            ],
        )

    def test_qom_type_names_and_socket_cardinality(self):
        # One source of truth per type, and exact QOM parent chains.
        # These guard against accidental type renames and card/bus mixups.
        header = (ROOT / 'include/hw/pcmcia/pcmcia.h').read_text(
            encoding='utf-8'
        )
        core = (ROOT / 'hw/pcmcia/pcmcia.c').read_text(encoding='utf-8')
        bridge = (ROOT / 'hw/pcmcia/i82092.c').read_text(
            encoding='utf-8'
        )
        modem = (ROOT / 'hw/pcmcia/worldport.c').read_text(
            encoding='utf-8'
        )
        qtest = (ROOT / 'tests/qtest/i82092aa-test.c').read_text(
            encoding='utf-8'
        )

        self.assertIn('#define TYPE_PCMCIA_BUS "pcmcia-bus"', header)
        self.assertIn('#define TYPE_PCMCIA_CARD "pcmcia-card"', header)
        self.assertIn(
            'OBJECT_DECLARE_SIMPLE_TYPE(PCMCIABus, PCMCIA_BUS)', header
        )
        self.assertIn(
            'OBJECT_DECLARE_TYPE(PCMCIACardState, PCMCIACardClass, '
            'PCMCIA_CARD)', header
        )
        self.assertIn('.name = TYPE_PCMCIA_BUS,', core)
        self.assertIn('.parent = TYPE_BUS,', core)
        self.assertIn('.name = TYPE_PCMCIA_CARD,', core)
        self.assertIn('.parent = TYPE_DEVICE,', core)
        self.assertIn('.abstract = true,', core)
        self.assertIn('dc->bus_type = TYPE_PCMCIA_BUS;', core)
        self.assertIn('bc->max_dev = 1;', core)
        self.assertIn('.class_init = pcmcia_bus_class_init,', core)
        self.assertIn('#define TYPE_I82092AA "i82092aa"', bridge)
        self.assertIn('.parent = TYPE_PCI_DEVICE,', bridge)
        self.assertIn('#define TYPE_USR_WORLDPORT_V34 "usr-worldport-v34"',
                      modem)
        self.assertIn('.parent = TYPE_PCMCIA_CARD,', modem)
        self.assertIn('test_pcmcia_type_names', qtest)
        self.assertIn("Bus 'pcic.0' is full", qtest)

    def test_default_pci_device_set_enables_bridge_core_and_card(self):
        resolved = resolved_pcmcia_config(pci=True, pci_devices=True)
        for symbol in ('I82092AA', 'PCMCIA', 'PCMCIA_MODEM', 'SERIAL'):
            self.assertTrue(resolved[symbol], symbol)

    def test_disabling_default_pci_devices_does_not_force_pcmcia(self):
        resolved = resolved_pcmcia_config(pci=True, pci_devices=False)
        for symbol in ('I82092AA', 'PCMCIA', 'PCMCIA_MODEM', 'SERIAL'):
            self.assertFalse(resolved[symbol], symbol)

    def test_explicit_bridge_enable_is_architecture_neutral(self):
        resolved = resolved_pcmcia_config(
            pci=True,
            pci_devices=False,
            i82092aa=True,
        )
        for symbol in ('I82092AA', 'PCMCIA', 'PCMCIA_MODEM', 'SERIAL'):
            self.assertTrue(resolved[symbol], symbol)


if __name__ == '__main__':
    unittest.main()
