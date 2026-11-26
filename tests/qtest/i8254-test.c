/*
 * Intel 8254 interval timer regression tests.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "libqtest.h"

#define PIT_COUNTER0 0x40
#define PIT_CONTROL  0x43
#define PIT_MODE2    0x34
#define PIT_MODE3    0x36
#define PIT_LATCH0   0x00
#define PIT_STATUS0  0xe2
#define PIT_OUT      0x80
#define PIT_CLOCK_HZ 1193182ULL
#define NS_PER_SEC   1000000000ULL

static bool pit_out(QTestState *s)
{
    qtest_outb(s, PIT_CONTROL, PIT_STATUS0);
    return (qtest_inb(s, PIT_COUNTER0) & PIT_OUT) != 0;
}

static void check_output(QTestState *s, bool expected)
{
    g_assert_cmpint(pit_out(s), ==, expected);
    g_assert_cmpint(qtest_get_irq(s, 0), ==, expected);
}

static void step_to_tick(QTestState *s, uint64_t tick, uint64_t *elapsed)
{
    uint64_t edge = (tick * NS_PER_SEC + PIT_CLOCK_HZ - 1) / PIT_CLOCK_HZ;

    /* Sample on both sides of the edge; no early transitions are allowed. */
    qtest_clock_step(s, edge - *elapsed - 1);
    *elapsed = edge - 1;
}

static void test_mode2(void)
{
    QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults");
    uint64_t elapsed = 0;

    qtest_irq_intercept_in(s, "ioapic");
    qtest_outb(s, PIT_CONTROL, PIT_MODE2);
    qtest_outb(s, PIT_COUNTER0, 5);
    qtest_outb(s, PIT_COUNTER0, 0);
    check_output(s, true);

    step_to_tick(s, 4, &elapsed);
    check_output(s, true);
    qtest_clock_step(s, 1);
    elapsed++;
    check_output(s, false);

    step_to_tick(s, 5, &elapsed);
    check_output(s, false);
    qtest_clock_step(s, 1);
    elapsed++;
    check_output(s, true);

    step_to_tick(s, 9, &elapsed);
    check_output(s, true);
    qtest_clock_step(s, 1);
    elapsed++;
    check_output(s, false);

    step_to_tick(s, 10, &elapsed);
    check_output(s, false);
    qtest_clock_step(s, 1);
    check_output(s, true);

    qtest_quit(s);
}

static void load_mode3(QTestState *s, uint16_t divisor)
{
    qtest_outb(s, PIT_CONTROL, PIT_MODE3);
    qtest_outb(s, PIT_COUNTER0, divisor & 0xff);
    qtest_outb(s, PIT_COUNTER0, divisor >> 8);
}

static uint16_t read_latched_count(QTestState *s)
{
    uint16_t count;

    qtest_outb(s, PIT_CONTROL, PIT_LATCH0);
    count = qtest_inb(s, PIT_COUNTER0);
    count |= (uint16_t)qtest_inb(s, PIT_COUNTER0) << 8;

    return count;
}

static void advance_to_tick(QTestState *s, uint64_t tick, uint64_t *elapsed)
{
    uint64_t edge = (tick * NS_PER_SEC + PIT_CLOCK_HZ - 1) / PIT_CLOCK_HZ;

    if (edge > *elapsed) {
        qtest_clock_step(s, edge - *elapsed);
        *elapsed = edge;
    }
}

static void test_mode3_counts(void)
{
    static const uint16_t odd_counts[] = { 4, 2, 0, 4, 2, 4, 2 };
    static const uint16_t even_counts[] = { 6, 4, 2, 6, 4, 2, 6 };
    QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults");
    uint64_t elapsed = 0;
    unsigned int i;

    load_mode3(s, 5);
    for (i = 0; i < G_N_ELEMENTS(odd_counts); i++) {
        advance_to_tick(s, i, &elapsed);
        g_assert_cmphex(read_latched_count(s), ==, odd_counts[i]);
        g_assert_cmpint(pit_out(s), ==, i % 5 < 3);
    }

    elapsed = 0;
    load_mode3(s, 6);
    for (i = 0; i < G_N_ELEMENTS(even_counts); i++) {
        advance_to_tick(s, i, &elapsed);
        g_assert_cmphex(read_latched_count(s), ==, even_counts[i]);
        g_assert_cmpint(pit_out(s), ==, i % 6 < 3);
    }

    qtest_quit(s);
}

static void test_bios_tick_latch(void)
{
    QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults");
    uint64_t elapsed = 0;
    uint16_t count;

    /* A programmed zero denotes 65536 clocks, the BIOS tick divisor. */
    load_mode3(s, 0);
    g_assert_cmphex(read_latched_count(s), ==, 0);
    g_assert_true(pit_out(s));

    advance_to_tick(s, 1, &elapsed);
    qtest_outb(s, PIT_CONTROL, PIT_LATCH0);
    count = qtest_inb(s, PIT_COUNTER0);
    advance_to_tick(s, 129, &elapsed);

    /* A second latch must not replace a partially read count. */
    qtest_outb(s, PIT_CONTROL, PIT_LATCH0);
    count |= (uint16_t)qtest_inb(s, PIT_COUNTER0) << 8;
    g_assert_cmphex(count, ==, 0xfffe);
    g_assert_cmphex(read_latched_count(s), ==, 0xfefe);

    advance_to_tick(s, 32768, &elapsed);
    g_assert_false(pit_out(s));
    g_assert_cmphex(read_latched_count(s), ==, 0);
    advance_to_tick(s, 65536, &elapsed);
    g_assert_true(pit_out(s));
    g_assert_cmphex(read_latched_count(s), ==, 0);

    qtest_quit(s);
}

static void test_mode_aliases(void)
{
    static const uint8_t modes[] = { 2, 3, 6, 7 };
    static const uint16_t mode2_counts[] = { 5, 4, 3, 2, 1, 5 };
    static const uint16_t mode3_counts[] = { 4, 2, 0, 4, 2, 4 };
    QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults");
    unsigned int i;

    qtest_irq_intercept_in(s, "ioapic");
    for (i = 0; i < G_N_ELEMENTS(modes); i++) {
        uint8_t control = 0x30 | (modes[i] << 1);
        bool square = modes[i] & 1;
        uint64_t elapsed = 0;
        unsigned int tick;

        qtest_outb(s, PIT_CONTROL, control);
        qtest_outb(s, PIT_COUNTER0, 5);
        qtest_outb(s, PIT_COUNTER0, 0);
        for (tick = 0; tick < G_N_ELEMENTS(mode2_counts); tick++) {
            bool out = square ? tick % 5 < 3 : tick % 5 != 4;
            uint8_t status;

            advance_to_tick(s, tick, &elapsed);
            qtest_outb(s, PIT_CONTROL, PIT_STATUS0);
            status = qtest_inb(s, PIT_COUNTER0);
            g_assert_cmphex(status & 0x3f, ==, control);
            g_assert_cmpint(!!(status & PIT_OUT), ==, out);
            g_assert_cmpint(qtest_get_irq(s, 0), ==, out);
            g_assert_cmphex(read_latched_count(s), ==,
                            square ? mode3_counts[tick] :
                                     mode2_counts[tick]);
        }
    }

    qtest_quit(s);
}

static void test_reprogram_latch(void)
{
    QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults");

    load_mode3(s, 0x1234);
    qtest_outb(s, PIT_CONTROL, PIT_LATCH0);
    g_assert_cmphex(qtest_inb(s, PIT_COUNTER0), ==, 0x34);

    /* A new control word must discard the unread old high byte. */
    load_mode3(s, 0x5678);
    g_assert_cmphex(read_latched_count(s), ==, 0x5678);

    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/i8254/mode2/output", test_mode2);
    qtest_add_func("/i8254/mode3/counts", test_mode3_counts);
    qtest_add_func("/i8254/mode3/bios-tick-latch", test_bios_tick_latch);
    qtest_add_func("/i8254/mode-aliases", test_mode_aliases);
    qtest_add_func("/i8254/reprogram-latch", test_reprogram_latch);

    return g_test_run();
}
