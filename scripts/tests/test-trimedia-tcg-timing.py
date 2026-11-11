#!/usr/bin/env python3
"""Static regression for TriMedia packet-count / guest cycle separation."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRANS = (ROOT / "target/trimedia/translate.c").read_text()
CPU = (ROOT / "target/trimedia/cpu.c").read_text()
HEADER = (ROOT / "target/trimedia/cpu.h").read_text()
OPS = (ROOT / "target/trimedia/opcode.h").read_text()


class TriMediaTCGTimingTest(unittest.TestCase):
    def test_vliw_one_translator_instruction(self):
        self.assertIn("#define TRIMEDIA_MAX_ISSUE_SLOTS 5", OPS)
        self.assertIn(".translate_insn = trimedia_tr_translate_insn", TRANS)
        self.assertIn("tcg_gen_insn_start(ctx->base.pc_next, 0, 0)", TRANS)
        self.assertNotIn("num_insns += packet.num_ops", TRANS)
        self.assertNotIn("num_insns += packet->num_ops", TRANS)

    def test_packet_counter_does_not_fake_cccount(self):
        self.assertIn("uint64_t issued_packets;", HEADER)
        self.assertIn("uint64_t cccount;", HEADER)
        self.assertIn("offsetof(CPUTrimediaState, issued_packets)", TRANS)
        self.assertIn("qemu-issued-packets=%", CPU)
        self.assertNotIn("cpu_cccount", TRANS)

    def test_one_runtime_count_after_packet_commit(self):
        block = TRANS.split("static bool trimedia_gen_packet(", 1)[1]
        block = block.split("static bool trimedia_decode_packet(", 1)[0]
        self.assertEqual(block.count("tcg_gen_addi_i64(cpu_issued_packets,"), 1)
        self.assertLess(block.index("trimedia_commit_write(&write[i]);"),
                        block.index("tcg_gen_addi_i64(cpu_issued_packets,"))
        self.assertIn("cpu_issued_packets, 1);", block)

    def test_no_infinite_same_pc_tb_on_failure(self):
        block = TRANS.split("static void trimedia_tr_translate_insn(", 1)[1]
        block = block.split("static void trimedia_tr_tb_stop(", 1)[0]
        self.assertGreaterEqual(block.count("cpu_abort(cs,"), 3)
        self.assertNotIn("tcg_gen_exit_tb(NULL, 0)", block)

    def test_reset_clears_diagnostic_count(self):
        self.assertLess(HEADER.index("uint64_t issued_packets;"),
                        HEADER.index("end_reset_fields;"))
        self.assertIn("memset(env, 0, offsetof(CPUTrimediaState,"
                      " end_reset_fields));", CPU)


if __name__ == "__main__":
    unittest.main()
