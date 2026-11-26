/*
 * ISA analog gameport regression tests.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

#define GAMEPORT 0x201

static void test_gameport_timing(gconstpointer opaque)
{
    const char *type = opaque;
    QTestState *s = qtest_initf("-M pc -nodefaults -device %s,"
                              "connected=3,buttons=1,a-x=0,a-y=100000", type);

    /* Button A1 low; absent B axes stay high. */
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xec);
    qtest_outb(s, GAMEPORT, 0x00);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xef);
    qtest_clock_step(s, 24199);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xef);
    qtest_clock_step(s, 1);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xee);
    qtest_clock_step(s, 1099999);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xee);
    qtest_clock_step(s, 1);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xec);

    qtest_outb(s, GAMEPORT, 0xff);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xef);
    qtest_system_reset(s);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xec);
    qtest_quit(s);
}

static void test_gameport_disconnected(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults -device isa-gameport");

    qtest_outb(s, GAMEPORT, 0);
    qtest_clock_step(s, 2000000);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xff);
    qtest_quit(s);
}

static void test_gameport_overlap(void)
{
    if (g_test_subprocess()) {
        QTestState *s = qtest_init("-M pc -nodefaults -device isa-gameport "
                                   "-device creative-gameport");

        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*creative-gameport: ISA I/O range*overlaps*");
}

static void test_sb16_gameport_default(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                               "-audiodev none,id=snd "
                               "-device sb16-generic,id=sb,audiodev=snd");

    g_assert_true(qtest_qom_get_bool(s, "/machine/peripheral/sb", "gameport"));
    g_assert_true(qtest_qom_get_bool(s,
                  "/machine/peripheral/sb/gameport-device", "realized"));
    qtest_outb(s, GAMEPORT, 0);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xff);
    qtest_quit(s);
}

static void test_sb16_gameport_connected(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                               "-audiodev none,id=snd "
                               "-global creative-gameport.connected=3 "
                               "-device sb16-generic,audiodev=snd");

    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xfc);
    qtest_outb(s, GAMEPORT, 0);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xff);
    qtest_clock_step(s, 574200);
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xfc);
    qtest_quit(s);
}

static void test_sb16_gameport_disabled(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                               "-audiodev none,id=snd "
                               "-device sb16-generic,id=sb,audiodev=snd,gameport=off "
                               "-device ibm-game-control,connected=3");

    g_assert_false(qtest_qom_get_bool(s, "/machine/peripheral/sb", "gameport"));
    g_assert_cmphex(qtest_inb(s, GAMEPORT), ==, 0xfc);
    qtest_quit(s);
}

static void test_sb16_gameport_overlap(gconstpointer opaque)
{
    const char *args = opaque;

    if (g_test_subprocess()) {
        QTestState *s = qtest_initf("-M pc -nodefaults "
                                    "-audiodev none,id=snd %s", args);

        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*overlaps*");
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_data_func("/gameport/generic/timing", "isa-gameport",
                        test_gameport_timing);
    qtest_add_data_func("/gameport/ibm/timing", "ibm-game-control",
                        test_gameport_timing);
    qtest_add_data_func("/gameport/creative/timing", "creative-gameport",
                        test_gameport_timing);
    qtest_add_func("/gameport/disconnected", test_gameport_disconnected);
    qtest_add_func("/gameport/overlap", test_gameport_overlap);
    if (qtest_has_device("sb16-generic")) {
        qtest_add_func("/gameport/sb16/default", test_sb16_gameport_default);
        qtest_add_func("/gameport/sb16/connected", test_sb16_gameport_connected);
        qtest_add_func("/gameport/sb16/disabled", test_sb16_gameport_disabled);
        qtest_add_data_func("/gameport/sb16/overlap-first",
                            "-device sb16-generic,audiodev=snd -device isa-gameport",
                            test_sb16_gameport_overlap);
        qtest_add_data_func("/gameport/sb16/overlap-last",
                            "-device isa-gameport -device sb16-generic,audiodev=snd",
                            test_sb16_gameport_overlap);
        qtest_add_data_func("/gameport/sb16/overlap-dsp",
                            "-device sb16-generic,audiodev=snd,iobase=0x1fd",
                            test_sb16_gameport_overlap);
    }
    return g_test_run();
}
