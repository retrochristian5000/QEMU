/*
 * QEMU Hayes-compatible modem voice control tests
 *
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/config-file.h"
#include "qemu/module.h"
#include "qemu/option.h"
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

static Chardev *modem_new(const char *label, const char *model)
{
    QemuOpts *opts;
    Chardev *chr;

    opts = qemu_opts_create(qemu_find_opts("chardev"), label, 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "modem", &error_abort);
    if (model) {
        qemu_opt_set(opts, "model", model, &error_abort);
    }

    chr = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    qemu_opts_del(opts);
    return chr;
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
    assert_response_contains(response, "DataPort Express 3740 (QEMU emulation)");
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

/* Lock down the current synthetic transcript, not the historical CRC. */
static void test_paradyne_3740_unimodem_probe(void)
{
    static const char *const expected[] = {
        "288", "000", "ROM NOT EMULATED",
        "Paradyne DataPort Express 3740 (QEMU emulation)",
        "QEMU Paradyne-compatible serial modem", "V1.0", "DATAPORT3740",
        "Paradyne-compatible data modem", "28800", "QEMU", "SERIAL MODEM",
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
        g_autofree char *reply = g_strdup_printf("\r\n%s\r\n\r\nOK\r\n",
                                                 expected[i]);

        g_assert_cmpstr(modem_command(&fe, &out, command), ==, reply);
    }
    g_assert_cmpstr(modem_command(&fe, &out, "AT%V\r"), ==,
                    "\r\nQEMU DataPort Express 3740 profile\r\n\r\nOK\r\n");
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
                             "DataPort Express 3740 (QEMU emulation)");
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

static void test_generic_modem_rejects_paradyne_controls(void)
{
    ModemOutput out = { 0 };
    CharFrontend fe = { 0 };
    Chardev *chr = modem_new("modem-generic-controls",
                             "hayes-accura-2400");
    const char *response;

    modem_frontend_init(&fe, &out, chr);
    response = modem_command(&fe, &out, "AT\\Q3\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\D1\r");
    assert_response_contains(response, "\r\nERROR\r\n");
    response = modem_command(&fe, &out, "AT\\A3\r");
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
    g_test_add_func("/modem/paradyne/3740-modulation",
                    test_dataport_3740_modulation);
    g_test_add_data_func("/modem/paradyne/family-3711",
                         "att-paradyne-dataport-3711",
                         test_dataport_family_controls);
    g_test_add_data_func("/modem/paradyne/family-3740",
                         "att-paradyne-3740", test_dataport_family_controls);
    g_test_add_func("/modem/paradyne/3740-unimodem-probe",
                    test_paradyne_3740_unimodem_probe);
    g_test_add_func("/modem/paradyne/3740-legacy-name",
                    test_paradyne_3740_legacy_name);
    g_test_add_func("/modem/paradyne/generic-isolation",
                    test_generic_modem_rejects_paradyne_controls);

    return g_test_run();
}
