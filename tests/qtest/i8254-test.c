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

static void test_mode4_strobe(void)
{
    QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults");
    uint64_t elapsed = 0;

    qtest_irq_intercept_in(s, "ioapic");
    qtest_outb(s, PIT_CONTROL, 0x38);
    qtest_outb(s, PIT_COUNTER0, 5);
    qtest_outb(s, PIT_COUNTER0, 0);
    check_output(s, true);

    step_to_tick(s, 5, &elapsed);
    check_output(s, true);
    qtest_clock_step(s, 1);
    elapsed++;
    check_output(s, false);

    step_to_tick(s, 6, &elapsed);
    check_output(s, false);
    qtest_clock_step(s, 1);
    check_output(s, true);
    qtest_clock_step(s, NS_PER_SEC);
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

static void test_i8253_model(void)
{
    static const uint16_t counts[] = { 5, 4, 2, 5, 2, 5, 4 };
    QTestState *s = qtest_init("-machine generic-pc,hpet=off -nodefaults "
                              "-global isa-pit.model=i8253");
    uint64_t elapsed = 0;
    unsigned int i;

    qtest_irq_intercept_in(s, "ioapic");
    load_mode3(s, 5);
    for (i = 0; i < G_N_ELEMENTS(counts); i++) {
        advance_to_tick(s, i, &elapsed);
        /* The 8254 status read-back command must not latch status. */
        qtest_outb(s, PIT_CONTROL, PIT_STATUS0);
        g_assert_cmphex(read_latched_count(s), ==, counts[i]);
        g_assert_cmpint(qtest_get_irq(s, 0), ==, i % 5 < 3);
    }

    qtest_quit(s);
}

static void test_i8254_model(void)
{
    QTestState *s = qtest_init("-machine generic-pc,hpet=off -nodefaults "
                              "-global isa-pit.model=i8254");

    load_mode3(s, 5);
    g_assert_cmphex(read_latched_count(s), ==, 4);
    g_assert_true(pit_out(s));

    qtest_quit(s);
}

static uint8_t read_status(QTestState *s, unsigned channel)
{
    qtest_outb(s, PIT_CONTROL, 0xe0 | (2 << channel));
    return qtest_inb(s, PIT_COUNTER0 + channel);
}

static void test_i8254_initial_count(void)
{
    QTestState *s = qtest_init("-machine generic-pc,hpet=off -nodefaults "
                              "-global isa-pit.model=i8254");

    /* Program every counter, but only complete channel 1's count. */
    for (unsigned i = 0; i < 3; i++) {
        qtest_outb(s, PIT_CONTROL, PIT_MODE3 | (i << 6));
        g_assert_cmphex(read_status(s, i) & 0x7f, ==, 0x76);
    }
    qtest_outb(s, PIT_COUNTER0 + 1, 0x34);
    g_assert_cmphex(read_status(s, 1) & 0x40, ==, 0x40);
    qtest_outb(s, PIT_COUNTER0 + 1, 0x12);
    g_assert_cmphex(read_status(s, 1) & 0x40, ==, 0);
    g_assert_cmphex(read_status(s, 0) & 0x40, ==, 0x40);
    g_assert_cmphex(read_status(s, 2) & 0x40, ==, 0x40);

    /* An unread status latch must preserve its earlier null-count bit. */
    qtest_outb(s, PIT_CONTROL, PIT_STATUS0);
    qtest_outb(s, PIT_COUNTER0, 0x78);
    qtest_outb(s, PIT_COUNTER0, 0x56);
    qtest_outb(s, PIT_CONTROL, PIT_STATUS0);
    g_assert_cmphex(qtest_inb(s, PIT_COUNTER0) & 0x40, ==, 0x40);
    g_assert_cmphex(read_status(s, 0) & 0x40, ==, 0);
    g_assert_cmphex(read_latched_count(s), ==, 0x5678);

    /* Reset clears the pending programming state. */
    qtest_system_reset(s);
    g_assert_cmphex(read_status(s, 2) & 0x40, ==, 0);
    qtest_quit(s);
}

static void test_explicit_pit(gconstpointer opaque)
{
    const char *model = opaque;
    bool is_8253 = !strcmp(model, "i8253");
    QTestState *s = qtest_initf("-machine pc,pit=off,hpet=off -nodefaults "
                               "-device %s", model);
    uint64_t elapsed = 0;

    qtest_irq_intercept_in(s, "ioapic");
    load_mode3(s, 5);
    g_assert_cmphex(read_latched_count(s), ==, is_8253 ? 5 : 4);
    g_assert_true(qtest_get_irq(s, 0));

    advance_to_tick(s, 3, &elapsed);
    g_assert_false(qtest_get_irq(s, 0));
    advance_to_tick(s, 5, &elapsed);
    g_assert_true(qtest_get_irq(s, 0));

    if (!is_8253) {
        g_assert_true(pit_out(s));
    }
    qtest_quit(s);
}

static void test_pc_chipset_controllers(gconstpointer opaque)
{
    bool specific = GPOINTER_TO_INT(opaque);
    QTestState *s = qtest_initf("-machine pc,hpet=off,chipset-controllers=%s "
                               "-nodefaults", specific ? "on" : "off");
    g_autofree char *tree = qtest_hmp(s, "info qtree");
    g_auto(GStrv) pics = g_strsplit(tree,
        specific ? "dev: i8259a," : "dev: isa-i8259,", -1);
    g_auto(GStrv) pits = g_strsplit(tree,
        specific ? "dev: i8254," : "dev: isa-pit,", -1);
    uint64_t elapsed = 0;

    /* Exactly two cascaded PICs and one motherboard PIT, not duplicates. */
    g_assert_cmpuint(g_strv_length(pics), ==, 3);
    g_assert_cmpuint(g_strv_length(pits), ==, 2);
    g_assert_null(strstr(tree, specific ? "dev: isa-i8259," : "dev: i8259a,"));
    g_assert_null(strstr(tree, specific ? "dev: isa-pit," : "dev: i8254,"));

    qtest_irq_intercept_in(s, "ioapic");
    load_mode3(s, 5);
    check_output(s, true);
    advance_to_tick(s, 3, &elapsed);
    check_output(s, false);
    advance_to_tick(s, 5, &elapsed);
    check_output(s, true);
    qtest_quit(s);
}

static void test_explicit_pit_duplicate(void)
{
    if (g_test_subprocess()) {
        QTestState *s = qtest_init("-machine pc,hpet=off -nodefaults "
                                   "-device i8254");

        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*ISA bus already has a system PIT*");
}

static void test_pcspk_port61(gconstpointer opaque)
{
    bool specific = GPOINTER_TO_INT(opaque);
    QTestState *s = qtest_initf("-machine pc,hpet=off,chipset-controllers=%s "
                               "-nodefaults", specific ? "on" : "off");
    uint8_t refresh = qtest_inb(s, 0x61) & 0x10;

    /* Reads without advancing virtual time cannot create refresh edges. */
    for (unsigned i = 0; i < 16; i++) {
        g_assert_cmphex(qtest_inb(s, 0x61) & 0x10, ==, refresh);
    }
    qtest_clock_step(s, 15000);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x10, ==, refresh ^ 0x10);
    qtest_clock_step(s, 15000);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x10, ==, refresh);

    /* Channel 2, mode 3, six clocks: three high and three low. */
    qtest_outb(s, 0x61, 0);
    qtest_outb(s, PIT_CONTROL, 0xb6);
    qtest_outb(s, 0x42, 6);
    qtest_outb(s, 0x42, 0);
    qtest_clock_step(s, 4000);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x23, ==, 0x20);
    qtest_outb(s, 0x61, 3);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x23, ==, 0x23);
    qtest_clock_step(s, 3000);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x23, ==, 3);
    qtest_outb(s, 0x61, 2);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x23, ==, 0x22);
    qtest_clock_step(s, 4000);
    g_assert_cmphex(qtest_inb(s, 0x61) & 0x23, ==, 0x22);
    qtest_outb(s, 0x61, 3);
    qtest_system_reset(s);
    g_assert_cmphex(qtest_inb(s, 0x61) & 3, ==, 0);
    qtest_quit(s);
}

static void test_pc_reprogram_pending(gconstpointer opaque)
{
    const char *machine = opaque;
    QTestState *s = qtest_initf("-M %s,hpet=off -nodefaults", machine);
    uint64_t elapsed = 0;

    qtest_irq_intercept_in(s, "ioapic");
    qtest_outb(s, PIT_CONTROL, PIT_MODE2);
    qtest_outb(s, PIT_COUNTER0, 5);
    qtest_outb(s, PIT_COUNTER0, 0);
    advance_to_tick(s, 4, &elapsed);
    check_output(s, false);

    /* A new control word restores OUT high and retires the old divisor. */
    qtest_outb(s, PIT_CONTROL, PIT_MODE3);
    check_output(s, true);
    g_assert_cmphex(read_status(s, 0) & 0x40, ==, 0x40);
    qtest_clock_step(s, 100000);
    check_output(s, true);
    qtest_outb(s, PIT_COUNTER0, 7);
    qtest_clock_step(s, 100000);
    check_output(s, true);
    g_assert_cmphex(read_status(s, 0) & 0x40, ==, 0x40);
    qtest_outb(s, PIT_COUNTER0, 0);
    elapsed = 0;
    g_assert_cmphex(read_status(s, 0) & 0x40, ==, 0);
    advance_to_tick(s, 4, &elapsed);
    check_output(s, false);
    advance_to_tick(s, 7, &elapsed);
    check_output(s, true);

    /* Mode 0 forces OUT low while waiting for its complete initial count. */
    qtest_outb(s, PIT_CONTROL, 0x30);
    check_output(s, false);
    qtest_clock_step(s, 100000);
    check_output(s, false);
    qtest_quit(s);
}

static void test_pc_reprogram_compat(gconstpointer opaque)
{
    const char *args = opaque;
    QTestState *s = qtest_initf("%s -nodefaults", args);
    uint64_t elapsed = 0;

    qtest_irq_intercept_in(s, "ioapic");
    qtest_outb(s, PIT_CONTROL, PIT_MODE2);
    qtest_outb(s, PIT_COUNTER0, 5);
    qtest_outb(s, PIT_COUNTER0, 0);
    qtest_outb(s, PIT_CONTROL, PIT_MODE2);
    advance_to_tick(s, 4, &elapsed);
    check_output(s, false);
    advance_to_tick(s, 5, &elapsed);
    check_output(s, true);
    qtest_quit(s);
}

static void test_pc_periodic_cadence(gconstpointer opaque)
{
    unsigned divisor = GPOINTER_TO_UINT(opaque);
    QTestState *s = qtest_init("-M pc,hpet=off -nodefaults");
    uint64_t elapsed = 0;

    qtest_irq_intercept_in(s, "ioapic");
    load_mode3(s, divisor);
    for (unsigned i = 0; i < 64; i++) {
        uint64_t high_end = (uint64_t)i * divisor + (divisor + 1) / 2;
        uint64_t period_end = (uint64_t)(i + 1) * divisor;

        step_to_tick(s, high_end, &elapsed);
        check_output(s, true);
        qtest_clock_step(s, 1);
        elapsed++;
        check_output(s, false);
        step_to_tick(s, period_end, &elapsed);
        check_output(s, false);
        qtest_clock_step(s, 1);
        elapsed++;
        check_output(s, true);
    }
    qtest_quit(s);
}

static void test_reset_latches(void)
{
    QTestState *s = qtest_init("-M pc,hpet=off -nodefaults");

    load_mode3(s, 0x1234);
    qtest_outb(s, PIT_CONTROL, PIT_LATCH0);
    qtest_outb(s, PIT_CONTROL, PIT_STATUS0);
    qtest_system_reset(s);
    /* Neither the status nor count latch may retain the old divisor. */
    g_assert_cmphex(read_latched_count(s), ==, 0);
    g_assert_cmphex(read_status(s, 0) & 0x7f, ==, 0x36);
    qtest_quit(s);
}

static void test_constant_periodic_output(void)
{
    QTestState *s = qtest_init("-M pc,hpet=off -nodefaults");

    qtest_irq_intercept_in(s, "ioapic");
    load_mode3(s, 1);
    check_output(s, true);
    qtest_clock_step(s, NS_PER_SEC);
    check_output(s, true);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/i8254/mode2/output", test_mode2);
    qtest_add_func("/i8254/reset/latches", test_reset_latches);
    qtest_add_func("/i8254/mode3/constant-output", test_constant_periodic_output);
    qtest_add_func("/i8254/mode4/strobe", test_mode4_strobe);
    qtest_add_data_func("/i8254/speaker/compat", GINT_TO_POINTER(0),
                        test_pcspk_port61);
    qtest_add_data_func("/i8254/speaker/chipset", GINT_TO_POINTER(1),
                        test_pcspk_port61);
    qtest_add_func("/i8254/mode3/counts", test_mode3_counts);
    qtest_add_func("/i8254/mode3/bios-tick-latch", test_bios_tick_latch);
    qtest_add_func("/i8254/mode-aliases", test_mode_aliases);
    qtest_add_func("/i8254/reprogram-latch", test_reprogram_latch);
    qtest_add_data_func("/i8254/reprogram/pending", "pc",
                        test_pc_reprogram_pending);
    qtest_add_data_func("/i8254/reprogram/machine-on",
                        "generic-pc,pit-strict-programming=on",
                        test_pc_reprogram_pending);
    qtest_add_data_func("/i8254/reprogram/compat",
                        "-M pc,hpet=off -global i8254.strict-programming=off",
                        test_pc_reprogram_compat);
    qtest_add_data_func("/i8254/reprogram/machine-off",
                        "-M pc,hpet=off,pit-strict-programming=off",
                        test_pc_reprogram_compat);
    qtest_add_data_func("/i8254/cadence/bios", GUINT_TO_POINTER(65536),
                        test_pc_periodic_cadence);
    qtest_add_data_func("/i8254/cadence/1193", GUINT_TO_POINTER(1193),
                        test_pc_periodic_cadence);
    qtest_add_func("/i8254/model/i8253", test_i8253_model);
    qtest_add_func("/i8254/model/i8254", test_i8254_model);
    qtest_add_func("/i8254/model/initial-count", test_i8254_initial_count);
    qtest_add_data_func("/i8254/device/generic", "isa-pit", test_explicit_pit);
    qtest_add_data_func("/i8254/device/i8253", "i8253", test_explicit_pit);
    qtest_add_data_func("/i8254/device/i8254", "i8254", test_explicit_pit);
    qtest_add_func("/i8254/device/duplicate", test_explicit_pit_duplicate);
    qtest_add_data_func("/i8254/board/compat", GINT_TO_POINTER(0),
                        test_pc_chipset_controllers);
    qtest_add_data_func("/i8254/board/chipset", GINT_TO_POINTER(1),
                        test_pc_chipset_controllers);

    return g_test_run();
}
