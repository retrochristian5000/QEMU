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
                             "128,\"8-BIT LINEAR\",8,0,(8000),(0),(0)");
    response = modem_command(&fe, &out, "AT+VSM=128,8000\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VSM?\r");
    assert_response_contains(response, "\r\n128,8000\r\n");

    response = modem_command(&fe, &out, "AT+VLS=1\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VLS?\r");
    assert_response_contains(response, "\r\n1\r\n");

    response = modem_command(&fe, &out, "AT+VGR=96\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VGR?\r");
    assert_response_contains(response, "\r\n96\r\n");

    response = modem_command(&fe, &out, "AT+VGT=160\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VGT?\r");
    assert_response_contains(response, "\r\n160\r\n");

    response = modem_command(&fe, &out, "AT+VIP\r");
    assert_response_contains(response, "\r\nOK\r\n");
    response = modem_command(&fe, &out, "AT+VLS?\r");
    assert_response_contains(response, "\r\n0\r\n");
    response = modem_command(&fe, &out, "AT+VGR?\r");
    assert_response_contains(response, "\r\n128\r\n");
    response = modem_command(&fe, &out, "AT+VGT?\r");
    assert_response_contains(response, "\r\n128\r\n");

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

    return g_test_run();
}
