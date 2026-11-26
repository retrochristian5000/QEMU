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
#include <limits.h>
#include "qapi/error.h"
#include "qapi/qapi-types-sockets.h"
#include "qemu/fifo8.h"
#include "qemu/module.h"
#include "qemu/option.h"
#include "io/channel-socket.h"
#include "io/task.h"
#include "chardev/char.h"
#include "chardev/modem.h"
#include "chardev/char-serial.h"
#include "qom/object.h"
#include "qemu/timer.h"
#include "qemu/atomic.h"
#include "chardev-internal.h"
#include "trace.h"

#define TYPE_CHARDEV_MODEM "chardev-modem"
OBJECT_DECLARE_SIMPLE_TYPE(ModemChardev, CHARDEV_MODEM)

#define MODEM_OUTBUF_SIZE 4096
#define MODEM_NETBUF_SIZE 65536
#define MODEM_COMMAND_SIZE 256
#define MODEM_COMMAND_LOG_LIMIT (16 * 1024)
#define MODEM_SREG_COUNT 100
#define MODEM_XON 0x11
#define MODEM_XOFF 0x13
#define MODEM_DEFAULT_MODEL "hayes-accura-2400"
#define MODEM_VOICE_MODEL "rockwell-voice-14400"
#define MODEM_PARADYNE_3711 "att-paradyne-dataport-3711"
#define MODEM_PARADYNE_3740 "att-paradyne-3740"

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

typedef enum DataPortHighSpeedMode {
    DATAPORT_V34_AND_VFC = 0,
    DATAPORT_V34_ONLY,
    DATAPORT_VFC_ONLY,
} DataPortHighSpeedMode;

typedef struct ModemModel {
    const char *name;
    int connect_speed;
    int max_fax_rate; /* Separate from the data DCE rate. */
    bool supports_voice;
    bool paradyne_commands;
    bool dataport_3740_line;
    int max_reliable_mode;
    const char *identification[11];
    const char *fallback_identification;
} ModemModel;

static const ModemModel modem_models[] = {
    {
        .name = MODEM_DEFAULT_MODEL,
        .connect_speed = 2400,
        .supports_voice = false,
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
    {
        .name = MODEM_VOICE_MODEL,
        .connect_speed = 14400,
        .supports_voice = true,
        .identification = {
            "144",
            "000",
            "ROM CHECKSUM OK",
            "Rockwell-compatible 14.4 Voice",
            "QEMU Rockwell-compatible voice modem",
            "V1.0",
            "VOICE14400",
            "Hayes-compatible voice/fax/data modem",
            "14400",
            "QEMU",
            "VOICE MODEM",
        },
        .fallback_identification = "QEMU Rockwell-compatible voice modem",
    },
    {
        .name = MODEM_PARADYNE_3711,
        .connect_speed = 14400,
        .paradyne_commands = true,
        .max_reliable_mode = 7,
        .identification = {
            "144",
            "000",
            "ROM NOT EMULATED",
            "Paradyne DataPort Express 3711 (QEMU emulation)",
            "QEMU Paradyne-compatible serial modem",
            "V1.0",
            "DATAPORT3711",
            "Paradyne-compatible data modem",
            "14400",
            "QEMU",
            "SERIAL MODEM",
        },
        .fallback_identification = "QEMU DataPort Express 3711 profile",
    },
    {
        .name = MODEM_PARADYNE_3740,
        .connect_speed = 28800,
        .max_fax_rate = 14400,
        .paradyne_commands = true,
        .dataport_3740_line = true,
        /* The archived DataPort Express V.34 driver requests \N7. */
        .max_reliable_mode = 7,
        /*
         * Rockwell reference product code, corroborated by HylaFAX.
         * Exact OEM firmware replies are not recovered. NULL means
         * unavailable, not a known original firmware response.
         */
        .identification = {
            [0] = "28800",
            [3] = "AT&T DataPort Express 3740 V.34 V.FC (QEMU emulation)",
        },
        .fallback_identification = "QEMU DataPort Express 3740 profile",
    },
};

/* Only configuration, never connection state or host transport resources. */
typedef struct ModemStoredProfile {
    int sreg[MODEM_SREG_COUNT];
    int connect_speed;
    bool echo;
    bool quiet;
    bool verbose;
    bool carrier_follows_connection;
    bool cts_follows_dtr;
    bool compression;
    int dtr_mode;
    int x_mode;
    int w_mode;
    int reliable_mode;
    int flow_control_mode;
    bool xon_xoff_passthrough;
    int lapm_frame_size;
    DataPortHighSpeedMode v34_modulation;
    bool dataport_legacy_rate;
} ModemStoredProfile;

struct ModemChardev {
    Chardev parent;

    const ModemModel *model;
    ModemStoredProfile stored_profiles[2];
    unsigned powerup_profile;
    GString *command_log;
    Fifo8 outbuf;
    Fifo8 net_rxbuf; /* 3740: line payload, separate from AT replies. */
    Fifo8 net_txbuf;
    QIOChannel *tcp_ioc;
    guint tcp_read_tag;
    guint tcp_write_tag;
    char *tcp_host;
    char *tcp_port;
    QEMUSerialSetParams dte;
    int tiocm;
    unsigned indicator_active;
    unsigned indicator_rx_events;
    unsigned indicator_tx_events;
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
    bool offline_line; /* ISA hardware profiles have no attached line. */
    bool dialing;
    bool command_mode;
    bool carrier_follows_connection;
    bool cts_follows_dtr;
    bool compression;
    int dtr_mode;
    int x_mode;
    int w_mode;
    int reliable_mode;
    int flow_control_mode;
    bool xon_xoff_passthrough;
    bool dte_rx_paused;
    int lapm_frame_size;
    DataPortHighSpeedMode v34_modulation;
    bool dataport_legacy_rate;

    int service_class;
    uint8_t fax_dcc[8]; /* Class 2 requested capabilities, not negotiated. */
    int voice_line;
    int voice_compression;
    int voice_sample_rate;
    int voice_rx_gain;
    int voice_tx_gain;
};

static void modem_connect(ModemChardev *modem);
static void modem_hangup(ModemChardev *modem, bool report);
static void modem_tcp_arm_read(ModemChardev *modem);
static void modem_tcp_close(ModemChardev *modem);

static bool modem_dataport_rx_ready(const ModemChardev *modem)
{
    return modem->connected && !modem->command_mode &&
           !modem->dte_rx_paused &&
           (modem->flow_control_mode != 3 ||
            (modem->tiocm & CHR_TIOCM_RTS));
}

static Fifo8 *modem_line_rx_fifo(ModemChardev *modem)
{
    return modem->model->dataport_3740_line ?
           &modem->net_rxbuf : &modem->outbuf;
}

static void modem_drain_fifo(ModemChardev *modem, Fifo8 *fifo,
                             bool line_payload)
{
    Chardev *chr = CHARDEV(modem);

    while (!fifo8_is_empty(fifo)) {
        uint32_t len = qemu_chr_be_can_write(chr);
        const uint8_t *buf;
        uint32_t size;

        if (!len || (line_payload && !modem_dataport_rx_ready(modem))) {
            return;
        }
        buf = fifo8_pop_bufptr(fifo, MIN(len, fifo8_num_used(fifo)), &size);
        if (modem->model->dataport_3740_line) {
            qatomic_inc(&modem->indicator_rx_events);
        }
        qemu_chr_be_write(chr, buf, size);
    }
}

static void modem_chr_accept_input(Chardev *chr)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);

    /* Keep AT replies prompt even if the guest has paused line payload. */
    if (modem->model->dataport_3740_line ||
        !modem->dte_rx_paused || modem->command_mode) {
        modem_drain_fifo(modem, &modem->outbuf, false);
    }
    if (modem->model->dataport_3740_line &&
        fifo8_is_empty(&modem->outbuf)) {
        modem_drain_fifo(modem, &modem->net_rxbuf, true);
    }

    modem_tcp_arm_read(modem);
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

/* BQL serializes capture with the inspector and the modem callbacks. */
static bool modem_command_log_enabled;

static void modem_log_command_line(ModemChardev *modem,
                                   const char *direction, const char *str)
{
    GString *log;

    if (!modem_command_log_enabled || !modem->model ||
        !modem->model->dataport_3740_line) {
        return;
    }
    if (!modem->command_log) {
        modem->command_log = g_string_sized_new(1024);
    }
    log = modem->command_log;
    g_string_append_printf(log, "%s ", direction);
    for (const unsigned char *p = (const unsigned char *)str; *p; p++) {
        if (g_ascii_isprint(*p)) {
            g_string_append_c(log, *p);
        } else {
            g_string_append_printf(log, "\\x%02X", (unsigned)*p);
        }
    }
    g_string_append_c(log, '\n');
    if (log->len > MODEM_COMMAND_LOG_LIMIT) {
        const char *end = strchr(log->str + log->len -
                                 MODEM_COMMAND_LOG_LIMIT, '\n');

        g_string_erase(log, 0, end - log->str + 1);
    }
}

static void modem_queue_line(ModemChardev *modem, const char *str)
{
    modem_log_command_line(modem, "MODEM>", str);
    modem_queue_string(modem, "\r\n");
    modem_queue_string(modem, str);
    modem_queue_string(modem, "\r\n");
}

static void modem_queue_value(ModemChardev *modem,
                              const char *name, int value)
{
    g_autofree char *line = g_strdup_printf("%s: %d", name, value);

    modem_queue_line(modem, line);
}

/* CD is the simulated carrier, not the forced RS-232 &C0 output. */
static void modem_publish_indicators(ModemChardev *modem)
{
    unsigned active = MODEM_LED_MR;

    if (!modem->model || !modem->model->dataport_3740_line) {
        return;
    }
    if (modem->tiocm & CHR_TIOCM_DTR) {
        active |= MODEM_LED_TR;
    }
    if (modem->connected) {
        active |= MODEM_LED_CD;
    }
    if (modem->connected || modem->dialing) {
        active |= MODEM_LED_OH;
    }
    qatomic_set(&modem->indicator_active, active);
}

static void modem_indicator_snapshot_free(gpointer opaque)
{
    ModemIndicatorSnapshot *snapshot = opaque;

    g_free(snapshot->id);
    g_free(snapshot->model);
    g_free(snapshot->command_log);
    g_free(snapshot);
}

static int modem_indicator_collect(Object *obj, void *opaque)
{
    GPtrArray *snapshots = opaque;
    ModemChardev *modem;
    ModemIndicatorSnapshot *snapshot;

    if (!object_dynamic_cast(obj, TYPE_CHARDEV_MODEM)) {
        return 0;
    }
    modem = CHARDEV_MODEM(obj);
    if (!modem->model || !modem->model->dataport_3740_line) {
        return 0;
    }
    snapshot = g_new0(ModemIndicatorSnapshot, 1);
    snapshot->id = g_strdup(CHARDEV(modem)->label);
    snapshot->model = g_strdup(modem->model->name);
    snapshot->supported = MODEM_LED_MR | MODEM_LED_TR | MODEM_LED_CD |
                          MODEM_LED_OH | MODEM_LED_RD | MODEM_LED_SD;
    snapshot->active = qatomic_read(&modem->indicator_active);
    snapshot->rx_events = qatomic_read(&modem->indicator_rx_events);
    snapshot->tx_events = qatomic_read(&modem->indicator_tx_events);
    if (modem_command_log_enabled && modem->command_log) {
        snapshot->command_log = g_strdup(modem->command_log->str);
    }
    g_ptr_array_add(snapshots, snapshot);
    return 0;
}

GPtrArray *qemu_modem_indicator_snapshot(void)
{
    GPtrArray *snapshots =
        g_ptr_array_new_with_free_func(modem_indicator_snapshot_free);

    object_child_foreach(get_chardevs_root(), modem_indicator_collect,
                         snapshots);
    return snapshots;
}

static int modem_clear_command_log(Object *obj, void *opaque)
{
    if (object_dynamic_cast(obj, TYPE_CHARDEV_MODEM)) {
        ModemChardev *modem = CHARDEV_MODEM(obj);

        if (modem->command_log) {
            g_string_free(modem->command_log, true);
            modem->command_log = NULL;
        }
    }
    return 0;
}

void qemu_modem_command_log_clear(void)
{
    object_child_foreach(get_chardevs_root(), modem_clear_command_log, NULL);
}

void qemu_modem_command_log_set_enabled(bool enabled)
{
    if (modem_command_log_enabled != enabled) {
        qemu_modem_command_log_clear();
        modem_command_log_enabled = enabled;
    }
}

static void modem_update_carrier(ModemChardev *modem)
{
    modem->tiocm |= CHR_TIOCM_DSR;
    modem->tiocm &= ~CHR_TIOCM_RI;

    /* DataPort Express 3711/3740: \D0 forces CTS, \D1 follows DTR. */
    if (!modem->cts_follows_dtr || (modem->tiocm & CHR_TIOCM_DTR)) {
        modem->tiocm |= CHR_TIOCM_CTS;
    } else {
        modem->tiocm &= ~CHR_TIOCM_CTS;
    }

    if (!modem->carrier_follows_connection || modem->connected) {
        modem->tiocm |= CHR_TIOCM_CAR;
    } else {
        modem->tiocm &= ~CHR_TIOCM_CAR;
    }
    modem_publish_indicators(modem);
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

    /* Preserve the original command-line model spelling. */
    if (strcmp(name, "att-paradyne-dataport-3740") == 0) {
        name = MODEM_PARADYNE_3740;
    }

    for (i = 0; i < ARRAY_SIZE(modem_models); i++) {
        if (strcmp(name, modem_models[i].name) == 0) {
            return &modem_models[i];
        }
    }

    return NULL;
}

static void modem_voice_defaults(ModemChardev *modem)
{
    modem->voice_line = 0;
    modem->voice_compression = 128;
    modem->voice_sample_rate = 8000;
    modem->voice_rx_gain = 128;
    modem->voice_tx_gain = 128;
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
    modem->cts_follows_dtr = modem->model->paradyne_commands;
    modem->compression = true;
    modem->dtr_mode = 2;
    modem->x_mode = 4;
    modem->w_mode = 1;
    /* These are requested settings; no analogue negotiation is simulated. */
    modem->reliable_mode = modem->model->paradyne_commands ? 6 : 0;
    modem->flow_control_mode = modem->model->paradyne_commands ? 3 : 0;
    modem->xon_xoff_passthrough = false;
    modem->dte_rx_paused = false;
    modem->lapm_frame_size = 256;
    modem->v34_modulation = DATAPORT_V34_AND_VFC;
    modem->dataport_legacy_rate = false;
    modem->connect_speed = modem->model->connect_speed;
    modem->service_class = 0;
    memset(modem->fax_dcc, 0, sizeof(modem->fax_dcc));
    if (modem->model->max_fax_rate) {
        modem->fax_dcc[1] = modem->model->max_fax_rate / 2400 - 1;
        modem->fax_dcc[3] = 2; /* Unlimited page length. */
    }
    modem_voice_defaults(modem);
    modem_update_carrier(modem);
}

static void modem_hangup(ModemChardev *modem, bool report)
{
    bool was_connected = modem->connected ||
                         (modem->model->dataport_3740_line && modem->dialing);

    modem_tcp_close(modem);
    modem->connected = false;
    modem->command_mode = true;
    modem->dte_rx_paused = false;
    modem->plus_count = 0;
    modem_update_carrier(modem);

    if (report && was_connected) {
        modem_result(modem, MODEM_RESULT_NO_CARRIER);
    }
}

static void modem_store_profile(ModemChardev *modem, unsigned index)
{
    ModemStoredProfile *profile = &modem->stored_profiles[index];

    memcpy(profile->sreg, modem->sreg, sizeof(profile->sreg));
    profile->connect_speed = modem->connect_speed;
    profile->echo = modem->echo;
    profile->quiet = modem->quiet;
    profile->verbose = modem->verbose;
    profile->carrier_follows_connection = modem->carrier_follows_connection;
    profile->cts_follows_dtr = modem->cts_follows_dtr;
    profile->compression = modem->compression;
    profile->dtr_mode = modem->dtr_mode;
    profile->x_mode = modem->x_mode;
    profile->w_mode = modem->w_mode;
    profile->reliable_mode = modem->reliable_mode;
    profile->flow_control_mode = modem->flow_control_mode;
    profile->xon_xoff_passthrough = modem->xon_xoff_passthrough;
    profile->lapm_frame_size = modem->lapm_frame_size;
    profile->v34_modulation = modem->v34_modulation;
    profile->dataport_legacy_rate = modem->dataport_legacy_rate;
}

static void modem_restore_profile(ModemChardev *modem, unsigned index)
{
    const ModemStoredProfile *profile = &modem->stored_profiles[index];

    memcpy(modem->sreg, profile->sreg, sizeof(modem->sreg));
    modem->connect_speed = profile->connect_speed;
    modem->echo = profile->echo;
    modem->quiet = profile->quiet;
    modem->verbose = profile->verbose;
    modem->carrier_follows_connection = profile->carrier_follows_connection;
    modem->cts_follows_dtr = profile->cts_follows_dtr;
    modem->compression = profile->compression;
    modem->dtr_mode = profile->dtr_mode;
    modem->x_mode = profile->x_mode;
    modem->w_mode = profile->w_mode;
    modem->reliable_mode = profile->reliable_mode;
    modem->flow_control_mode = profile->flow_control_mode;
    modem->xon_xoff_passthrough = profile->xon_xoff_passthrough;
    modem->lapm_frame_size = profile->lapm_frame_size;
    modem->v34_modulation = profile->v34_modulation;
    modem->dataport_legacy_rate = profile->dataport_legacy_rate;
    modem_update_carrier(modem);
}

static void modem_reset(ModemChardev *modem, unsigned index)
{
    modem_hangup(modem, false);
    modem_model_defaults(modem);
    if (modem->model->paradyne_commands) {
        modem_restore_profile(modem, index);
    }
    modem->command_len = 0;
}

void qemu_modem_hardware_reset(Chardev *chr)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);

    /* Physical reset drops pending data, unlike the ATZ soft reset. */
    fifo8_reset(&modem->outbuf);
    fifo8_reset(&modem->net_txbuf);
    /* The owned UART resets MCR with DTR and RTS deasserted. */
    modem->tiocm &= ~MODEM_INPUT_LINES;
    modem->last_command[0] = '\0';
    modem_reset(modem, modem->powerup_profile);
}

static int modem_parse_number(const char **command, int default_value)
{
    const char *p = *command;
    int value = 0;
    bool found = false;

    while (g_ascii_isdigit(*p)) {
        found = true;
        int digit = *p - '0';

        /* Keep malformed oversized AT numbers from overflowing a signed int. */
        value = value > (INT_MAX - digit) / 10 ?
                INT_MAX : value * 10 + digit;
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

static bool modem_report_identification(ModemChardev *modem, int index)
{
    const char *identification = modem->model->fallback_identification;

    if (index >= 0 &&
        (size_t)index < ARRAY_SIZE(modem->model->identification)) {
        identification = modem->model->identification[index];
    } else if (modem->model->dataport_3740_line) {
        identification = NULL;
    }
    if (modem->model->dataport_3740_line) {
        trace_dataport_3740_ident(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                                 index, identification ?
                                 identification : "ERROR");
    }
    if (!identification) {
        return false;
    }
    modem_queue_line(modem, identification);
    return true;
}

/* Rockwell V.FC supports 14.4 to 28.8 kbit/s in 2.4 kbit/s steps. */
static bool modem_dataport_vfc_rate(int speed)
{
    return speed >= 14400 && speed <= 28800 && speed % 2400 == 0;
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
    if (modem->model->paradyne_commands) {
        g_clear_pointer(&line, g_free);
        line = g_strdup_printf("&Y%u", modem->powerup_profile);
        modem_queue_line(modem, line);
        g_clear_pointer(&line, g_free);
        line = g_strdup_printf("\\N%d \\Q%d DCE:%d",
                               modem->reliable_mode, modem->flow_control_mode,
                               modem->connect_speed);
        modem_queue_line(modem, line);
        g_clear_pointer(&line, g_free);
        line = g_strdup_printf("\\D%d \\A%d \\X%d",
                               modem->cts_follows_dtr,
                               modem->lapm_frame_size / 64 - 1,
                               modem->xon_xoff_passthrough);
        modem_queue_line(modem, line);
        if (modem->model->dataport_3740_line) {
            g_clear_pointer(&line, g_free);
            line = g_strdup_printf("%%M%d %%B%s%d S76:%03d S78:%03d",
                                   modem->v34_modulation,
                                   modem->dataport_legacy_rate ? "L" : "",
                                   modem->connect_speed, modem->sreg[76],
                                   modem->sreg[78]);
            modem_queue_line(modem, line);
            g_clear_pointer(&line, g_free);
            line = g_strdup_printf("VFC CONFIGURED RATE:%s",
                !modem->dataport_legacy_rate &&
                modem->v34_modulation != DATAPORT_V34_ONLY &&
                modem_dataport_vfc_rate(modem->connect_speed) ?
                "ELIGIBLE" : "NOT ELIGIBLE");
            modem_queue_line(modem, line);
        }
    }
}

static void modem_connect(ModemChardev *modem)
{
    modem->connected = true;
    modem->dte_rx_paused = false;
    modem->plus_count = 0;
    modem_update_carrier(modem);
    if (modem->model->dataport_3740_line) {
        /* Finish CONNECT before releasing any buffered line payload. */
        modem_result(modem, MODEM_RESULT_CONNECT);
        modem->command_mode = false;
        modem_chr_accept_input(CHARDEV(modem));
    } else {
        modem->command_mode = false;
        modem_result(modem, MODEM_RESULT_CONNECT);
    }
}

static void modem_tcp_close(ModemChardev *modem)
{
    if (modem->tcp_read_tag) {
        g_source_remove(modem->tcp_read_tag);
        modem->tcp_read_tag = 0;
    }
    if (modem->tcp_write_tag) {
        g_source_remove(modem->tcp_write_tag);
        modem->tcp_write_tag = 0;
    }
    if (modem->tcp_ioc) {
        qio_channel_close(modem->tcp_ioc, NULL);
        object_unref(OBJECT(modem->tcp_ioc));
        modem->tcp_ioc = NULL;
    }
    modem->dialing = false;
    modem_publish_indicators(modem);
    fifo8_reset(&modem->net_txbuf);
    if (modem->model && modem->model->dataport_3740_line) {
        fifo8_reset(&modem->net_rxbuf);
    }
}

static gboolean modem_tcp_read_ready(QIOChannel *ioc, GIOCondition condition,
                                     gpointer opaque)
{
    ModemChardev *modem = opaque;
    uint8_t buf[4096];
    size_t avail;
    ssize_t ret;
    Error *err = NULL;

    (void)condition;
    if (ioc != modem->tcp_ioc) {
        return G_SOURCE_REMOVE;
    }

    avail = fifo8_num_free(modem_line_rx_fifo(modem));
    if (!avail) {
        modem->tcp_read_tag = 0;
        return G_SOURCE_REMOVE;
    }

    ret = qio_channel_read(ioc, buf, MIN(sizeof(buf), avail), &err);
    if (ret > 0) {
        if (modem->model->dataport_3740_line) {
            fifo8_push_all(&modem->net_rxbuf, buf, ret);
            modem_chr_accept_input(CHARDEV(modem));
        } else {
            modem_queue_bytes(modem, buf, ret);
        }
        if (!fifo8_num_free(modem_line_rx_fifo(modem))) {
            modem->tcp_read_tag = 0;
            return G_SOURCE_REMOVE;
        }
        return G_SOURCE_CONTINUE;
    }
    if (ret == QIO_CHANNEL_ERR_BLOCK) {
        error_free(err);
        return G_SOURCE_CONTINUE;
    }

    error_free(err);
    modem->tcp_read_tag = 0;
    modem_hangup(modem, true);
    return G_SOURCE_REMOVE;
}

static void modem_tcp_arm_read(ModemChardev *modem)
{
    if (!modem->tcp_ioc || !modem->connected || modem->tcp_read_tag ||
        !fifo8_num_free(modem_line_rx_fifo(modem))) {
        return;
    }

    modem->tcp_read_tag =
        qio_channel_add_watch(modem->tcp_ioc,
                              G_IO_IN | G_IO_HUP | G_IO_ERR,
                              modem_tcp_read_ready, modem, NULL);
}

static void modem_tcp_flush(ModemChardev *modem);

static gboolean modem_tcp_write_ready(QIOChannel *ioc, GIOCondition condition,
                                      gpointer opaque)
{
    ModemChardev *modem = opaque;

    (void)condition;
    if (ioc != modem->tcp_ioc) {
        return G_SOURCE_REMOVE;
    }

    modem->tcp_write_tag = 0;
    modem_tcp_flush(modem);
    return G_SOURCE_REMOVE;
}

static void modem_tcp_flush(ModemChardev *modem)
{
    while (modem->tcp_ioc && fifo8_num_used(&modem->net_txbuf)) {
        const uint8_t *buf;
        uint32_t size;
        ssize_t ret;
        Error *err = NULL;

        buf = fifo8_peek_bufptr(&modem->net_txbuf,
                                fifo8_num_used(&modem->net_txbuf), &size);
        ret = qio_channel_write(modem->tcp_ioc, buf, size, &err);
        if (ret > 0) {
            fifo8_drop(&modem->net_txbuf, ret);
            continue;
        }
        if (ret == QIO_CHANNEL_ERR_BLOCK) {
            error_free(err);
            if (!modem->tcp_write_tag) {
                modem->tcp_write_tag =
                    qio_channel_add_watch(modem->tcp_ioc,
                                          G_IO_OUT | G_IO_HUP | G_IO_ERR,
                                          modem_tcp_write_ready, modem, NULL);
            }
            return;
        }

        error_free(err);
        modem_hangup(modem, true);
        return;
    }
}

static bool modem_tcp_queue(ModemChardev *modem,
                            const uint8_t *buf, size_t len)
{
    if (!modem->tcp_ioc) {
        return true;
    }
    if (len > fifo8_num_free(&modem->net_txbuf)) {
        return false;
    }

    fifo8_push_all(&modem->net_txbuf, buf, len);
    modem_tcp_flush(modem);
    return true;
}

static void modem_tcp_connected(QIOTask *task, gpointer opaque)
{
    ModemChardev *modem = opaque;
    QIOChannelSocket *sioc =
        QIO_CHANNEL_SOCKET(qio_task_get_source(task));
    QIOChannel *ioc = QIO_CHANNEL(sioc);
    Error *err = NULL;

    if (qio_task_propagate_error(task, &err)) {
        if (modem->tcp_ioc == ioc && modem->dialing) {
            modem_tcp_close(modem);
            modem_result(modem, MODEM_RESULT_NO_CARRIER);
        }
        error_free(err);
        return;
    }

    if (modem->tcp_ioc != ioc || !modem->dialing) {
        return;
    }
    modem->dialing = false;

    if (!qio_channel_set_blocking(ioc, false, &err)) {
        modem_tcp_close(modem);
        modem_result(modem, MODEM_RESULT_NO_CARRIER);
        error_free(err);
        return;
    }

    qio_channel_set_delay(ioc, false);
    modem_connect(modem);
    modem_tcp_arm_read(modem);
}

static void modem_dial(ModemChardev *modem)
{
    QIOChannelSocket *sioc;
    SocketAddress addr = {
        .type = SOCKET_ADDRESS_TYPE_INET,
    };

    if (modem->offline_line ||
        (modem->model->dataport_3740_line && !modem->tcp_host)) {
        /* Blind dialing cannot detect a missing dial tone. It still
         * cannot establish a carrier on a disconnected line. */
        bool blind = modem->model->dataport_3740_line &&
                     (modem->x_mode == 0 || modem->x_mode == 1 ||
                      modem->x_mode == 3);
        modem_hangup(modem, false);
        modem_result(modem, blind ? MODEM_RESULT_NO_CARRIER :
                                    MODEM_RESULT_NO_DIALTONE);
        return;
    }
    if (modem->model->max_fax_rate && modem->service_class != 0) {
        /* The TCP byte stream cannot carry an analogue fax session. */
        modem_hangup(modem, false);
        modem_result(modem, MODEM_RESULT_NO_CARRIER);
        return;
    }
    if (!modem->tcp_host) {
        modem_connect(modem);
        return;
    }

    modem_hangup(modem, false);
    addr.u.inet.host = modem->tcp_host;
    addr.u.inet.port = modem->tcp_port;

    sioc = qio_channel_socket_new();
    modem->tcp_ioc = QIO_CHANNEL(sioc);
    modem->dialing = true;
    modem_publish_indicators(modem);
    qio_channel_set_name(modem->tcp_ioc, "modem-tcp");
    qio_channel_socket_connect_async(sioc, &addr,
                                     modem_tcp_connected,
                                     object_ref(OBJECT(modem)),
                                     object_unref, NULL);
}

static bool modem_handle_service_class(ModemChardev *modem,
                                       const char **command,
                                       const char *prefix)
{
    const char *p = *command;
    int value;

    if (!g_str_has_prefix(p, prefix)) {
        return false;
    }
    p += strlen(prefix);

    if (g_str_has_prefix(p, "=?")) {
        modem_queue_line(modem, modem->model->max_fax_rate ? "0,1,2" :
                         modem->model->supports_voice ? "0,1,8" : "0,1");
        p += 2;
    } else if (*p == '?') {
        g_autofree char *line = g_strdup_printf("%d", modem->service_class);

        modem_queue_line(modem, line);
        p++;
    } else if (*p == '=') {
        p++;
        value = modem_parse_number(&p, -1);
        if ((value != 0 && value != 1 &&
             !(value == 2 && modem->model->max_fax_rate) &&
             !(value == 8 && modem->model->supports_voice)) ||
            *p == '.' ||
            (modem->model->max_fax_rate &&
             (modem->connected || modem->dialing) &&
             value != modem->service_class)) {
            return false;
        }
        modem->service_class = value;
    } else {
        return false;
    }

    *command = p;
    return true;
}

static bool modem_handle_voice_gain(ModemChardev *modem,
                                    const char **command,
                                    const char *prefix,
                                    int *gain)
{
    const char *p = *command;
    int value;

    if (!g_str_has_prefix(p, prefix)) {
        return false;
    }
    p += strlen(prefix);

    if (g_str_has_prefix(p, "=?")) {
        g_autofree char *line = g_strdup_printf("%s: (0-255)", prefix);

        modem_queue_line(modem, line);
        p += 2;
    } else if (*p == '?') {
        modem_queue_value(modem, prefix, *gain);
        p++;
    } else if (*p == '=') {
        p++;
        value = modem_parse_number(&p, -1);
        if (value < 0 || value > 255) {
            return false;
        }
        *gain = value;
    } else {
        return false;
    }

    *command = p;
    return true;
}

static bool modem_handle_voice_line(ModemChardev *modem,
                                    const char **command)
{
    const char *p = *command;
    int value;

    if (!g_str_has_prefix(p, "+VLS")) {
        return false;
    }
    p += strlen("+VLS");

    if (g_str_has_prefix(p, "=?")) {
        modem_queue_line(modem, "+VLS: (0-7)");
        p += 2;
    } else if (*p == '?') {
        modem_queue_value(modem, "+VLS", modem->voice_line);
        p++;
    } else if (*p == '=') {
        p++;
        value = modem_parse_number(&p, -1);
        if (value < 0 || value > 7) {
            return false;
        }
        modem->voice_line = value;
    } else {
        return false;
    }

    *command = p;
    return true;
}

static bool modem_handle_voice_compression(ModemChardev *modem,
                                           const char **command)
{
    const char *p = *command;
    int compression;
    int sample_rate;

    if (!g_str_has_prefix(p, "+VSM")) {
        return false;
    }
    p += strlen("+VSM");

    if (g_str_has_prefix(p, "=?")) {
        modem_queue_line(modem,
                         "+VSM: 128,\"8-BIT LINEAR\",8,0,(8000),(0),(0)");
        p += 2;
    } else if (*p == '?') {
        g_autofree char *line = g_strdup_printf("+VSM: %d,%d",
                                                modem->voice_compression,
                                                modem->voice_sample_rate);

        modem_queue_line(modem, line);
        p++;
    } else if (*p == '=') {
        p++;
        compression = modem_parse_number(&p, -1);
        if (*p != ',') {
            return false;
        }
        p++;
        sample_rate = modem_parse_number(&p, -1);
        if (compression != 128 || sample_rate != 8000) {
            return false;
        }
        modem->voice_compression = compression;
        modem->voice_sample_rate = sample_rate;
    } else {
        return false;
    }

    *command = p;
    return true;
}

/*
 * DataPort 3740 fax discovery/configuration. Rockwell reference 1048
 * supplies command formats; this is not a T.30 or analogue data pump.
 */
static bool modem_handle_dataport_fax(ModemChardev *modem,
                                      const char **command)
{
    const char *p = *command;
    const char *reply = NULL;
    g_autofree char *formatted = NULL;

    if (!modem->model->max_fax_rate) {
        return false;
    }
    if (modem->service_class == 1) {
        if (g_str_has_prefix(p, "+FTM=?") ||
            g_str_has_prefix(p, "+FRM=?")) {
            reply = "24,48,72,73,74,96,97,98,121,122,145,146";
            p += 6;
        } else if (g_str_has_prefix(p, "+FTH=?") ||
                   g_str_has_prefix(p, "+FRH=?")) {
            reply = "3,24,48,72,73,74,96,97,98,121,122,145,146";
            p += 6;
        }
    } else if (modem->service_class == 2) {
        if (g_str_has_prefix(p, "+FMFR?")) {
            reply = "AT&T Paradyne";
            p += 6;
        } else if (g_str_has_prefix(p, "+FMDL?")) {
            reply = "DataPort Express 3740";
            p += 6;
        } else if (g_str_has_prefix(p, "+FREV?")) {
            reply = modem->model->fallback_identification;
            p += 6;
        } else if (g_str_has_prefix(p, "+FDCC=?")) {
            formatted = g_strdup_printf("(0,1),(0-%d),(0-3),(0-2),"
                                        "(0-2),(0-2),(0),(0-7)",
                                        modem->model->max_fax_rate / 2400 - 1);
            reply = formatted;
            p += 7;
        } else if (g_str_has_prefix(p, "+FDCC?")) {
            const uint8_t *c = modem->fax_dcc;

            formatted = g_strdup_printf("%u,%u,%u,%u,%u,%u,%u,%u",
                                        c[0], c[1], c[2], c[3],
                                        c[4], c[5], c[6], c[7]);
            reply = formatted;
            p += 6;
        } else if (g_str_has_prefix(p, "+FDCC=")) {
            uint8_t next[8];
            const int maximum[] = {
                1, modem->model->max_fax_rate / 2400 - 1,
                3, 2, 2, 2, 0, 7,
            };

            p += 6;
            memcpy(next, modem->fax_dcc, sizeof(next));
            for (size_t i = 0; i < ARRAY_SIZE(next); i++) {
                if (g_ascii_isdigit(*p)) {
                    int value = modem_parse_number(&p, -1);

                    if (value < 0 || value > maximum[i]) {
                        return false;
                    }
                    next[i] = value;
                } else if (*p != ',' && *p != ';' && *p != '\0') {
                    return false;
                }
                if (*p != ',') {
                    break;
                }
                if (i == ARRAY_SIZE(next) - 1) {
                    return false;
                }
                p++;
            }
            if (*p && *p != ';') {
                return false;
            }
            memcpy(modem->fax_dcc, next, sizeof(next));
            *command = p;
            return true;
        }
    }
    if (!reply || (*p && *p != ';')) {
        return false;
    }
    modem_queue_line(modem, reply);
    *command = p;
    return true;
}

static bool modem_handle_extended(ModemChardev *modem, const char **command)
{
    const char *p = *command;

    if (modem_handle_service_class(modem, command, "+FCLASS") ||
        modem_handle_service_class(modem, command, "#CLS")) {
        return true;
    }

    if (modem_handle_dataport_fax(modem, command)) {
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

    if (!modem->model->supports_voice || modem->service_class != 8) {
        return false;
    }

    if (g_str_has_prefix(p, "+VIP")) {
        modem_voice_defaults(modem);
        *command = p + strlen("+VIP");
        return true;
    }
    if (modem_handle_voice_line(modem, command) ||
        modem_handle_voice_compression(modem, command) ||
        modem_handle_voice_gain(modem, command, "+VGR",
                                &modem->voice_rx_gain) ||
        modem_handle_voice_gain(modem, command, "+VGT",
                                &modem->voice_tx_gain)) {
        return true;
    }

    return false;
}

static bool modem_paradyne_speed_valid(const ModemChardev *modem,
                                       int speed, bool legacy)
{
    static const int speeds[] = {
        300, 1200, 2400, 4800, 7200, 9600, 12000, 14400,
        16800, 19200, 21600, 24000, 26400, 28800,
    };
    size_t i;

    if (!modem->model->paradyne_commands ||
        speed > modem->model->connect_speed) {
        return false;
    }
    if (legacy) {
        /* %BL is documented for the 3740, not the other profiles. */
        return modem->model->dataport_3740_line &&
               speed >= 2400 && speed <= 14400 && speed % 2400 == 0;
    }
    for (i = 0; i < ARRAY_SIZE(speeds); i++) {
        if (speed == speeds[i]) {
            return true;
        }
    }
    return false;
}

static void modem_execute_command(ModemChardev *modem, const char *input)
{
    g_autofree char *normalized = modem_normalize_command(input);
    const char *p = normalized;

    if (g_str_has_prefix(p, "AT") || !strcmp(p, "A/")) {
        modem_log_command_line(modem, "GUEST>", input);
    }
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
            if (modem->offline_line || modem->model->dataport_3740_line) {
                /* No inbound line transport is implemented for this model. */
                modem_result(modem, MODEM_RESULT_NO_CARRIER);
            } else {
                modem_connect(modem);
            }
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
            modem_dial(modem);
            return;
        case 'E':
            modem->echo = modem_parse_number(&p, 0) != 0;
            break;
        case 'H':
            modem_parse_number(&p, 0);
            modem_hangup(modem, false);
            break;
        case 'I':
            value = modem_parse_number(&p, 0);
            if (!modem_report_identification(modem, value)) {
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case 'O':
            modem_parse_number(&p, 0);
            if (!modem->connected) {
                modem_result(modem, MODEM_RESULT_NO_CARRIER);
                return;
            }
            if (modem->model->dataport_3740_line) {
                modem_result(modem, MODEM_RESULT_CONNECT);
                modem->command_mode = false;
                modem_chr_accept_input(CHARDEV(modem));
            } else {
                modem->command_mode = false;
                modem_result(modem, MODEM_RESULT_CONNECT);
            }
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
                if (value < 0 || value > 255 ||
                    (modem->model->dataport_3740_line &&
                     (reg == 76 || reg == 78) && value > 1)) {
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
            value = modem_parse_number(&p, 0);
            if (modem->model->paradyne_commands &&
                (value < 0 ||
                 (unsigned)value >= ARRAY_SIZE(modem->stored_profiles))) {
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            modem_reset(modem, modem->model->paradyne_commands ? value : 0);
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
            case 'W':
            case 'Y': {
                char operation = p[-1];

                value = modem_parse_number(&p, 0);
                if (!modem->model->paradyne_commands || value < 0 ||
                    (unsigned)value >= ARRAY_SIZE(modem->stored_profiles)) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                if (operation == 'W') {
                    modem_store_profile(modem, value);
                } else {
                    modem->powerup_profile = value;
                }
                break;
            }
            default:
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case '%':
            switch (*p++) {
            case 'B':
            {
                bool legacy = *p == 'L';

                if (legacy) {
                    p++;
                }
                value = modem_parse_number(&p, -1);
                if (!modem_paradyne_speed_valid(modem, value, legacy)) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                modem->connect_speed = value;
                modem->dataport_legacy_rate = legacy;
                break;
            }
            case 'C':
                modem->compression = modem_parse_number(&p, 0) != 0;
                break;
            case 'M':
                value = modem_parse_number(&p, -1);
                if (!modem->model->dataport_3740_line ||
                    value < DATAPORT_V34_AND_VFC ||
                    value > DATAPORT_VFC_ONLY) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                /* Record V.34/V.FC selection; no DSP negotiation yet. */
                modem->v34_modulation = value;
                break;
            case 'V':
                if (modem->model->dataport_3740_line) {
                    trace_dataport_3740_ident(
                        qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL), -1,
                        modem->model->fallback_identification);
                }
                if (modem->model->paradyne_commands) {
                    /* Model-specific placeholder, not a firmware dump. */
                    modem_queue_line(modem,
                                     modem->model->fallback_identification);
                } else {
                    modem_queue_line(modem, "QEMU Hayes modem V1.0");
                }
                break;
            default:
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case '+':
        case '#':
            p--;
            if (!modem_handle_extended(modem, &p)) {
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
        case '\\':
            switch (*p++) {
            case 'A':
                value = modem_parse_number(&p, -1);
                if (!modem->model->paradyne_commands ||
                    value < 0 || value > 3) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                modem->lapm_frame_size = 64 * (value + 1);
                break;
            case 'D':
                value = modem_parse_number(&p, 0);
                if (!modem->model->paradyne_commands || value > 1) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                modem->cts_follows_dtr = value == 1;
                modem_update_carrier(modem);
                break;
            case 'N':
                value = modem_parse_number(&p, -1);
                if (modem->model->paradyne_commands) {
                    if (value < 0 ||
                        value > modem->model->max_reliable_mode) {
                        modem_result(modem, MODEM_RESULT_ERROR);
                        return;
                    }
                    modem->reliable_mode = value;
                }
                break;
            case 'Q':
                if (!modem->model->paradyne_commands) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                value = modem_parse_number(&p, -1);
                if (value < 0 || value > 4) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                modem->flow_control_mode = value;
                modem->dte_rx_paused = false;
                break;
            case 'X':
                value = modem_parse_number(&p, -1);
                if (!modem->model->paradyne_commands ||
                    value < 0 || value > 1) {
                    modem_result(modem, MODEM_RESULT_ERROR);
                    return;
                }
                modem->xon_xoff_passthrough = value == 1;
                break;
            default:
                modem_result(modem, MODEM_RESULT_ERROR);
                return;
            }
            break;
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
                    modem_log_command_line(modem, "GUEST>", "+++");
                    modem->command_mode = true;
                    modem->dte_rx_paused = false;
                    modem_result(modem, MODEM_RESULT_OK);
                }
                continue;
            }

            if (modem->plus_count) {
                static const uint8_t pluses[] = "++";

                if (!modem_tcp_queue(modem, pluses, modem->plus_count)) {
                    goto done;
                }
                modem->plus_count = 0;
            }
            if (modem->model->paradyne_commands &&
                modem->service_class == 0 &&
                modem->flow_control_mode == 1 &&
                (c == MODEM_XON || c == MODEM_XOFF)) {
                /* \X1 additionally forwards the local flow-control byte. */
                if (modem->xon_xoff_passthrough &&
                    !modem_tcp_queue(modem, &c, 1)) {
                    goto done;
                }
                if (modem->connected && !modem->command_mode) {
                    modem->dte_rx_paused = c == MODEM_XOFF;
                    if (!modem->dte_rx_paused) {
                        modem_chr_accept_input(chr);
                    }
                }
                continue;
            }
            if (!modem_tcp_queue(modem, &c, 1)) {
                goto done;
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

done:
    if (i > 0 && modem->model->dataport_3740_line) {
        qatomic_inc(&modem->indicator_tx_events);
    }
    return i;
}

static int modem_chr_ioctl(Chardev *chr, int cmd, void *arg)
{
    ModemChardev *modem = CHARDEV_MODEM(chr);

    switch (cmd) {
    case CHR_IOCTL_SERIAL_SET_PARAMS:
        modem->dte = *(QEMUSerialSetParams *)arg;
        if (modem->model->dataport_3740_line) {
            trace_dataport_3740_dte(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                                   modem->dte.speed, modem->dte.data_bits,
                                   modem->dte.parity, modem->dte.stop_bits);
        }
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
                modem->dte_rx_paused = false;
            } else if (modem->dtr_mode == 2) {
                modem_hangup(modem, true);
            }
        }
        if (modem->model->dataport_3740_line && old != modem->tiocm) {
            trace_dataport_3740_lines(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                                     old, modem->tiocm);
            /* Resume without a timer when the DTE raises RTS. */
            if (!(old & CHR_TIOCM_RTS) && (input & CHR_TIOCM_RTS)) {
                modem_chr_accept_input(chr);
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
    if (backend && backend->u.modem.data) {
        ChardevModem *opts = backend->u.modem.data;

        if (!!opts->host != !!opts->port) {
            error_setg(errp,
                       "modem TCP transport requires both 'host' and 'port'");
            return false;
        }
        modem->tcp_host = g_strdup(opts->host);
        modem->tcp_port = g_strdup(opts->port);
    }
    modem->model = modem_model_find(model_name);
    if (!modem->model) {
        error_setg(errp, "Unsupported modem model '%s'", model_name);
        return false;
    }

    fifo8_create(&modem->outbuf, MODEM_OUTBUF_SIZE);
    if (modem->model->dataport_3740_line) {
        fifo8_create(&modem->net_rxbuf, MODEM_NETBUF_SIZE);
    }
    fifo8_create(&modem->net_txbuf, MODEM_NETBUF_SIZE);
    modem->tiocm = CHR_TIOCM_CTS | CHR_TIOCM_DSR;
    modem->command_mode = true;
    modem_hangup(modem, false);
    modem_model_defaults(modem);
    if (modem->model->paradyne_commands) {
        for (unsigned i = 0; i < ARRAY_SIZE(modem->stored_profiles); i++) {
            modem_store_profile(modem, i);
        }
    }
    return true;
}

Chardev *qemu_modem_new_offline(const char *model, Error **errp)
{
    ChardevModem options = { .model = (char *)model };
    ChardevBackend backend = {
        .type = CHARDEV_BACKEND_KIND_MODEM,
        .u.modem.data = &options,
    };
    Chardev *chr = qemu_chardev_new(NULL, TYPE_CHARDEV_MODEM,
                                    &backend, NULL, errp);

    if (chr) {
        CHARDEV_MODEM(chr)->offline_line = true;
    }
    return chr;
}

static void modem_chr_parse(QemuOpts *opts, ChardevBackend *backend,
                            Error **errp)
{
    ChardevModem *modem;

    backend->type = CHARDEV_BACKEND_KIND_MODEM;
    modem = backend->u.modem.data = g_new0(ChardevModem, 1);
    qemu_chr_parse_common(opts, qapi_ChardevModem_base(modem));
    modem->model = g_strdup(qemu_opt_get(opts, "model"));
    modem->host = g_strdup(qemu_opt_get(opts, "host"));
    modem->port = g_strdup(qemu_opt_get(opts, "port"));
}

static void modem_chr_finalize(Object *obj)
{
    ModemChardev *modem = CHARDEV_MODEM(obj);

    modem_tcp_close(modem);
    fifo8_destroy(&modem->net_txbuf);
    if (modem->model && modem->model->dataport_3740_line) {
        fifo8_destroy(&modem->net_rxbuf);
    }
    fifo8_destroy(&modem->outbuf);
    g_free(modem->tcp_host);
    g_free(modem->tcp_port);
    if (modem->command_log) {
        g_string_free(modem->command_log, true);
    }
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
