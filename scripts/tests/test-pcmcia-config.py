#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import re
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

    def test_pci_device_class_declared_before_82092aa_use(self):
        # pci.h alone does not declare PCIDeviceClass or PCI_DEVICE_CLASS.
        # The 82092AA host is a PCI device, not just a generic PCI bus user.
        bridge = (ROOT / 'hw/pcmcia/i82092.c').read_text(
            encoding='utf-8'
        )
        pci_device_header = (
            ROOT / 'include/hw/pci/pci_device.h'
        ).read_text(encoding='utf-8')

        self.assertIn(
            '#include "hw/pci/pci_device.h"', bridge
        )
        self.assertLess(
            bridge.index('#include "hw/pci/pci_device.h"'),
            bridge.index('PCIDeviceClass *pc = PCI_DEVICE_CLASS(klass);'),
        )
        self.assertIn('typedef struct PCIDeviceClass PCIDeviceClass;',
                      pci_device_header)
        self.assertIn('struct PCIDeviceClass {', pci_device_header)
        self.assertIn('DECLARE_OBJ_CHECKERS(PCIDevice, PCIDeviceClass,',
                      pci_device_header)
        self.assertNotIn('PCIDevicCLass', bridge)

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

    def test_shared_cis_and_exca_definitions(self):
        cis = (ROOT / 'include/hw/pcmcia/pcmcia.h').read_text(
            encoding='utf-8'
        )
        exca = (ROOT / 'include/hw/pcmcia/i365.h').read_text(
            encoding='utf-8'
        )
        controller = (ROOT / 'hw/pcmcia/i82092.c').read_text(
            encoding='utf-8'
        )
        qtest = (ROOT / 'tests/qtest/i82092aa-test.c').read_text(
            encoding='utf-8'
        )
        modem = (ROOT / 'hw/pcmcia/worldport.c').read_text(
            encoding='utf-8'
        )

        def check_definitions(source, expected):
            found = dict(re.findall(
                r'(?m)^#define\s+(CISTPL_\w+|I365_\w+)\s+'
                r'(0x[0-9a-fA-F]+)\b', source
            ))
            for name, value in expected.items():
                self.assertIn(name, found)
                self.assertEqual(int(found[name], 16), value, name)

        check_definitions(cis, {
            'CISTPL_CHECKSUM': 0x10,
            'CISTPL_LONGLINK_A': 0x11,
            'CISTPL_LONGLINK_C': 0x12,
            'CISTPL_VERS_1': 0x15,
            'CISTPL_CONFIG': 0x1a,
            'CISTPL_CFTABLE_ENTRY': 0x1b,
            'CISTPL_MANFID': 0x20,
            'CISTPL_FUNCID': 0x21,
            'CISTPL_FUNCE': 0x22,
            'CISTPL_FUNCID_SERIAL': 0x02,
            'CISTPL_SERIAL_UART_16550': 0x02,
            'CISTPL_END': 0xff,
        })
        check_definitions(exca, {
            'I365_IDENT': 0x00,
            'I365_POWER': 0x02,
            'I365_INTCTL': 0x03,
            'I365_CSC': 0x04,
            'I365_CSCINT': 0x05,
            'I365_CS_DETECT': 0x0c,
            'I365_CS_READY': 0x20,
            'I365_PWR_OUT': 0x80,
            'I365_VCC_5V': 0x10,
            'I365_PC_RESET': 0x40,
            'I365_CSC_DETECT': 0x08,
            'I365_CSC_READY': 0x04,
            'I365_MEM_REG': 0x4000,
        })
        for source in (controller, qtest):
            self.assertIn('#include "hw/pcmcia/i365.h"', source)
            self.assertNotRegex(source, r'(?m)^#define I365_')
        self.assertIn('#include "hw/core/qdev-properties.h"', modem)
        self.assertIn('CISTPL_CONFIG, CISTPL_CFTABLE_ENTRY, CISTPL_END',
                      qtest)

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
