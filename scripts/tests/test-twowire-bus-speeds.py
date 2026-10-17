#!/usr/bin/env python3
"""2Wire bus evidence consistency guard, not a runtime timing test."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "devel" / "twowire-bus-speeds.json"


class BusSpeedsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(SPEC.read_text(encoding="utf-8"))

    def test_board_clocks_require_evidence(self):
        for name, domain in self.data["domains"].items():
            with self.subTest(domain=name):
                hz = domain["actual_hz"]
                provenance = domain["actual_provenance"]
                if hz is None:
                    self.assertIsNone(provenance)
                else:
                    self.assertIsInstance(hz, int)
                    self.assertGreater(hz, 0)
                    self.assertIsInstance(provenance, dict)
                    for field in ("board_revision", "method", "source_url"):
                        self.assertTrue(provenance.get(field))

    def test_all_claims_have_source_scope(self):
        self.assertEqual(self.data["schema_version"], 1)
        for name, domain in self.data["domains"].items():
            with self.subTest(domain=name):
                ref = domain["source"]
                if ref is not None:
                    self.assertIn(ref, self.data["source_kinds"])
        for item in self.data["source_kinds"].values():
            self.assertTrue(item["url"].startswith("https://"))
            self.assertIn(item["kind"],
                          {"reference-only", "part-datasheet",
                           "manufacturer-selector",
                           "comparison-only-88E6060-not-88E6061",
                           "part-brief"})

    def test_ddr400_peak_not_actual_throughput(self):
        ddr = self.data["domains"]["ddr"]
        self.assertEqual(ddr["part"], "Samsung K4H561638J-LCCC")
        self.assertEqual(ddr["capacity_bits"], 268435456)
        self.assertEqual(ddr["chip_clock_max_hz"], 200_000_000)
        peak = (ddr["chip_clock_max_hz"] *
                ddr["transfers_per_clock"] *
                ddr["part_data_bits"] // 8)
        self.assertEqual(peak, 800_000_000)
        self.assertEqual(peak, ddr["theoretical_single_chip_peak_Bps"])

    def test_nand_latency_and_transfer_rate_are_separate(self):
        nand = self.data["domains"]["nand"]
        self.assertEqual(nand["main_page_bytes"], 512)
        self.assertEqual(nand["spare_page_bytes"], 16)
        peak = ((1_000_000_000 // nand["seq_cycle_min_ns"]) *
                nand["part_data_bits"] // 8)
        self.assertEqual(peak, 20_000_000)
        self.assertEqual(peak, nand["theoretical_sequential_ceiling_Bps"])
        self.assertGreater(nand["read_page_max_ns"],
                           nand["seq_cycle_min_ns"])
        self.assertGreater(nand["page_program_typ_ns"],
                           nand["read_page_max_ns"])
        self.assertGreater(nand["block_erase_typ_ns"],
                           nand["page_program_typ_ns"])

    def test_clock_vs_network_link_rate(self):
        cpu, mmio = (self.data["domains"][key] for key in ("cpu", "mmio"))
        self.assertEqual(cpu["reference_max_hz"], 300_000_000)
        self.assertNotIn(cpu["reference_max_hz"], mmio["reference_choices_hz"])
        eth = self.data["domains"]["ethernet"]
        self.assertEqual(eth["part"], "Marvell 88E6061/B")
        self.assertEqual(eth["port_count"], 6)
        self.assertEqual(eth["reference_mii_100_hz"] * 4, 100_000_000)
        self.assertEqual(eth["reference_mii_10_hz"] * 4, 10_000_000)
        self.assertEqual(self.data["domains"]["wifi"]["max_radio_phy_rate_bps"],
                         54_000_000)


if __name__ == "__main__":
    unittest.main()
