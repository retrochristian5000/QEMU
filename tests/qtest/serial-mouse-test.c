/*
 * Serial mouse identification and modem-control regression.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

#define COM1 0x3f8
#define MCR (COM1 + 4)
#define LSR (COM1 + 5)

typedef struct MouseTest {
    const char *backend;
    const char *legacy_id;
    const char *pnp_id;
} MouseTest;

static const MouseTest profiles[] = {
    { "msmouse", "M", "PNP0F01" },
    { "logitech-mouseman", "M3", "PNP0F08" },
};

static void check_identification(QTestState *s, const MouseTest *test)
{
    uint8_t bytes[64];
    unsigned len = 0;
    size_t prefix = strlen(test->legacy_id);

    while (qtest_inb(s, LSR) & 1) {
        g_assert_cmpuint(len, <, sizeof(bytes));
        bytes[len++] = qtest_inb(s, COM1);
    }

    g_assert_cmpuint(len, >=, prefix + 10);
    g_assert_cmpmem(bytes, prefix, test->legacy_id, prefix);
    g_assert_cmphex(bytes[prefix], ==, '(' - 0x20);
    for (unsigned i = 0; i < 7; i++) {
        g_assert_cmphex(bytes[prefix + 3 + i] + 0x20, ==,
                        test->pnp_id[i]);
    }
    g_assert_cmphex(bytes[len - 1], ==, ')' - 0x20);
}

static void send_motion(QTestState *s, int x, int y)
{
    qtest_qmp_assert_success(s,
        "{'execute':'input-send-event','arguments':{'events':["
        "{'type':'rel','data':{'axis':'x','value':%d}},"
        "{'type':'rel','data':{'axis':'y','value':%d}}]}}", x, y);
}

static void expect_packet(QTestState *s, int x, int y, uint8_t buttons)
{
    uint8_t b[3];
    int dx, dy;

    for (size_t i = 0; i < ARRAY_SIZE(b); i++) {
        g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 1);
        b[i] = qtest_inb(s, COM1);
    }
    g_assert_cmphex(b[0] & 0x70, ==, 0x40 | buttons);
    g_assert_cmphex((b[1] | b[2]) & 0xc0, ==, 0);
    dx = ((b[0] & 3) << 6) | b[1];
    dy = ((b[0] & 12) << 4) | b[2];
    g_assert_cmpint(dx >= 128 ? dx - 256 : dx, ==, x);
    g_assert_cmpint(dy >= 128 ? dy - 256 : dy, ==, y);
}

static void send_button(QTestState *s, const char *button, bool down)
{
    qtest_qmp_assert_success(s, down ?
        "{'execute':'input-send-event','arguments':{'events':["
        "{'type':'btn','data':{'button':%s,'down':true}}]}}" :
        "{'execute':'input-send-event','arguments':{'events':["
        "{'type':'btn','data':{'button':%s,'down':false}}]}}", button);
}

static void test_mouse(gconstpointer opaque)
{
    const MouseTest *test = opaque;
    QTestState *s = qtest_initf(
        "-M pc,i8042=off,vmport=off -nodefaults -serial %s", test->backend);

    qtest_outb(s, COM1 + 3, 0x80);
    qtest_outb(s, COM1, 96); /* 115200 / 96 = 1200 baud */
    qtest_outb(s, COM1 + 1, 0);
    qtest_outb(s, COM1 + 3, 2); /* 7N1 */
    qtest_outb(s, COM1 + 2, 7); /* Enable and clear FIFO */
    qtest_outb(s, MCR, 0);
    qtest_outb(s, MCR, 1); /* DTR alone is not a completed reset. */
    g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 0);
    qtest_outb(s, MCR, 3);
    check_identification(s, test);

    /* Repeat detection by toggling only RTS, leaving DTR asserted. */
    qtest_outb(s, MCR, 1);
    qtest_outb(s, MCR, 3);
    check_identification(s, test);

    /* Signed packet boundaries and motion exceeding one packet. */
    send_motion(s, 200, -129);
    expect_packet(s, 127, -128, 0);
    expect_packet(s, 73, -1, 0);
    send_motion(s, -128, 127);
    expect_packet(s, -128, 127, 0);

    /* More than 64 bytes of packets with the UART FIFO disabled. */
    qtest_outb(s, COM1 + 2, 0);
    send_motion(s, 127 * 30 + 5, -128 * 30 - 6);
    for (int i = 0; i < 30; i++) {
        expect_packet(s, 127, -128, 0);
    }
    expect_packet(s, 5, -6, 0);
    g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 0);

    send_button(s, "left", true);
    expect_packet(s, 0, 0, 0x20);
    send_button(s, "left", false);
    expect_packet(s, 0, 0, 0);
    send_button(s, "wheel-up", true);
    g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 0);

    if (strcmp(test->backend, "logitech-mouseman") == 0) {
        send_button(s, "middle", true);
        expect_packet(s, 0, 0, 0);
        g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 1);
        g_assert_cmphex(qtest_inb(s, COM1), ==, 0x20);
        send_button(s, "middle", false);
        expect_packet(s, 0, 0, 0);
        g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 1);
        g_assert_cmphex(qtest_inb(s, COM1), ==, 0);
    } else {
        send_button(s, "middle", true);
        g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 0);
    }
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    for (unsigned i = 0; i < ARRAY_SIZE(profiles); i++) {
        g_autofree char *name = g_strdup_printf("/serial-mouse/%s",
                                                profiles[i].backend);
        qtest_add_data_func(name, &profiles[i], test_mouse);
    }
    return g_test_run();
}
