/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "hw/cpu/mcs51.h"

static void test_model(void)
{
    const MCS51Model *nmos = mcs51_model_find("intel-8052");
    const MCS51Model *cmos = mcs51_model_find("intel-80c52");

    g_assert_nonnull(nmos);
    g_assert_nonnull(cmos);
    g_assert_true(nmos != cmos);
    g_assert_false(nmos->cmos);
    g_assert_true(cmos->cmos);
    g_assert_true(nmos->timer2);
    g_assert_cmpuint(nmos->ram_size, ==, 256);
    g_assert_cmpuint(cmos->rom_size, ==, 8192);
    g_assert_null(mcs51_model_find("intel-8051"));
}

static void test_core(void)
{
    static const uint8_t rom[8192] = {
        0x75, 0x81, 0x7f,       /* MOV SP,#7fh */
        0x78, 0x90,             /* MOV R0,#90h */
        0x76, 0x5a,             /* MOV @R0,#5ah (upper IRAM) */
        0x74, 0x7f,             /* MOV A,#7fh */
        0x24, 0x01,             /* ADD A,#1 */
        0x12, 0x00, 0x16,       /* LCALL 0016h */
        0xe6,                   /* MOV A,@R0 */
        0x75, 0xd0, 0x08,       /* MOV PSW,#8 (bank 1) */
        0x78, 0x21,             /* MOV R0,#21h */
        0x80, 0x04,             /* SJMP 001ah */
        0x04,                   /* INC A */
        0x22,                   /* RET */
        0x00, 0x00,             /* Padding */
        0xa5,                   /* Reserved opcode */
    };
    MCS51State s = {
        .model = mcs51_model_find("intel-8052"),
        .rom = rom,
    };

    mcs51_reset(&s);
    g_assert_cmphex(s.sfr[1], ==, 7);
    g_assert_cmphex(s.sfr[0x10], ==, 0xff);
    for (unsigned int i = 0; i < 5; i++) {
        g_assert_true(mcs51_step(&s));
    }
    g_assert_cmphex(s.ram[0x90], ==, 0x5a);
    g_assert_cmphex(s.sfr[0x10], ==, 0xff); /* P1, not upper IRAM. */
    g_assert_cmphex(s.sfr[0x60], ==, 0x80); /* ACC */
    g_assert_cmphex(s.sfr[0x50], ==, 0x45); /* AC, OV, parity */
    g_assert_true(mcs51_step(&s));
    g_assert_cmphex(s.pc, ==, 0x16);
    g_assert_cmphex(s.sfr[1], ==, 0x81);
    g_assert_cmphex(s.ram[0x80], ==, 14);
    g_assert_cmphex(s.ram[0x81], ==, 0);
    g_assert_true(mcs51_step(&s));
    g_assert_true(mcs51_step(&s));
    g_assert_cmphex(s.pc, ==, 14);
    g_assert_cmphex(s.sfr[1], ==, 0x7f);
    g_assert_true(mcs51_step(&s));
    g_assert_cmphex(s.sfr[0x60], ==, 0x5a);
    g_assert_true(mcs51_step(&s));
    g_assert_true(mcs51_step(&s));
    g_assert_cmphex(s.ram[8], ==, 0x21);
    g_assert_cmphex(s.ram[0], ==, 0x90);
    g_assert_true(mcs51_step(&s));
    g_assert_cmphex(s.pc, ==, 0x1a);
    g_assert_false(mcs51_step(&s));
    s.pc = 8192;
    g_assert_false(mcs51_step(&s));
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/mcs51/model", test_model);
    g_test_add_func("/mcs51/core", test_core);
    return g_test_run();
}
