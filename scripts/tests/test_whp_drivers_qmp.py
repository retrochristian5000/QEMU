#!/usr/bin/env python3
"""Offline parser regressions for the WHP-Drivers QEMU bridge."""

import importlib.util
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).with_name("whp_drivers_qmp.py")
SPEC = importlib.util.spec_from_file_location("whp_drivers_qmp", SCRIPT)
BRIDGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BRIDGE)


def controller(ident, class_code, vendor=0x8086, device=0x1234):
    return {"qdev_id": ident, "class_info": {"class": class_code},
            "id": {"vendor": vendor, "device": device}}


def inventory():
    return [{"devices": [controller(ident, class_code)
                         for ident, _, class_code in BRIDGE.CONTROLLERS]}]


class InventoryTests(unittest.TestCase):
    def test_expected_controllers(self):
        rows = BRIDGE.validate_inventory(inventory())
        self.assertEqual([row["model"] for row in rows],
                         [model for _, model, _ in BRIDGE.CONTROLLERS])
        self.assertEqual(rows[0]["pci_id"], "8086:1234")

    def test_nested_pci_bridge(self):
        buses = inventory()
        nested = buses[0]["devices"].pop()
        buses[0]["devices"].append({
            "qdev_id": "whp-bridge", "pci_bridge": {"bus": {"devices": [nested]}}
        })
        self.assertEqual(len(BRIDGE.validate_inventory(buses)), 3)

    def test_missing_controller_fails(self):
        buses = inventory()
        buses[0]["devices"].pop()
        with self.assertRaisesRegex(ValueError, "did not expose"):
            BRIDGE.validate_inventory(buses)

    def test_wrong_class_fails(self):
        buses = inventory()
        buses[0]["devices"][0]["class_info"]["class"] = 0x0200
        with self.assertRaisesRegex(ValueError, "class/subclass"):
            BRIDGE.validate_inventory(buses)

    def test_missing_identity_fails(self):
        buses = inventory()
        del buses[0]["devices"][0]["id"]
        with self.assertRaisesRegex(ValueError, "missing PCI vendor"):
            BRIDGE.validate_inventory(buses)

    def test_malformed_bus_fails(self):
        with self.assertRaisesRegex(ValueError, "did not return a bus list"):
            BRIDGE.validate_inventory({"devices": []})


if __name__ == "__main__":
    unittest.main()
