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

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/i8254/mode2/output", test_mode2);

    return g_test_run();
}
