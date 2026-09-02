/*
 * QEMU Hayes-compatible serial modem emulation
 *
 * Copyright 2026
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/fifo8.h"
#include "qemu/module.h"
#include "qemu/option.h"
#include "chardev/char.h"
#include "chardev/char-serial.h"
#include "qom/object.h"

#define TYPE_CHARDEV_MODEM "chardev-modem"
OBJECT_DECLARE_SIMPLE_TYPE(ModemChardev, CHARDEV_MODEM)

#define MODEM_OUTBUF_SIZE 4096
#define MODEM_COMMAND_SIZE 256
#define MODEM_SREG_COUNT 100
#define MODEM_DEFAULT_MODEL "hayes-accura-2400"

#define MODEM_INPUT_LINES (CHR_TIOCM_DTR | CHR_TIOCM_RTS)
#define MODEM_OUTPUT_LINES \
    (CHR_TIOCM_CTS | CHR_TIOCM_DSR | CHR_TIOCM_CAR | CHR_TIOCM_RI)

typedef enum ModemResult {
    MODEM_RESULT_OK,
    MODEM_RESULT_CONNECT,
    MODEM_RESULT_RING,
    MODEM_RESULT_NO_CARRIER,
    MODEM_RESULT_ERROR,
    MODEM_RESULT_NO_DIALTONE,
    MODEM_RESULT_BUSY,
    MODEM_RESULT_NO_ANSWER,
} ModemResult;

typedef struct ModemModel {
    const char *name;
    int connect_speed;
    const char *identification[11];
    const char *fallback_identification;
} ModemModel;

static const ModemModel modem_models[] = {
    {
        .name = MODEM_DEFAULT_MODEL,
        .connect_speed = 2400,
        .identification = {
            "240",
            "000",
            "ROM CHECKSUM OK",
            "Hayes Accura 2400",
            "QEMU Hayes-compatible modem",
            "V1.0",
            "RCV2400",
            "Hayes-compatible error correcting modem",
            "2400",
            "QEMU",
            "SERIAL MODEM",
        },
        .fallback_identification = "QEMU Hayes-compatible modem",
    },
};

struct ModemChardev {
    Chardev parent;

    const ModemModel *model;
    Fifo8 outbuf;
    QEMUSerialSetParams dte;
    int tiocm;
    int connect_speed;
    int sreg[MODEM_SREG_COUNT];

    char command[MODEM_COMMAND_SIZE];
    char last_command[MODEM_COMMAND_SIZE];
    size_t command_len;
    unsigned int plus_count;

    bool echo;
    bool quiet;
    bool verbose;
    bool connected;
    bool command_mode;
    bool carrier_follows_connection;
    bool compression;
    int dtr_mode;
    int x_mode;
    int w_mode;
};

static void modem_chr_accept_input(Chardev *chr)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);
    uint32_t len = qemu_chr_be_can_write(chr);
    uint32_t avail = fifo8_num_used(&modem->outbuf);

    while (len > 0 && avail > 0) {
        const uint8_t *buf;
        uint32_t size;

        buf = fifo8_pop_bufptr(&modem->outbuf, MIN(len, avail), &size);
        qemu_chr_be_write(chr, buf, size);
        len = qemu_chr_be_can_write(chr);
        avail -= size;
    }
}

static void modem_queue_bytes(ModemChardev *modem,
                              const uint8_t *buf, size_t len)
{
    size_t free = fifo8_num_free(&modem->outbuf);

    if (len > free) {
        len = free;
    }
    if (len) {
        fifo8_push_all(&modem->outbuf, buf, len);
        modem_chr_accept_input(CHARDEV(modem));
    }
}

static void modem_queue_string(ModemChardev *modem, const char *str)
{
    modem_queue_bytes(modem, (const uint8_t *)str, strlen(str));
}

static void modem_queue_line(ModemChardev *modem, const char *str)
{
    modem_queue_string(modem, "\r\n");
    modem_queue_string(modem, str);
    modem_queue_string(modem, "\r\n");
}

static void modem_update_carrier(ModemChardev *modem)
{
    modem->tiocm |= CHR_TIOCM_CTS | CHR_TIOCM_DSR;
    modem->tiocm &= ~CHR_TIOCM_RI;

    if (!modem->carrier_follows_connection || modem->connected) {
        modem->tiocm |= CHR_TIOCM_CAR;
    } else {
        modem->tiocm &= ~CHR_TIOCM_CAR;
    }
}

static void modem_result(ModemChardev *modem, ModemResult result)
{
    const char *text;
    const char *numeric;
    g_autofree char *connect = NULL;

    if (modem->quiet) {
        return;
    }

    switch (result) {
    case MODEM_RESULT_OK:
        text = "OK";
        numeric = "0";
        break;
    case MODEM_RESULT_CONNECT:
        connect = g_strdup_printf("CONNECT %d", modem->connect_speed);
        text = connect;
        numeric = "1";
        break;
    case MODEM_RESULT_RING:
        text = "RING";
        numeric = "2";
        break;
    case MODEM_RESULT_NO_CARRIER:
        text = "NO CARRIER";
        numeric = "3";
        break;
    case MODEM_RESULT_ERROR:
        text = "ERROR";
        numeric = "4";
        break;
    case MODEM_RESULT_NO_DIALTONE:
        text = "NO DIALTONE";
        numeric = "6";
        break;
    case MODEM_RESULT_BUSY:
        text = "BUSY";
        numeric = "7";
        break;
    case MODEM_RESULT_NO_ANSWER:
        text = "NO ANSWER";
        numeric = "8";
        break;
    default:
        g_assert_not_reached();
    }

    modem_queue_line(modem, modem->verbose ? text : numeric);
}

static const ModemModel *modem_model_find(const char *name)
{
    size_t i;

    for (i = 0; i < ARRAY_SIZE(modem_models); i++) {
        if (strcmp(name, modem_models[i].name) == 0) {
            return &modem_models[i];
        }
    }

    return NULL;
}

static void modem_model_defaults(ModemChardev *modem)
{
    memset(modem->sreg, 0, sizeof(modem->sreg));
    modem->sreg[0] = 0;
    modem->sreg[7] = 50;
    modem->sreg[30] = 0;
    modem->sreg[95] = 0;

    modem->echo = true;
    modem->quiet = false;
    modem->verbose = true;
    modem->carrier_follows_connection = true;
    modem->compression = true;
    modem->dtr_mode = 2;
    modem->x_mode = 4;
    modem->w_mode = 1;
    modem->connect_speed = modem->model->connect_speed;
    modem_update_carrier(modem);
}

static void modem_hangup(ModemChardev *modem, bool report)
{
    bool was_connected = modem->connected;

    modem->connected = false;
    modem->command_mode = true;
    modem->plus_count = 0;
    modem_update_carrier(modem);

    if (report && was_connected) {
        modem_result(modem, MODEM_RESULT_NO_CARRIER);
    }
}

static void modem_reset(ModemChardev *modem)
{
    modem_hangup(modem, false);
    modem_model_defaults(modem);
    modem->command_len = 0;
}

static int modem_parse_number(const char **command, int default_value)
{
    const char *p = *command;
    int value = 0;
    bool found = false;

    while (g_ascii_isdigit(*p)) {
        found = true;
        value = value * 10 + (*p - '0');
        p++;
    }
    *command = p;
    return found ? value : default_value;
}

static char *modem_normalize_command(const char *command)
{
    GString *normalized = g_string_sized_new(strlen(command) + 1);
    const unsigned char *p = (const unsigned char *)command;

    while (*p) {
        if (!g_ascii_isspace(*p)) {
            g_string_append_c(normalized, g_ascii_toupper(*p));
        }
        p++;
    }

    return g_string_free(normalized, false);
}

static void modem_report_identification(ModemChardev *modem, int index)
{
    const char *identification = modem->model->fallback_identification;

    if (index >= 0 &&
        (size_t)index < ARRAY_SIZE(modem->model->identification)) {
        identification = modem->model->identification[index];
    }
    modem_queue_line(modem, identification);
}

static void modem_report_profile(ModemChardev *modem)
{
    g_autofree char *line = NULL;

    modem_queue_line(modem, "ACTIVE PROFILE:");
    line = g_strdup_printf("E%d Q%d V%d X%d W%d &C%d &D%d %%C%d",
                           modem->echo, modem->quiet, modem->verbose,
                           modem->x_mode, modem->w_mode,
                           modem->carrier_follows_connection,
                           modem->dtr_mode, modem->compression);
    modem_queue_line(modem, line);
    g_clear_pointer(&line, g_free);
    line = g_strdup_printf("S00:%03d S07:%03d S30:%03d S95:%03d",
                           modem->sreg[0], modem->sreg[7],
                           modem->sreg[30], modem->sreg[95]);
    modem_queue_line(modem, line);
}

static void modem_connect(ModemChardev *modem)
{
    modem->connected = true;
    modem->command_mode = false;
    modem->plus_count = 0;
    modem_update_carrier(modem);
    modem_result(modem, MODEM_RESULT_CONNECT);
}

static bool modem_handle_extended(ModemChardev *modem, const char **command)
{
    const char *p = *command;

    if (g_str_has_prefix(p, "+FCLASS=?")) {
        modem_queue_line(modem, "0,1");
        *command = p + strlen("+FCLASS=?");
        return true;
    }
    if (g_str_has_prefix(p, "+FCLASS?")) {
        modem_queue_line(modem, "0");
        *command = p + strlen("+FCLASS?");
        return true;
    }
    if (g_str_has_prefix(p, "+FCLASS=")) {
        p += strlen("+FCLASS=");
        if (*p != '0' && *p != '1') {
            return false;
        }
        p++;
        *command = p;
        return true;
    }
    if (g_str_has_prefix(p, "+MS")) {
        while (*p && *p != ';') {
            p++;
        }
        if (*p == ';') {
            p++;
        }
        *command = p;
        return true;
    }

    return false;
}

static void modem_execute_command(ModemChardev *modem, const char *input)
{
    g_autofree char *normalized = modem_normalize_command(input);
    const char *p = normalized;

    if (strcmp(p, "A/") == 0) {
        if (!modem->last_command[0]) {
            modem_result(modem, MODEM_RESULT_ERROR);
            return;
        }
        normalized = g_strdup(modem->last_command);
        p = normalized;
    }

    if (!g_str_has_prefix(p, "AT")) {
        modem_result(modem, MODEM_RESULT_ERROR);
        return;
    }

    g_strlcpy(modem->last_command, p, sizeof(modem->last_command));
    p += 2;

    while (*p) {
        int value;
        int reg;

        switch (*p++) {
        case 'A':
            modem_connect(modem);
            return;
        case 'B':
        case 'L':
        case 'M':
        case 'N':
            modem_parse_number(&p, 0);
            break;
        case 'D':
            if (*p == 'T' || *p == 'P') {
                p++;
            }
            while (*p && *p != ';') {
                p++;
            }
            modem_connect(modem);
            return;
        case 'E':
            modem->echo = modem_parse_number(&p, 0) != 0;
            break;
        case 'H':
            modem_parse_number(&p, 0);
            modem_hangup(modem, false);
            break;
        case 'I':
            modem_report_identification(modem, modem_parse_number(&p, 0));
            break;
        case 'O':
            modem_parse_number(&p, 0);
            if (!modem->connected) {
                modem_result(modem, MODEM_RESULT_NO_CARRIER);
                return;
            }
            modem->command_mode = false;
            modem_result(modem, MODEM_RESULT_CONNECT);
            return;
        case 'P':
        case 'T':
            break;
        case 'Q':
            modem->quiet = modem_parse_number(&p, 0) != 0;
            break;
        case 'S':
            reg = modem_parse_number(&p, -1);
            if (reg < 0 || reg >= MODEM_SREG_COUNT) {
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            if (*p == '?') {
                g_autofree char *line = g_strdup_printf("%03d",
                                                        modem->sreg[reg]);
                modem_queue_line(modem, line);
                p++;
            } else if (*p == '=') {
                p++;
                value = modem_parse_number(&p, -1);
                if (value < 0 || value > 255) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                modem->sreg[reg] = value;
            } else {
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case 'V':
            modem->verbose = modem_parse_number(&p, 0) != 0;
            break;
        case 'W':
            modem->w_mode = modem_parse_number(&p, 0);
            break;
        case 'X':
            modem->x_mode = MIN(modem_parse_number(&p, 0), 4);
            break;
        case 'Z':
            modem_parse_number(&p, 0);
            modem_reset(modem);
            break;
        case '&':
            switch (*p++) {
            case 'C':
                modem->carrier_follows_connection =
                    modem_parse_number(&p, 0) != 0;
                modem_update_carrier(modem);
                break;
            case 'D':
                modem->dtr_mode = MIN(modem_parse_number(&p, 0), 2);
                break;
            case 'F':
                modem_parse_number(&p, 0);
                modem_model_defaults(modem);
                break;
            case 'K':
            case 'Q':
            case 'T':
                modem_parse_number(&p, 0);
                break;
            case 'V':
                modem_report_profile(modem);
                break;
            default:
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case '%':
            switch (*p++) {
            case 'C':
                modem->compression = modem_parse_number(&p, 0) != 0;
                break;
            case 'V':
                modem_queue_line(modem, "QEMU Hayes modem V1.0");
                break;
            default:
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case '+':
            p--;
            if (!modem_handle_extended(modem, &p)) {
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case '\\':
            if (*p == 'N') {
                p++;
                modem_parse_number(&p, 0);
                break;
            }
            modem_result(modem, MODEM_RESULT_ERROR);
            return;
        case ';':
            break;
        default:
            modem_result(modem, MODEM_RESULT_ERROR);
            return;
        }
    }

    modem_result(modem, MODEM_RESULT_OK);
}

static int modem_chr_write(Chardev *chr, const uint8_t *buf, int len)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);
    int i;

    for (i = 0; i < len; i++) {
        uint8_t c = buf[i];

        if (!modem->command_mode) {
            if (c == '+') {
                modem->plus_count++;
                if (modem->plus_count == 3) {
                    modem->plus_count = 0;
                    modem->command_mode = true;
                    modem_result(modem, MODEM_RESULT_OK);
                }
            } else {
                /*
                 * Online payload transport will be supplied by a wrapped
                 * chardev in a later step.  Consume it here like a modem with
                 * an established carrier but no remote payload source.
                 */
                modem->plus_count = 0;
            }
            continue;
        }

        if (modem->echo) {
            modem_queue_bytes(modem, &c, 1);
        }

        if (c == '\r') {
            modem->command[modem->command_len] = '\0';
            modem_execute_command(modem, modem->command);
            modem->command_len = 0;
        } else if (c == '\n') {
            continue;
        } else if (c == '\b' || c == 0x7f) {
            if (modem->command_len) {
                modem->command_len--;
            }
        } else if (modem->command_len + 1 < sizeof(modem->command)) {
            modem->command[modem->command_len++] = c;
        } else {
            modem->command_len = 0;
            modem_result(modem, MODEM_RESULT_ERROR);
        }
    }

    return len;
}

static int modem_chr_ioctl(Chardev *chr, int cmd, void *arg)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);

    switch (cmd) {
    case CHR_IOCTL_SERIAL_SET_PARAMS:
        modem->dte = *(QEMUSerialSetParams *)arg;
        return 0;
    case CHR_IOCTL_SERIAL_SET_BREAK:
        return 0;
    case CHR_IOCTL_SERIAL_SET_TIOCM:
    {
        int old = modem->tiocm;
        int input = *(int *)arg & MODEM_INPUT_LINES;

        modem->tiocm = (modem->tiocm & MODEM_OUTPUT_LINES) | input;
        modem_update_carrier(modem);

        if ((old & CHR_TIOCM_DTR) && !(input & CHR_TIOCM_DTR)) {
            if (modem->dtr_mode == 1 && modem->connected) {
                modem->command_mode = true;
            } else if (modem->dtr_mode == 2) {
                modem_hangup(modem, true);
            }
        }
        return 0;
    }
    case CHR_IOCTL_SERIAL_GET_TIOCM:
        *(int *)arg = modem->tiocm;
        return 0;
    default:
        return -ENOTSUP;
    }
}

static void modem_chr_update_read_handler(Chardev *chr)
{
    if (!chr->be_open) {
        qemu_chr_be_event(chr, CHR_EVENT_OPENED);
    }
    modem_chr_accept_input(chr);
}

static char *modem_chr_get_filename(Chardev *chr)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);

    return g_strdup_printf("modem:%s", modem->model->name);
}

static bool modem_chr_open(Chardev *chr,
                           ChardevBackend *backend,
                           Error **errp)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);
    const char *model_name = MODEM_DEFAULT_MODEL;

    if (backend && backend->u.modem.data &&
        backend->u.modem.data->model) {
        model_name = backend->u.modem.data->model;
    }
    modem->model = modem_model_find(model_name);
    if (!modem->model) {
        error_setg(errp, "Unsupported modem model '%s'", model_name);
        return false;
    }

    fifo8_create(&modem->outbuf, MODEM_OUTBUF_SIZE);
    modem->tiocm = CHR_TIOCM_CTS | CHR_TIOCM_DSR;
    modem->command_mode = true;
    modem_reset(modem);
    return true;
}

static void modem_chr_parse(QemuOpts *opts, ChardevBackend *backend,
                            Error **errp)
{
    ChardevModem *modem;

    backend->type = CHARDEV_BACKEND_KIND_MODEM;
    modem = backend->u.modem.data = g_new0(ChardevModem, 1);
    qemu_chr_parse_common(opts, qapi_ChardevModem_base(modem));
    modem->model = g_strdup(qemu_opt_get(opts, "model"));
}

static void modem_chr_finalize(Object *obj)
{
    ModemChardev *modem = CHARDEV_MODEM(obj);

    fifo8_destroy(&modem->outbuf);
}

static void modem_chr_class_init(ObjectClass *oc, const void *data)
{
    ChardevClass *cc = CHARDEV_CLASS(oc);

    cc->chr_parse = modem_chr_parse;
    cc->chr_open = modem_chr_open;
    cc->chr_write = modem_chr_write;
    cc->chr_accept_input = modem_chr_accept_input;
    cc->chr_ioctl = modem_chr_ioctl;
    cc->chr_update_read_handler = modem_chr_update_read_handler;
    cc->chr_get_filename = modem_chr_get_filename;
}

static const TypeInfo modem_chr_type_info = {
    .name = TYPE_CHARDEV_MODEM,
    .parent = TYPE_CHARDEV,
    .instance_size = sizeof(ModemChardev),
    .instance_finalize = modem_chr_finalize,
    .class_init = modem_chr_class_init,
};

static void register_types(void)
{
    type_register_static(&modem_chr_type_info);
}

type_init(register_types);
