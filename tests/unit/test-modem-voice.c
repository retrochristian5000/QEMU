/*
 * QEMU Hayes-compatible modem voice control tests
 *
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include <math.h>
#include "chardev/modem-v21.h"
#include "qapi/error.h"
#include "qemu/config-file.h"
#include "qemu/module.h"
#include "qemu/option.h"
#include "qemu/sockets.h"
#include "qemu/main-loop.h"
#include "io/channel-socket.h"
#include "qapi/qapi-types-sockets.h"
#include "chardev/char-fe.h"
#include "chardev/char-serial.h"
#include "chardev/modem.h"
#include "system/system.h"

typedef struct ModemOutput {
    char buf[4096];
    size_t len;
} ModemOutput;

static int modem_can_read(void *opaque)
{
    ModemOutput *out = opaque;

    return sizeof(out->buf) - out->len - 1;
}

static void modem_read(void *opaque, const uint8_t *buf, int size)
{
    ModemOutput *out = opaque;

    g_assert_cmpint(size, <=, modem_can_read(opaque));
    memcpy(out->buf + out->len, buf, size);
    out->len += size;
    out->buf[out->len] = '\0';
}

static Chardev *modem_new_with_port(const char *label, const char *model,
                                   const char *port)
{
    QemuOpts *opts;
    Chardev *chr;

    opts = qemu_opts_create(qemu_find_opts("chardev"), label, 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "modem", &error_abort);
    if (model) {
        qemu_opt_set(opts, "model", model, &error_abort);
    }

    if (port) {
        qemu_opt_set(opts, "host", "127.0.0.1", &error_abort);
        qemu_opt_set(opts, "port", port, &error_abort);
    }
    chr = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    qemu_opts_del(opts);
    return chr;
}

static Chardev *modem_new(const char *label, const char *model)
{
    return modem_new_with_port(label, model, NULL);
}

static const char *modem_command(CharFrontend *fe, ModemOutput *out,
                                 const char *command)
{
    int len = strlen(command);
    int ret;

    out->len = 0;
    out->buf[0] = '\0';
    ret = qemu_chr_fe_write(fe, (const uint8_t *)command, len);
    g_assert_cmpint(ret, ==, len);
    return out->buf;
}

static void assert_response_contains(const char *response, const char *text)
{
    g_assert_nonnull(strstr(response, text));
}

static void modem_frontend_init(CharFrontend *fe, ModemOutput *out,
                                Chardev *chr)
{
    qemu_chr_fe_init(fe, chr, &error_abort);
    qemu_chr_fe_set_handlers(fe, modem_can_read, modem_read,
                             NULL, NULL, out, NULL, true);
}

static void modem_frontend_cleanup(CharFrontend *fe, Chardev *chr)
{
    qemu_chr_fe_deinit(fe, false);
    object_unparent(OBJECT(chr));
}

static void test_data_model_rejects_voice(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-data", "hayes-accura-2400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);

    response = modem_command(&fe, &out, "AT+FCLASS=?\r");
    assert_response_contains(response, "\r\n0,1\r\n");

    response = modem_command(&fe, &out, "AT+FCLASS=8\r");
    assert_response_contains(response, "\r\nERROR\r\n");

    modem_frontend_cleanup(&fe, chr);
}

static void test_voice_class_and_reset(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-voice", "rockwell-voice-14400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);

    response = modem_command(&fe, &out, "AT+FCLASS=?\r");
    assert_response_contains(response, "\r\n0,1,8\r\n");

    response = modem_command(&fe, &out, "AT+FCLASS=8\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+FCLASS?\r");
    assert_response_contains(response, "\r\n8\r\n");

    response = modem_command(&fe, &out, "ATZ\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+FCLASS?\r");
    assert_response_contains(response, "\r\n0\r\n");

    response = modem_command(&fe, &out, "AT#CLS=8\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT#CLS?\r");
    assert_response_contains(response, "\r\n8\r\n");

    modem_frontend_cleanup(&fe, chr);
}

static void test_voice_configuration(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-voice-config", "rockwell-voice-14400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);

    response = modem_command(&fe, &out, "AT+FCLASS=8\r");
    assert_response_contains(response, "\r\nOK\r\n");

    response = modem_command(&fe, &out, "AT+VSM=?\r");
    assert_response_contains(response,
                             "+VSM: 128,\"8-BIT LINEAR\",8,0,(8000),(0),(0)");
    response = modem_command(&fe, &out, "AT+VSM=128,8000\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VSM?\r");
    assert_response_contains(response, "\r\n+VSM: 128,8000\r\n");

    response = modem_command(&fe, &out, "AT+VLS=1\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VLS?\r");
    assert_response_contains(response, "\r\n+VLS: 1\r\n");

    response = modem_command(&fe, &out, "AT+VGR=96\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VGR?\r");
    assert_response_contains(response, "\r\n+VGR: 96\r\n");

    response = modem_command(&fe, &out, "AT+VGT=160\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VGT?\r");
    assert_response_contains(response, "\r\n+VGT: 160\r\n");

    response = modem_command(&fe, &out, "AT+VIP\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VLS?\r");
    assert_response_contains(response, "\r\n+VLS: 0\r\n");
    response = modem_command(&fe, &out, "AT+VGR?\r");
    assert_response_contains(response, "\r\n+VGR: 128\r\n");
    response = modem_command(&fe, &out, "AT+VGT?\r");
    assert_response_contains(response, "\r\n+VGT: 128\r\n");

    modem_frontend_cleanup(&fe, chr);
}

static void test_voice_transport_is_not_advertised(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-voice-transport",
                             "rockwell-voice-14400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);
    modem_command(&fe, &out, "AT+FCLASS=8\r");

    response = modem_command(&fe, &out, "AT+VTX\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT+VRX\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT+VTR\r");
    assert_response_contains(response, "\r\nERROR\r\n");

    modem_frontend_cleanup(&fe, chr);
}

static void test_hardware_reset(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-hardware-reset", "rockwell-voice-14400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);
    response = modem_command(&fe, &out, "AT+FCLASS=8\r");
    assert_response_contains(response, "\r\nOK\r\n");

    qemu_modem_hardware_reset(chr);

    response = modem_command(&fe, &out, "AT+FCLASS?\r");
    assert_response_contains(response, "\r\n0\r\n");
    modem_frontend_cleanup(&fe, chr);
}

/* Paradyne settings are command-plane state, not real fax/line negotiation. */
static void test_paradyne_3711_profile(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-paradyne-3711",
                             "att-paradyne-dataport-3711");
    const char *response;

    modem_frontend_init(&fe, &out, chr);
    response = modem_command(&fe, &out, "ATI3\r");
    assert_response_contains(response, "DataPort Express 3711 (QEMU emulation)");
    response = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(response, "\\N6 \\Q3 DCE:14400");

    response = modem_command(&fe, &out, "ATE1V1&F\\N7\\Q3%C1S7=60\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(response, "\\N7 \\Q3 DCE:14400");
    assert_response_contains(response, "S07:060");

    response = modem_command(&fe, &out, "AT%B12000\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(response, "\\N7 \\Q3 DCE:12000");
    response = modem_command(&fe, &out, "AT%B28800\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\Q5\r");
    assert_response_contains(response, "\r\nERROR\r\n");

    response = modem_command(&fe, &out, "ATZ\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(response, "\\N6 \\Q3 DCE:14400");
    response = modem_command(&fe, &out, "AT+FCLASS=8\r");
    assert_response_contains(response, "\r\nERROR\r\n");

    modem_frontend_cleanup(&fe, chr);
}

static void test_paradyne_3740_profile(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-paradyne-3740",
                             "att-paradyne-3740");
    const char *response;

    modem_frontend_init(&fe, &out, chr);
    response = modem_command(&fe, &out, "ATI3\r");
    assert_response_contains(response,
                             "DataPort Express 3740 V.34 V.FC (QEMU emulation)");
    response = modem_command(&fe, &out, "AT\\N6\\Q3%B28800\r");
    assert_response_contains(response, "\r\nOK\r\n");
    /* Initialization used by the archived DataPort Express V.34 driver. */
    response = modem_command(&fe, &out, "ATE1V1&F\\N7\\Q3%C1S7=60\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(response, "\\N7 \\Q3 DCE:28800");
    assert_response_contains(response, "S07:060");
    response = modem_command(&fe, &out, "AT\\N8\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT%B16800\\Q4\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(response, "\\N7 \\Q4 DCE:16800");
    response = modem_command(&fe, &out, "AT%B999999999999999999999\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT%B28800\r");
    assert_response_contains(response, "\r\nOK\r\n");

    modem_frontend_cleanup(&fe, chr);
}

/* Reference-based probe replies, not a verified historical CRC. */
static void test_paradyne_3740_unimodem_probe(void)
{
    static const char *const expected[11] = {
        [0] = "28800",
        [3] = "AT&T DataPort Express 3740 V.34 V.FC (QEMU emulation)",
    };
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-paradyne-3740-probe",
                             "att-paradyne-3740");

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out, "ATE0Q0V1\r"),
                             "\r\nOK\r\n");
    for (unsigned i = 0; i < G_N_ELEMENTS(expected); i++) {
        g_autofree char *command = g_strdup_printf("ATI%u\r", i);
        g_autofree char *reply = expected[i] ?
            g_strdup_printf("\r\n%s\r\n\r\nOK\r\n", expected[i]) :
            g_strdup("\r\nERROR\r\n");

        g_assert_cmpstr(modem_command(&fe, &out, command), ==, reply);
    }
    g_assert_cmpstr(modem_command(&fe, &out, "AT%V\r"), ==,
                    "\r\nQEMU DataPort Express 3740 profile\r\n\r\nOK\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "ATI\r"), ==,
                    "\r\n28800\r\n\r\nOK\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "ATI19\r"), ==,
                    "\r\nERROR\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "ATV0I8\r"), ==, "\r\n4\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "ATV1\r"), ==, "\r\nOK\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "ATQ1I8\r"), ==, "");
    g_assert_cmpstr(modem_command(&fe, &out, "ATQ0I0\r"), ==,
                    "\r\n28800\r\n\r\nOK\r\n");
    modem_frontend_cleanup(&fe, chr);
}

static void test_paradyne_3740_legacy_name(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-paradyne-3740-legacy",
                             "att-paradyne-dataport-3740");

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out, "ATI3\r"),
                             "DataPort Express 3740 V.34 V.FC (QEMU emulation)");
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_family_controls(gconstpointer opaque)
{
    const char *model = opaque;
    bool v34 = !strcmp(model, "att-paradyne-3740");
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-dataport-family", model);
    int lines = 0;

    modem_frontend_init(&fe, &out, chr);
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &lines), ==, 0);
    g_assert_false(lines & CHR_TIOCM_CTS);
    lines = CHR_TIOCM_DTR;
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &lines), ==, 0);
    g_assert_true(lines & CHR_TIOCM_CTS);
    lines = 0;
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    assert_response_contains(modem_command(&fe, &out, "AT\\D0\\A1\r"),
                             "\r\nOK\r\n");
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &lines), ==, 0);
    g_assert_true(lines & CHR_TIOCM_CTS);
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\D0 \\A1");
    assert_response_contains(modem_command(&fe, &out, "AT\\A4\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT%M2\r"),
                             v34 ? "\r\nOK\r\n" : "\r\nERROR\r\n");
    if (!v34) {
        assert_response_contains(modem_command(&fe, &out, "AT%BL2400\r"),
                                 "\r\nERROR\r\n");
    }
    if (v34) {
        assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "%M2");
        assert_response_contains(modem_command(&fe, &out, "AT%M3\r"),
                                 "\r\nERROR\r\n");
    }
    assert_response_contains(modem_command(&fe, &out, "AT%V\r"),
                             v34 ? "DataPort Express 3740" :
                                   "DataPort Express 3711");
    assert_response_contains(modem_command(&fe, &out, "AT&F\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\D1 \\A3");
    if (v34) {
        assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "%M0");
    }
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &lines), ==, 0);
    g_assert_false(lines & CHR_TIOCM_CTS);
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_reliability_config(gconstpointer opaque)
{
    const char *model = opaque;
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-reliability-config", model);

    modem_frontend_init(&fe, &out, chr);

    /* Initial AOL 4.0 probe reported by the user. */
    static const char *const probe[] = {
        "AT\r", "AT\r", "ATH\r", "AT\r", "ATEQV1\r",
    };
    for (unsigned i = 0; i < ARRAY_SIZE(probe); i++) {
        assert_response_contains(modem_command(&fe, &out, probe[i]),
                                 "\r\nOK\r\n");
    }
    g_assert_cmpstr(modem_command(&fe, &out, "AT\r"), ==, "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\C0 %A19");

    for (unsigned i = 0; i <= 7; i++) {
        g_autofree char *command = g_strdup_printf("AT\\N%u\r", i);
        g_autofree char *setting = g_strdup_printf("\\N%u ", i);

        g_assert_cmpstr(modem_command(&fe, &out, command), ==,
                        "\r\nOK\r\n");
        assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                                 setting);
    }
    for (unsigned i = 0; i <= 2; i++) {
        g_autofree char *command = g_strdup_printf("AT\\C%u\r", i);
        g_autofree char *setting = g_strdup_printf("\\C%u ", i);

        g_assert_cmpstr(modem_command(&fe, &out, command), ==,
                        "\r\nOK\r\n");
        assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                                 setting);
    }
    g_assert_cmpstr(modem_command(&fe, &out, "AT%A127\r"), ==,
                    "\r\nOK\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "AT\\C3\r"), ==,
                    "\r\nERROR\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "AT%A128\r"), ==,
                    "\r\nERROR\r\n");
    g_assert_cmpstr(modem_command(&fe, &out, "AT\\N8\r"), ==,
                    "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\C2 %A127");
    assert_response_contains(modem_command(&fe, &out, "AT\\C%A\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\C0 %A0");

    assert_response_contains(modem_command(&fe, &out, "AT\\C1%A20&W0\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT\\C2%A0&W1&Y1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&F\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\C0 %A19");
    assert_response_contains(modem_command(&fe, &out, "ATZ\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\C1 %A20");
    qemu_modem_hardware_reset(chr);
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "\\C2 %A0");
    modem_frontend_cleanup(&fe, chr);
}

static void test_v21_signals(void)
{
    const unsigned frequencies[2][2] = { { 1180, 980 }, { 1850, 1650 } };
    const bool bits[] = { 1, 0, 1, 1, 0, 0, 1 };
    int16_t samples[MODEM_V21_SAMPLES_PER_BIT];

    for (unsigned ch = 0; ch < 2; ch++) {
        ModemV21Tx tx;
        double phase = 0;

        modem_v21_tx_init(&tx, ch);
        for (unsigned b = 0; b < ARRAY_SIZE(bits); b++) {
            double step = 2 * M_PI * frequencies[ch][bits[b]] / 9600;

            modem_v21_tx_bit(&tx, bits[b], samples);
            for (unsigned i = 0; i < ARRAY_SIZE(samples); i++) {
                /* Independent reference waveform including phase continuity. */
                int expected = lrint(12000 * sin(phase));

                g_assert_cmpint(abs(samples[i] - expected), <=, 1);
                phase += step;
            }
            g_assert_cmpint(modem_v21_rx_bit(ch, samples), ==, bits[b]);
        }
        for (unsigned bit = 0; bit < 2; bit++) {
            for (unsigned shift = 0; shift < 8; shift++) {
                for (unsigned i = 0; i < ARRAY_SIZE(samples); i++) {
                    samples[i] = lrint(8000 * sin(shift * M_PI / 4 +
                        2 * M_PI * frequencies[ch][bit] * i / 9600));
                }
                g_assert_cmpint(modem_v21_rx_bit(ch, samples), ==, bit);
            }
        }
        memset(samples, 0, sizeof(samples));
        g_assert_cmpint(modem_v21_rx_bit(ch, samples), ==, -1);
    }
}

static void test_dataport_v21_selection(gconstpointer opaque)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-v21-selection", opaque);

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out, "ATB0%B300&W0\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "REQUESTED MODULATION: V.21");
    assert_response_contains(modem_command(&fe, &out, "ATB2\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "REQUESTED MODULATION: V.21");
    assert_response_contains(modem_command(&fe, &out, "ATB1&W1&Y1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "REQUESTED MODULATION: BELL 103");
    assert_response_contains(modem_command(&fe, &out, "ATZ\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "REQUESTED MODULATION: V.21");
    qemu_modem_hardware_reset(chr);
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "REQUESTED MODULATION: BELL 103");
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_break_config(gconstpointer opaque)
{
    const char *model = opaque;
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-break-config", model);

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out, "ATE0Q0V1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K5");

    for (unsigned i = 0; i <= 5; i++) {
        g_autofree char *command = g_strdup_printf("AT\\K%u\r", i);
        g_autofree char *setting = g_strdup_printf("\\K%u", i);

        g_assert_cmpstr(modem_command(&fe, &out, command), ==,
                        "\r\nOK\r\n");
        assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                                 setting);
    }
    assert_response_contains(modem_command(&fe, &out, "AT\\K6\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out,
                             "AT\\K999999999999999999999\r"), "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K5");

    /* Bare \K selects zero, while &K remains a distinct command. */
    assert_response_contains(modem_command(&fe, &out, "AT\\K\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&K3\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K0");

    assert_response_contains(modem_command(&fe, &out, "AT\\K2&W0\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT\\K4&W1&Y1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&F\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K5");
    assert_response_contains(modem_command(&fe, &out, "ATZ\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K2");
    assert_response_contains(modem_command(&fe, &out, "ATZ1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K4");
    qemu_modem_hardware_reset(chr);
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\K4");
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_stored_profiles(gconstpointer opaque)
{
    const char *model = opaque;
    bool v34 = !strcmp(model, "att-paradyne-3740");
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-stored-profiles", model);
    const char *reply;

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out,
                             "AT&FX3\\Q0\\N7%C0S0=1E0V0&W\r"),
                             "\r\n0\r\n");
    assert_response_contains(modem_command(&fe, &out,
                             "ATV1&C0&D0\\D0\\A1\\X1S7=60&W1\r"),
                             "\r\nOK\r\n");
    if (v34) {
        assert_response_contains(modem_command(&fe, &out,
                                 "AT%M2%BL14400S76=1S78=1&W1\r"),
                                 "\r\nOK\r\n");
    }
    assert_response_contains(modem_command(&fe, &out, "AT&Y1&F\r"),
                             "\r\nOK\r\n");
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "&Y1");
    assert_response_contains(reply, "&C1 &D2 %C1");
    assert_response_contains(reply, "S00:000 S07:050");

    /* Z without an argument recalls 0, not the power-up selection. */
    assert_response_contains(modem_command(&fe, &out, "ATZ\r"), "\r\n0\r\n");
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "E0 Q0 V0 X3");
    assert_response_contains(reply, "\\N7 \\Q0");
    assert_response_contains(reply, "S00:001 S07:050");
    assert_response_contains(reply, "&Y1");

    assert_response_contains(modem_command(&fe, &out, "ATZ1\r"), "\r\nOK\r\n");
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "&C0 &D0 %C0");
    assert_response_contains(reply, "\\D0 \\A1 \\X1");
    assert_response_contains(reply, "S00:001 S07:060");
    if (v34) {
        assert_response_contains(reply, "%M2 %BL14400 S76:001 S78:001");
    }
    assert_response_contains(modem_command(&fe, &out, "AT&W2\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&Y2\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "ATZ2\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&F\r"),
                             "\r\nOK\r\n");
    qemu_modem_hardware_reset(chr);
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "&Y1");
    assert_response_contains(reply, "&C0 &D0 %C0");
    assert_response_contains(reply, "S00:001 S07:060");

    assert_response_contains(modem_command(&fe, &out, "AT&Y\r"),
                             "\r\nOK\r\n");
    qemu_modem_hardware_reset(chr);
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "&Y0");
    assert_response_contains(reply, "E0 Q0 V0 X3");
    assert_response_contains(reply, "S00:001 S07:050");
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_3740_modulation(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-dataport-modulation", "att-paradyne-3740");
    const char *reply;

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "%M0 %B28800 S76:000 S78:000");
    assert_response_contains(modem_command(&fe, &out, "AT%M2%B14400\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "VFC CONFIGURED RATE:ELIGIBLE");
    assert_response_contains(modem_command(&fe, &out, "AT%BL14400\r"),
                             "\r\nOK\r\n");
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "%M2 %BL14400");
    assert_response_contains(reply, "VFC CONFIGURED RATE:NOT ELIGIBLE");
    assert_response_contains(modem_command(&fe, &out, "AT%BL16800\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "%M2 %BL14400");
    assert_response_contains(modem_command(&fe, &out, "AT%B12000\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "VFC CONFIGURED RATE:NOT ELIGIBLE");
    assert_response_contains(modem_command(&fe, &out, "AT%M1%B28800\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "VFC CONFIGURED RATE:NOT ELIGIBLE");
    assert_response_contains(modem_command(&fe, &out, "ATS76=1S78=1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "ATS78=2\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "S76:001 S78:001");
    assert_response_contains(modem_command(&fe, &out, "AT&F\r"),
                             "\r\nOK\r\n");
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "%M0 %B28800 S76:000 S78:000");
    assert_response_contains(reply, "VFC CONFIGURED RATE:ELIGIBLE");
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_3740_fax_discovery(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-dataport-fax", "att-paradyne-3740");
    int lines = 0;

    modem_frontend_init(&fe, &out, chr);
    modem_command(&fe, &out, "ATE0\r");
    g_assert_cmpstr(modem_command(&fe, &out, "AT+FCLASS=?\r"), ==,
                    "\r\n0,1,2\r\n\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FCLASS=1\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FTM=?\r"),
                             "24,48,72,73,74,96,97,98,121,122,145,146");
    assert_response_contains(modem_command(&fe, &out, "AT+FRH=?\r"),
                             "3,24,48,72,73,74,96,97,98,121,122,145,146");
    assert_response_contains(modem_command(&fe, &out, "AT+FTM=146\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FCLASS=2.0\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FCLASS?\r"),
                             "\r\n1\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FCLASS=2\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FMFR?\r"),
                             "AT&T Paradyne");
    assert_response_contains(modem_command(&fe, &out, "AT+FMDL?\r"),
                             "DataPort Express 3740");
    assert_response_contains(modem_command(&fe, &out, "AT+FDCC=?\r"),
                             "(0-5)");
    assert_response_contains(modem_command(&fe, &out, "AT+FDCC?\r"),
                             "0,5,0,2,0,0,0,0");
    assert_response_contains(modem_command(&fe, &out, "AT+FDCC=0,3\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FDCC=1,6\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FDCC?\r"),
                             "0,3,0,2,0,0,0,0");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                             "DCE:28800");
    assert_response_contains(modem_command(&fe, &out, "ATD0\r"),
                             "NO DIALTONE");
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &lines), ==, 0);
    g_assert_false(lines & CHR_TIOCM_CAR);
    assert_response_contains(modem_command(&fe, &out, "AT+FDT\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&F\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT+FCLASS?\r"),
                             "\r\n0\r\n");
    modem_command(&fe, &out, "AT+FCLASS=2\r");
    assert_response_contains(modem_command(&fe, &out, "AT+FDCC?\r"),
                             "0,5,0,2,0,0,0,0");
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_xon_xoff_config(gconstpointer opaque)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-xon-config", opaque);

    modem_frontend_init(&fe, &out, chr);
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\X0");
    assert_response_contains(modem_command(&fe, &out, "AT\\Q1\\X1X4\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\X1");
    assert_response_contains(modem_command(&fe, &out, "AT\\X7\r"),
                             "\r\nERROR\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\X1");
    assert_response_contains(modem_command(&fe, &out, "AT\\X0\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\X0");
    modem_command(&fe, &out, "AT\\X1\r");
    modem_command(&fe, &out, "AT&F\r");
    assert_response_contains(modem_command(&fe, &out, "AT&V\r"), "\\X0");
    modem_frontend_cleanup(&fe, chr);
}

static void modem_test_wait_output(ModemOutput *out, const char *expected)
{
    int64_t deadline = g_get_monotonic_time() + 5 * G_TIME_SPAN_SECOND;

    while (!strstr(out->buf, expected) &&
           g_get_monotonic_time() < deadline) {
        main_loop_wait(true);
        g_usleep(1000);
    }
    assert_response_contains(out->buf, expected);
}

static void modem_test_expect_peer(QIOChannel *peer, const char *expected)
{
    uint8_t buf[8];
    size_t len = strlen(expected);
    size_t received = 0;
    int64_t deadline = g_get_monotonic_time() + 5 * G_TIME_SPAN_SECOND;

    g_assert_cmpuint(len, <=, sizeof(buf));
    while (received < len && g_get_monotonic_time() < deadline) {
        ssize_t ret = qio_channel_read(peer, buf + received,
                                       len - received, &error_abort);
        if (ret == QIO_CHANNEL_ERR_BLOCK) {
            main_loop_wait(true);
            g_usleep(1000);
        } else {
            g_assert_cmpint(ret, >, 0);
            received += ret;
        }
    }
    g_assert_cmpuint(received, ==, len);
    g_assert_cmpmem(buf, received, expected, len);
}

/*
 * Apple's MacPPP documentation gives this initialization string for
 * the related 14.4 kbit/s DataPort. Exercise it on both Express profiles.
 */
static void test_dataport_macppp_init(gconstpointer opaque)
{
    const char *model = opaque;
    SocketAddress address = {
        .type = SOCKET_ADDRESS_TYPE_INET,
        .u.inet = { .host = "127.0.0.1", .port = "0" },
    };
    QIOChannelSocket *listener = qio_channel_socket_new();
    QIOChannel *peer;
    SocketAddress *bound;
    Error *err = NULL;
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr;
    const char *reply;
    int lines = CHR_TIOCM_DTR | CHR_TIOCM_RTS;
    int status;

    if (qio_channel_socket_listen_sync(listener, &address, 1, &err) < 0) {
        g_test_skip(error_get_pretty(err));
        error_free(err);
        object_unref(OBJECT(listener));
        return;
    }
    bound = qio_channel_socket_get_local_address(listener, &error_abort);
    chr = modem_new_with_port("modem-macppp", model, bound->u.inet.port);
    qapi_free_SocketAddress(bound);
    modem_frontend_init(&fe, &out, chr);

    /* Start with contrasting settings so initialization must change them. */
    assert_response_contains(modem_command(&fe, &out, "AT\\N0%C0&C0&D2\\Q0\r"),
                             "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "AT\\N7%C1&C1&D0\\Q3\r"),
                             "\r\nOK\r\n");
    reply = modem_command(&fe, &out, "AT&V\r");
    assert_response_contains(reply, "&C1 &D0 %C1");
    assert_response_contains(reply, "\\N7 \\Q3");
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &status), ==, 0);
    g_assert_false(status & CHR_TIOCM_CAR);

    modem_command(&fe, &out, "ATD0\r");
    modem_test_wait_output(&out, "CONNECT");
    peer = QIO_CHANNEL(qio_channel_socket_accept(listener, &error_abort));
    g_assert_true(qio_channel_set_blocking(peer, false, &error_abort));
    object_unref(OBJECT(listener));

    /* DTR may change independently of RTS on the computer interface. */
    lines &= ~CHR_TIOCM_DTR;
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &status), ==, 0);
    g_assert_true(status & CHR_TIOCM_CAR);
    out.len = 0;
    out.buf[0] = '\0';
    g_assert_cmpint(qio_channel_write(peer, "mac", 3, &error_abort), ==, 3);
    modem_test_wait_output(&out, "mac");

    /* Restore DTR before sending commands: CTS may follow DTR. */
    lines |= CHR_TIOCM_DTR;
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    assert_response_contains(modem_command(&fe, &out, "+++"), "\r\nOK\r\n");
    assert_response_contains(modem_command(&fe, &out, "ATH\r"), "\r\nOK\r\n");
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_GET_TIOCM,
                                     &status), ==, 0);
    g_assert_false(status & CHR_TIOCM_CAR);
    modem_frontend_cleanup(&fe, chr);
    object_unref(OBJECT(peer));
}

static void test_dataport_xon_xoff_transport(gconstpointer opaque)
{
    int mode = GPOINTER_TO_INT(opaque);
    bool software = mode < 2;
    bool forward = mode != 0;
    bool rts_test = mode == 3;
    SocketAddress address = {
        .type = SOCKET_ADDRESS_TYPE_INET,
        .u.inet = { .host = "127.0.0.1", .port = "0" },
    };
    QIOChannelSocket *listener = qio_channel_socket_new();
    QIOChannel *peer;
    SocketAddress *bound;
    Error *err = NULL;
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr;
    int lines = CHR_TIOCM_DTR | CHR_TIOCM_RTS;
    int64_t deadline;

    if (qio_channel_socket_listen_sync(listener, &address, 1, &err) < 0) {
        g_test_skip(error_get_pretty(err));
        error_free(err);
        object_unref(OBJECT(listener));
        return;
    }
    bound = qio_channel_socket_get_local_address(listener, &error_abort);
    chr = modem_new_with_port("modem-xon-transport", "att-paradyne-3740",
                              bound->u.inet.port);
    qapi_free_SocketAddress(bound);
    modem_frontend_init(&fe, &out, chr);
    if (rts_test) {
        qemu_modem_command_log_set_enabled(true);
        lines &= ~CHR_TIOCM_RTS;
    }
    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    assert_response_contains(modem_command(&fe, &out, software ?
                             (forward ? "AT\\Q1\\X1\r" : "AT\\Q1\\X0\r") :
                             "AT\\Q3\\X0\r"), "\r\nOK\r\n");
    modem_command(&fe, &out, "ATD0\r");
    modem_test_wait_output(&out, "CONNECT");
    peer = QIO_CHANNEL(qio_channel_socket_accept(listener, &error_abort));
    g_assert_true(qio_channel_set_blocking(peer, false, &error_abort));
    object_unref(OBJECT(listener));

    modem_command(&fe, &out, "\x13" "A");
    modem_test_expect_peer(peer, forward ? "\x13" "A" : "A");
    g_assert_cmpint(qio_channel_write(peer, "held", 4, &error_abort), ==, 4);
    if (software || rts_test) {
        /* Give the local read watch a chance to queue the paused bytes. */
        deadline = g_get_monotonic_time() + 50 * G_TIME_SPAN_MILLISECOND;
        while (g_get_monotonic_time() < deadline) {
            main_loop_wait(true);
            g_assert_cmpuint(out.len, ==, 0);
            g_usleep(1000);
        }
    } else {
        modem_test_wait_output(&out, "held");
    }

    if (rts_test) {
        /* AT replies must be delivered even with RTS low. */
        assert_response_contains(modem_command(&fe, &out, "+++"),
                                 "\r\nOK\r\n");
        g_assert_null(strstr(out.buf, "held"));
        assert_response_contains(modem_command(&fe, &out, "AT\r"),
                                 "\r\nOK\r\n");
        assert_response_contains(modem_command(&fe, &out, "ATO\r"),
                                 "CONNECT");
        g_assert_null(strstr(out.buf, "held"));
        lines |= CHR_TIOCM_RTS;
        g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                         &lines), ==, 0);
        modem_test_wait_output(&out, "held");
    }
    modem_command(&fe, &out, "\x11" "B");
    modem_test_expect_peer(peer, forward ? "\x11" "B" : "B");
    if (software) {
        modem_test_wait_output(&out, "held");
    }

    modem_command(&fe, &out, "+++");
    assert_response_contains(modem_command(&fe, &out, "ATH\r"),
                             "\r\nOK\r\n");
    if (rts_test) {
        GPtrArray *snapshots = qemu_modem_indicator_snapshot();
        const ModemIndicatorSnapshot *snapshot =
            g_ptr_array_index(snapshots, 0);

        assert_response_contains(snapshot->command_log, "GUEST> ATD0\n");
        assert_response_contains(snapshot->command_log, "GUEST> +++\n");
        g_assert_null(strstr(snapshot->command_log, "held"));
        g_ptr_array_unref(snapshots);
        qemu_modem_command_log_set_enabled(false);
    }
    modem_frontend_cleanup(&fe, chr);
    object_unref(OBJECT(peer));
}

static void test_dataport_command_log(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-command-log", "att-paradyne-3740");
    GPtrArray *snapshots;
    ModemIndicatorSnapshot *snapshot;

    modem_frontend_init(&fe, &out, chr);
    qemu_modem_command_log_set_enabled(false);
    modem_command(&fe, &out, "ATI0\r");
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_null(snapshot->command_log);
    g_ptr_array_unref(snapshots);

    qemu_modem_command_log_set_enabled(true);
    modem_command(&fe, &out, "ATE0\r");
    modem_command(&fe, &out, "ATI0\r");
    modem_command(&fe, &out, "ATI8\r");
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    assert_response_contains(snapshot->command_log,
                             "GUEST> ATI0\nMODEM> 28800\nMODEM> OK\n");
    assert_response_contains(snapshot->command_log,
                             "GUEST> ATI8\nMODEM> ERROR\n");
    g_ptr_array_unref(snapshots);

    for (unsigned i = 0; i < 1000; i++) {
        modem_command(&fe, &out, "ATI0\r");
    }
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_cmpuint(strlen(snapshot->command_log), <=, 16 * 1024);
    g_assert_true(g_str_has_suffix(snapshot->command_log, "MODEM> OK\n"));
    g_ptr_array_unref(snapshots);

    qemu_modem_command_log_clear();
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_null(snapshot->command_log);
    g_ptr_array_unref(snapshots);
    modem_command(&fe, &out, "ATI0\r");
    qemu_modem_command_log_set_enabled(false);
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_null(snapshot->command_log);
    g_ptr_array_unref(snapshots);
    modem_frontend_cleanup(&fe, chr);
}

static void test_dataport_indicators(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-indicators", "att-paradyne-3740");
    Chardev *other = modem_new("modem-indicators-other", "hayes-accura-2400");
    GPtrArray *snapshots;
    ModemIndicatorSnapshot *snapshot;
    int lines = CHR_TIOCM_DTR;

    modem_frontend_init(&fe, &out, chr);
    snapshots = qemu_modem_indicator_snapshot();
    g_assert_cmpuint(snapshots->len, ==, 1);
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_cmpstr(snapshot->id, ==, "modem-indicators");
    g_assert_cmpuint(snapshot->active, ==, MODEM_LED_MR);
    g_assert_cmpuint(snapshot->supported &
                     (MODEM_LED_TST | MODEM_LED_HS | MODEM_LED_EC), ==, 0);
    g_ptr_array_unref(snapshots);

    g_assert_cmpint(qemu_chr_fe_ioctl(&fe, CHR_IOCTL_SERIAL_SET_TIOCM,
                                     &lines), ==, 0);
    modem_command(&fe, &out, "AT&C0\r");
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_cmpuint(snapshot->active, ==, MODEM_LED_MR | MODEM_LED_TR);
    g_assert_cmpuint(snapshot->rx_events, >, 0);
    g_assert_cmpuint(snapshot->tx_events, >, 0);
    g_ptr_array_unref(snapshots);

    qemu_modem_hardware_reset(chr);
    snapshots = qemu_modem_indicator_snapshot();
    snapshot = g_ptr_array_index(snapshots, 0);
    g_assert_cmpuint(snapshot->active, ==, MODEM_LED_MR);
    g_ptr_array_unref(snapshots);
    modem_frontend_cleanup(&fe, chr);
    object_unparent(OBJECT(other));
    snapshots = qemu_modem_indicator_snapshot();
    g_assert_cmpuint(snapshots->len, ==, 0);
    g_ptr_array_unref(snapshots);
}

static void test_modem_identity_isolation(void)
{
    static const struct {
        const char *model;
        const char *version;
        bool paradyne;
    } cases[] = {
        { "hayes-accura-2400", "QEMU Hayes modem V1.0", false },
        { "rockwell-voice-14400", "QEMU Rockwell-compatible voice modem",
          false },
        { "att-paradyne-dataport-3711", "QEMU DataPort Express 3711 profile",
          true },
        { "att-paradyne-3740", "QEMU DataPort Express 3740 profile", true },
    };

    for (unsigned i = 0; i < ARRAY_SIZE(cases); i++) {
        ModemOutput out = { 0 };
        CharFrontend fe = { 0 };
        Chardev *chr = modem_new("modem-identity-isolation", cases[i].model);
        g_autofree char *expected = g_strdup_printf("\r\n%s\r\n\r\nOK\r\n",
                                                    cases[i].version);

        modem_frontend_init(&fe, &out, chr);
        assert_response_contains(modem_command(&fe, &out, "ATE0Q0V1\r"),
                                 "\r\nOK\r\n");
        g_assert_cmpstr(modem_command(&fe, &out, "AT%V\r"), ==, expected);
        if (i != 0) {
            for (unsigned j = 0; j <= 11; j++) {
                g_autofree char *command = g_strdup_printf("ATI%u\r", j);

                g_assert_null(strstr(modem_command(&fe, &out, command),
                                     "Hayes"));
            }
        }
        if (cases[i].paradyne) {
            assert_response_contains(modem_command(&fe, &out, "AT%C0\r"),
                                     "\r\nOK\r\n");
            assert_response_contains(modem_command(&fe, &out, "AT%C2\r"),
                                     "\r\nERROR\r\n");
            assert_response_contains(modem_command(&fe, &out, "AT&V\r"),
                                     "%C0");
            assert_response_contains(modem_command(&fe, &out, "AT%C1\r"),
                                     "\r\nOK\r\n");
        }
        modem_frontend_cleanup(&fe, chr);
    }
}

static void test_generic_modem_rejects_paradyne_controls(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-generic-controls",
                             "hayes-accura-2400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);
    response = modem_command(&fe, &out, "AT+FCLASS=2\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\X1\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\Q3\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\D1\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\A3\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\K5\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\C1\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT%A19\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT%M0\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT%B14400\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT%BL2400\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT&V\r");
    g_assert_null(strstr(response, "DCE:"));
    modem_frontend_cleanup(&fe, chr);
}

int main(int argc, char **argv)
{
    qemu_init_main_loop(&error_abort);
    socket_init();
    g_test_init(&argc, &argv, NULL);
    module_call_init(MODULE_INIT_QOM);
    qemu_add_opts(&qemu_chardev_opts);

    g_test_add_func("/modem/voice/data-model-rejects-voice",
                    test_data_model_rejects_voice);
    g_test_add_func("/modem/voice/class-and-reset",
                    test_voice_class_and_reset);
    g_test_add_func("/modem/voice/configuration",
                    test_voice_configuration);
    g_test_add_func("/modem/voice/transport-not-advertised",
                    test_voice_transport_is_not_advertised);
    g_test_add_func("/modem/hardware-reset", test_hardware_reset);
    g_test_add_func("/modem/paradyne/3711", test_paradyne_3711_profile);
    g_test_add_func("/modem/paradyne/3740", test_paradyne_3740_profile);
    g_test_add_func("/modem/paradyne/3740-command-log",
                    test_dataport_command_log);
    g_test_add_func("/modem/paradyne/3740-indicators",
                    test_dataport_indicators);
    g_test_add_data_func("/modem/paradyne/xon-config-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_xon_xoff_config);
    g_test_add_data_func("/modem/paradyne/xon-config-3740",
                         "att-paradyne-3740",
                         test_dataport_xon_xoff_config);
    g_test_add_data_func("/modem/paradyne/xon-local", GINT_TO_POINTER(0),
                         test_dataport_xon_xoff_transport);
    g_test_add_data_func("/modem/paradyne/xon-forward", GINT_TO_POINTER(1),
                         test_dataport_xon_xoff_transport);
    g_test_add_data_func("/modem/paradyne/xon-hardware-mode", GINT_TO_POINTER(2),
                         test_dataport_xon_xoff_transport);
    g_test_add_data_func("/modem/paradyne/3740-rts-pacing", GINT_TO_POINTER(3),
                         test_dataport_xon_xoff_transport);
    g_test_add_func("/modem/paradyne/3740-fax-discovery",
                    test_dataport_3740_fax_discovery);
    g_test_add_func("/modem/paradyne/3740-modulation",
                    test_dataport_3740_modulation);
    g_test_add_data_func("/modem/paradyne/family-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_family_controls);
    g_test_add_data_func("/modem/paradyne/family-3740",
                         "att-paradyne-3740", test_dataport_family_controls);
    g_test_add_data_func("/modem/paradyne/macppp-3711",
                         "att-paradyne-dataport-3711", test_dataport_macppp_init);
    g_test_add_data_func("/modem/paradyne/macppp-3740",
                         "att-paradyne-3740", test_dataport_macppp_init);
    g_test_add_data_func("/modem/paradyne/reliability-config-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_reliability_config);
    g_test_add_data_func("/modem/paradyne/reliability-config-3740",
                         "att-paradyne-3740",
                         test_dataport_reliability_config);
    g_test_add_func("/modem/v21/signals", test_v21_signals);
    g_test_add_data_func("/modem/paradyne/v21-selection-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_v21_selection);
    g_test_add_data_func("/modem/paradyne/v21-selection-3740",
                         "att-paradyne-3740", test_dataport_v21_selection);
    g_test_add_data_func("/modem/paradyne/break-config-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_break_config);
    g_test_add_data_func("/modem/paradyne/break-config-3740",
                         "att-paradyne-3740", test_dataport_break_config);
    g_test_add_data_func("/modem/paradyne/stored-profiles-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_stored_profiles);
    g_test_add_data_func("/modem/paradyne/stored-profiles-3740",
                         "att-paradyne-3740", test_dataport_stored_profiles);
    g_test_add_func("/modem/paradyne/3740-unimodem-probe",
                    test_paradyne_3740_unimodem_probe);
    g_test_add_func("/modem/paradyne/3740-legacy-name",
                    test_paradyne_3740_legacy_name);
    g_test_add_func("/modem/identity-isolation",
                    test_modem_identity_isolation);
    g_test_add_func("/modem/paradyne/generic-isolation",
                    test_generic_modem_rejects_paradyne_controls);

    return g_test_run();
}
