/*
 * ISA MPU-401 UART and CT1740 shared interrupt tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"
#include "qobject/qdict.h"
#ifndef _WIN32
#include "qemu/sockets.h"
#endif

#define MIDI_FRAME_NS 320000

static void enter_uart(QTestState *s, unsigned int base)
{
    g_assert_cmphex(qtest_inb(s, base + 1), ==, 0x80);
    qtest_outb(s, base + 1, 0xff);
    g_assert_cmphex(qtest_inb(s, base + 1), ==, 0);
    g_assert_cmphex(qtest_inb(s, base), ==, 0xfe);
    g_assert_cmphex(qtest_inb(s, base + 1), ==, 0x80);
    qtest_outb(s, base + 1, 0x3f);
    g_assert_cmphex(qtest_inb(s, base + 1), ==, 0);
    g_assert_cmphex(qtest_inb(s, base), ==, 0xfe);
    g_assert_cmphex(qtest_inb(s, base + 1), ==, 0x80);
}

static void test_mpu_tx(void)
{
    static const uint8_t bytes[] = { 0x90, 0x3c, 0x7f };
    QTestState *s = qtest_init("-M pc -nodefaults "
                               "-chardev ringbuf,id=midi,size=4096 "
                               "-device mpu401-uart-compat,chardev=midi");
    QDict *reply;

    qtest_outb(s, 0x330, 0x55); /* Ignore data before UART mode. */
    enter_uart(s, 0x330);
    for (size_t i = 0; i < ARRAY_SIZE(bytes); i++) {
        qtest_outb(s, 0x330, bytes[i]);
        g_assert_cmphex(qtest_inb(s, 0x331), ==, 0xc0);
        qtest_clock_step(s, MIDI_FRAME_NS - 1);
        g_assert_cmphex(qtest_inb(s, 0x331), ==, 0xc0);
        qtest_clock_step(s, 1);
        g_assert_cmphex(qtest_inb(s, 0x331), ==, 0x80);
    }
    reply = qtest_qmp_assert_success_ref(s,
        "{'execute':'ringbuf-read','arguments':"
        "{'device':'midi','size':16,'format':'base64'}}");
    g_assert_cmpstr(qdict_get_str(reply, "return"), ==, "kDx/");
    qobject_unref(reply);

    qtest_outb(s, 0x330, 0x91);
    qtest_outb(s, 0x331, 0xff); /* Reset cancels pending transmit. */
    g_assert_cmphex(qtest_inb(s, 0x330), ==, 0xfe);
    qtest_clock_step(s, MIDI_FRAME_NS);
    reply = qtest_qmp_assert_success_ref(s,
        "{'execute':'ringbuf-read','arguments':"
        "{'device':'midi','size':16,'format':'base64'}}");
    g_assert_cmpstr(qdict_get_str(reply, "return"), ==, "");
    qobject_unref(reply);
    qtest_system_reset(s);
    g_assert_cmphex(qtest_inb(s, 0x331), ==, 0x80);
    qtest_quit(s);
}

static void check_midi_capture(QTestState *s, const char *id,
                               const char *expected)
{
    QDict *reply = qtest_qmp_assert_success_ref(s,
        "{'execute':'ringbuf-read','arguments':"
        "{'device':%s,'size':16,'format':'base64'}}", id);

    g_assert_cmpstr(qdict_get_str(reply, "return"), ==, expected);
    qobject_unref(reply);
}

static void test_sb16_waveblaster(gconstpointer opaque)
{
    const char *type = opaque;
    static const uint8_t bytes[] = { 0x90, 0x3c, 0x7f };
    QTestState *s = qtest_initf("-M pc -nodefaults -audiodev none,id=snd "
                                "-chardev ringbuf,id=midi,size=4096 "
                                "-chardev ringbuf,id=wave,size=4096 "
                                "-device %s,id=card,audiodev=snd,gameport=off,"
                                "midi-chardev=midi,waveblaster-chardev=wave",
                                type);

    enter_uart(s, 0x330);
    for (size_t i = 0; i < ARRAY_SIZE(bytes); i++) {
        qtest_outb(s, 0x330, bytes[i]);
        qtest_clock_step(s, MIDI_FRAME_NS - 1);
        g_assert_cmphex(qtest_inb(s, 0x331), ==, 0xc0);
        check_midi_capture(s, "midi", "");
        check_midi_capture(s, "wave", "");
        qtest_clock_step(s, 1);
        g_assert_cmphex(qtest_inb(s, 0x331), ==, 0x80);
        /* Read each frame before starting the next one. */
        g_autofree char *expected = g_base64_encode(bytes + i, 1);
        check_midi_capture(s, "midi", expected);
        check_midi_capture(s, "wave", expected);
    }

    qtest_outb(s, 0x330, 0x91);
    qtest_outb(s, 0x331, 0xff);
    g_assert_cmphex(qtest_inb(s, 0x330), ==, 0xfe);
    qtest_clock_step(s, MIDI_FRAME_NS);
    check_midi_capture(s, "midi", "");
    check_midi_capture(s, "wave", "");
    qtest_quit(s);
}

static uint8_t sb16_pending(QTestState *s)
{
    qtest_outb(s, 0x224, 0x82);
    return qtest_inb(s, 0x225) & 7;
}

static void test_sb16_shared_irq(gconstpointer opaque)
{
    unsigned int base = GPOINTER_TO_UINT(opaque);
    QTestState *s = qtest_initf("-M pc -nodefaults "
                                "-audiodev none,id=snd "
                                "-device sb16-ct1740,id=card,audiodev=snd,"
                                "mpu-iobase=0x%x", base);

    g_assert_true(qtest_qom_get_bool(s,
                      "/machine/peripheral/card/mpu401", "realized"));
    qtest_irq_intercept_in(s, "ioapic");
    qtest_outb(s, 0x226, 1);
    qtest_outb(s, 0x226, 0);
    qtest_inb(s, 0x22a);
    qtest_outb(s, base + 1, 0xff);
    g_assert_cmphex(qtest_inb(s, base), ==, 0xfe);
    qtest_outb(s, base + 1, 0x3f);
    g_assert_cmphex(sb16_pending(s), ==, 4);
    g_assert_true(qtest_get_irq(s, 5));

    qtest_outb(s, 0x22c, 0xf2);
    qtest_outb(s, 0x22c, 0xf3);
    g_assert_cmphex(sb16_pending(s), ==, 7);
    qtest_inb(s, 0x22e);
    g_assert_cmphex(sb16_pending(s), ==, 6);
    g_assert_true(qtest_get_irq(s, 5));
    g_assert_cmphex(qtest_inb(s, base), ==, 0xfe);
    g_assert_cmphex(sb16_pending(s), ==, 2);
    g_assert_true(qtest_get_irq(s, 5));
    qtest_inb(s, 0x22f);
    g_assert_cmphex(sb16_pending(s), ==, 0);
    g_assert_false(qtest_get_irq(s, 5));

    qtest_outb(s, base + 1, 0xff);
    qtest_inb(s, base);
    qtest_outb(s, base + 1, 0x3f);
    qtest_outb(s, 0x226, 1);
    qtest_outb(s, 0x226, 0);
    g_assert_cmphex(sb16_pending(s), ==, 4);
    g_assert_true(qtest_get_irq(s, 5));
    g_assert_cmphex(qtest_inb(s, base), ==, 0xfe);
    g_assert_cmphex(sb16_pending(s), ==, 0);
    g_assert_false(qtest_get_irq(s, 5));
    qtest_quit(s);
}

#ifndef _WIN32
/* Exercise the raw receive path through a real local character backend. */
static void test_sb16_midi_receive(void)
{
    static const uint8_t bytes[] = { 0x90, 0x3c, 0x7f };
    g_autofree char *dir = g_dir_make_tmp("qemu-mpu401-XXXXXX", NULL);
    g_autofree char *path = NULL;
    g_autofree char *arg = NULL;
    QTestState *s;
    int listener, peer;

    g_assert_nonnull(dir);
    path = g_build_filename(dir, "midi.sock", NULL);
    arg = g_shell_quote(path);
    listener = qtest_socket_server(path);
    s = qtest_initf("-M pc -nodefaults -audiodev none,id=snd "
                    "-chardev socket,id=midi,path=%s "
                    "-device sb16-ct1740,audiodev=snd,midi-chardev=midi", arg);
    peer = accept(listener, NULL, NULL);
    g_assert_cmpint(peer, >=, 0);
    close(listener);

    enter_uart(s, 0x330);
    g_assert_cmphex(sb16_pending(s), ==, 0);
    g_assert_cmpint(send(peer, bytes, sizeof(bytes), 0), ==, sizeof(bytes));
    for (size_t i = 0; i < ARRAY_SIZE(bytes); i++) {
        int64_t deadline = g_get_monotonic_time() + 5 * G_USEC_PER_SEC;

        while (qtest_inb(s, 0x331) & 0x80) {
            g_assert_cmpint(g_get_monotonic_time(), <, deadline);
            g_usleep(1000);
        }
        g_assert_cmphex(sb16_pending(s), ==, 4);
        g_assert_cmphex(qtest_inb(s, 0x330), ==, bytes[i]);
    }
    g_assert_cmphex(qtest_inb(s, 0x331), ==, 0x80);
    g_assert_cmphex(sb16_pending(s), ==, 0);
    qtest_quit(s);
    close(peer);
    unlink(path);
    rmdir(dir);
}
#endif

static void test_mpu_overlap(gconstpointer opaque)
{
    const char *devices = opaque;

    if (g_test_subprocess()) {
        QTestState *s = qtest_initf("-M pc -nodefaults "
                                    "-audiodev none,id=snd %s", devices);
        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*ISA I/O range*overlaps*");
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    if (qtest_has_machine("pc") && qtest_has_device("mpu401-uart-compat")) {
        qtest_add_func("/mpu401/tx", test_mpu_tx);
        if (qtest_has_device("sb16-ct1740")) {
            qtest_add_data_func("/mpu401/sb16/waveblaster", "sb16-ct1740",
                                test_sb16_waveblaster);
            qtest_add_data_func("/mpu401/sb16/waveblaster-alias", "sb16",
                                test_sb16_waveblaster);
#ifndef _WIN32
            qtest_add_func("/mpu401/sb16/receive", test_sb16_midi_receive);
#endif
            qtest_add_data_func("/mpu401/sb16/default", GUINT_TO_POINTER(0x330),
                                test_sb16_shared_irq);
            qtest_add_data_func("/mpu401/sb16/alternate", GUINT_TO_POINTER(0x300),
                                test_sb16_shared_irq);
            qtest_add_data_func("/mpu401/sb16/overlap-first",
                                "-device mpu401-uart-compat "
                                "-device sb16-ct1740,audiodev=snd", test_mpu_overlap);
            qtest_add_data_func("/mpu401/sb16/overlap-last",
                                "-device sb16-ct1740,audiodev=snd "
                                "-device mpu401-uart-compat", test_mpu_overlap);
        }
    }
    return g_test_run();
}
