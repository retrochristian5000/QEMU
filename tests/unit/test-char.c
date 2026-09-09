#include "qemu/osdep.h"
#include <glib/gstdio.h>

#include "qapi/error.h"
#include "qemu/config-file.h"
#include "qemu/module.h"
#include "qemu/option.h"
#include "qemu/sockets.h"
#include "chardev/char-fe.h"
#include "system/system.h"
#include "qapi/error.h"
#include "qapi/qapi-commands-char.h"
#include "qobject/qdict.h"
#include "qom/qom-qobject.h"
#include "io/channel-socket.h"
#include "qapi/qobject-input-visitor.h"
#include "qapi/qapi-visit-sockets.h"
#include "socket-helpers.h"

static bool quit;

typedef struct FeHandler {
    int read_count;
    bool is_open;
    int openclose_count;
    bool openclose_mismatch;
    int last_event;
    char read_buf[128];
} FeHandler;

static void main_loop(void)
{
    quit = false;
    do {
        main_loop_wait(false);
    } while (!quit);
}

static int fe_can_read(void *opaque)
{
    FeHandler *h = opaque;

    return sizeof(h->read_buf) - h->read_count;
}

static void fe_read(void *opaque, const uint8_t *buf, int size)
{
    FeHandler *h = opaque;

    g_assert_cmpint(size, <=, fe_can_read(opaque));

    memcpy(h->read_buf + h->read_count, buf, size);
    h->read_count += size;
    quit = true;
}

static void fe_event(void *opaque, QEMUChrEvent event)
{
    FeHandler *h = opaque;
    bool new_open_state;

    h->last_event = event;
    switch (event) {
    case CHR_EVENT_BREAK:
        break;
    case CHR_EVENT_OPENED:
    case CHR_EVENT_CLOSED:
        h->openclose_count++;
        new_open_state = (event == CHR_EVENT_OPENED);
        if (h->is_open == new_open_state) {
            h->openclose_mismatch = true;
        }
        h->is_open = new_open_state;
        /* fallthrough */
    default:
        quit = true;
        break;
    }
}

#ifdef _WIN32
static void char_console_test_subprocess(void)
{
    QemuOpts *opts;
    Chardev *chr;

    opts = qemu_opts_create(qemu_find_opts("chardev"), "console-label",
                            1, &error_abort);
    qemu_opt_set(opts, "backend", "console", &error_abort);

    chr = qemu_chr_new_from_opts(opts, NULL, NULL);
    g_assert_nonnull(chr);

    qemu_chr_write_all(chr, (const uint8_t *)"CONSOLE", 7);

    qemu_opts_del(opts);
    object_unparent(OBJECT(chr));
}

static void char_console_test(void)
{
    g_test_trap_subprocess("/char/console/subprocess", 0, 0);
    g_test_trap_assert_passed();
    g_test_trap_assert_stdout("CONSOLE");
}
#endif
static void char_stdio_test_subprocess(void)
{
    Chardev *chr;
    CharFrontend c;
    int ret;

    chr = qemu_chr_new("label", "stdio", NULL);
    g_assert_nonnull(chr);

    qemu_chr_fe_init(&c, chr, &error_abort);
    qemu_chr_fe_set_open(&c, true);
    ret = qemu_chr_fe_write(&c, (void *)"buf", 4);
    g_assert_cmpint(ret, ==, 4);

    qemu_chr_fe_deinit(&c, true);
}

static void char_stdio_test(void)
{
    g_test_trap_subprocess("/char/stdio/subprocess", 0, 0);
    g_test_trap_assert_passed();
    g_test_trap_assert_stdout("buf");
}

static void char_ringbuf_test(void)
{
    QemuOpts *opts;
    Chardev *chr;
    CharFrontend c;
    char *data;
    int ret;

    opts = qemu_opts_create(qemu_find_opts("chardev"), "ringbuf-label",
                            1, &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);

    qemu_opt_set(opts, "size", "5", &error_abort);
    chr = qemu_chr_new_from_opts(opts, NULL, NULL);
    g_assert_null(chr);
    qemu_opts_del(opts);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "ringbuf-label",
                            1, &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);
    qemu_opt_set(opts, "size", "2", &error_abort);
    chr = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    g_assert_nonnull(chr);
    qemu_opts_del(opts);

    qemu_chr_fe_init(&c, chr, &error_abort);
    ret = qemu_chr_fe_write(&c, (void *)"buff", 4);
    g_assert_cmpint(ret, ==, 4);

    data = qmp_ringbuf_read("ringbuf-label", 4, false, 0, &error_abort);
    g_assert_cmpstr(data, ==, "ff");
    g_free(data);

    data = qmp_ringbuf_read("ringbuf-label", 4, false, 0, &error_abort);
    g_assert_cmpstr(data, ==, "");
    g_free(data);

    qemu_chr_fe_deinit(&c, true);

    /* check alias */
    opts = qemu_opts_create(qemu_find_opts("chardev"), "memory-label",
                            1, &error_abort);
    qemu_opt_set(opts, "backend", "memory", &error_abort);
    qemu_opt_set(opts, "size", "2", &error_abort);
    chr = qemu_chr_new_from_opts(opts, NULL, NULL);
    g_assert_nonnull(chr);
    object_unparent(OBJECT(chr));
    qemu_opts_del(opts);
}

static void char_mux_test(void)
{
    QemuOpts *opts;
    Chardev *chr, *base;
    char *data;
    FeHandler h1 = { 0, false, 0, false, }, h2 = { 0, false, 0, false, };
    CharFrontend chr_fe1, chr_fe2;
    Error *error = NULL;

    opts = qemu_opts_create(qemu_find_opts("chardev"), "mux-label",
                            1, &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);
    qemu_opt_set(opts, "size", "128", &error_abort);
    qemu_opt_set(opts, "mux", "on", &error_abort);
    chr = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    g_assert_nonnull(chr);
    qemu_opts_del(opts);

    qmp_chardev_remove("mux-label", &error_abort);
    qmp_chardev_remove("mux-label-base", &error_abort);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "mux-label",
                            1, &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);
    qemu_opt_set(opts, "size", "128", &error_abort);
    qemu_opt_set(opts, "mux", "on", &error_abort);
    chr = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    g_assert_nonnull(chr);
    qemu_opts_del(opts);

    qemu_chr_fe_init(&chr_fe1, chr, &error_abort);
    qemu_chr_fe_set_handlers(&chr_fe1, fe_can_read, fe_read, fe_event,
                             NULL, &h1, NULL, true);
    qemu_chr_fe_init(&chr_fe2, chr, &error_abort);
    qemu_chr_fe_set_handlers(&chr_fe2, fe_can_read, fe_read, fe_event,
                             NULL, &h2, NULL, true);
    qemu_chr_fe_take_focus(&chr_fe2);

    base = qemu_chr_find("mux-label-base");
    g_assert_cmpint(qemu_chr_be_can_write(base), !=, 0);
    qemu_chr_be_write(base, (void *)"hello", 6);
    g_assert_cmpint(h1.read_count, ==, 0);
    g_assert_cmpint(h2.read_count, ==, 6);
    g_assert_cmpstr(h2.read_buf, ==, "hello");
    h2.read_count = 0;

    qemu_chr_fe_deinit(&chr_fe1, false);
    qmp_chardev_remove("mux-label", &error);
    g_assert_cmpstr(error_get_pretty(error), ==, "Chardev 'mux-label' is busy");
    error_free(error);
    qemu_chr_fe_deinit(&chr_fe2, false);
    qmp_chardev_remove("mux-label", &error_abort);
}

static void char_hub_test(void)
{
    QemuOpts *opts;
    Chardev *hub, *chr1, *chr2, *base;
    char *data;
    FeHandler h = { 0, false, 0, false, };
    Error *error = NULL;
    CharFrontend chr_fe;
    int ret, i;

#define RB_SIZE 128
    opts = qemu_opts_create(qemu_find_opts("chardev"), "hub0", 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "hub", &error_abort);
    hub = qemu_chr_new_from_opts(opts, NULL, &error);
    g_assert_cmpstr(error_get_pretty(error), ==,
                    "hub: 'chardevs' list is not defined");
    error_free(error);
    error = NULL;
    qemu_opts_del(opts);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "chr0", 1,
                            &error_abort);
    qemu_opt_set(opts, "mux", "on", &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);
    qemu_opt_set(opts, "size", stringify(RB_SIZE), &error_abort);
    base = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    g_assert_nonnull(base);
    qemu_opts_del(opts);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "hub0", 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "hub", &error_abort);
    qemu_opt_set(opts, "chardevs.0", "chr0", &error_abort);
    hub = qemu_chr_new_from_opts(opts, NULL, &error);
    g_assert_nonnull(error);
    error_free(error);
    error = NULL;
    qemu_opts_del(opts);
    qmp_chardev_remove("chr0", &error_abort);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "hub0", 1,
                            &error_abort);
    for (i = 0; i < 10; i++) {
        char key[32], val[32];
        snprintf(key, sizeof(key), "chardevs.%d", i);
        snprintf(val, sizeof(val), "chr%d", i);
        qemu_opt_set(opts, key, val, &error);
        if (error) {
            error_free(error);
            break;
        }
    }
    error = NULL;
    qemu_opts_del(opts);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "chr1", 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);
    qemu_opt_set(opts, "size", stringify(RB_SIZE), &error_abort);
    chr1 = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    qemu_opts_del(opts);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "chr2", 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "ringbuf", &error_abort);
    qemu_opt_set(opts, "size", stringify(RB_SIZE), &error_abort);
    chr2 = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    qemu_opts_del(opts);

    opts = qemu_opts_create(qemu_find_opts("chardev"), "hub0", 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "hub", &error_abort);
    qemu_opt_set(opts, "chardevs.0", "chr1", &error_abort);
    qemu_opt_set(opts, "chardevs.1", "chr2", &error_abort);
    hub = qemu_chr_new_from_opts(opts, NULL, &error_abort);
    qemu_opts_del(opts);

    qemu_chr_fe_init(&chr_fe, hub, &error_abort);
    qemu_chr_fe_set_handlers(&chr_fe, fe_can_read, fe_read, fe_event,
                             NULL, &h, NULL, true);
    base = qemu_chr_find("chr1");
    qemu_chr_be_write(base, (void *)"hello", 6);
    data = qmp_ringbuf_read("chr1", RB_SIZE, false, 0, &error_abort);
    g_free(data);
    ret = qemu_chr_fe_write(&chr_fe, (void *)"heyhey", 6);
    g_assert_cmpint(ret, ==, 6);

    qemu_chr_fe_deinit(&chr_fe, false);
    qmp_chardev_remove("hub0", &error_abort);
    qmp_chardev_remove("chr1", &error_abort);
    qmp_chardev_remove("chr2", &error_abort);
}

static void websock_server_read(void *opaque, const uint8_t *buf, int size)
{
    g_assert_cmpint(size, ==, 5);
    g_assert(memcmp(buf, "world", size) == 0);
    quit = true;
}

static int websock_server_can_read(void *opaque)
{
    return 10;
}

static bool websock_check_http_headers(char *buf, int size)
{
    int i;
    const char *ans[] = { "HTTP/1.1 101 Switching Protocols\r\n",
                          "Server: QEMU VNC\r\n",
                          "Upgrade: websocket\r\n",
                          "Connection: Upgrade\r\n",
                          "Sec-WebSocket-Accept:",
                          "Sec-WebSocket-Protocol: binary\r\n" };
    for (i = 0; i < 6; i++) {
        if (g_strstr_len(buf, size, ans[i]) == NULL) {
            return false;
        }
    }
    return true;
}

static void websock_client_read(void *opaque, const uint8_t *buf, int size)
{
    const uint8_t ping[] = { 0x89, 0x85, 0x07, 0x77, 0x9e, 0xf9,
                             0x6f, 0x12, 0xf2, 0x95, 0x68 };
    const uint8_t binary[] = { 0x82, 0x85, 0x74, 0x90, 0xb9, 0xdf,
                               0x03, 0xff, 0xcb, 0xb3, 0x10 };
    Chardev *chr_client = opaque;
    if (websock_check_http_headers((char *)buf, size)) {
        qemu_chr_fe_write(chr_client->fe, ping, sizeof(ping));
    } else if (buf[0] == 0x8a && buf[1] == 0x05) {
        qemu_chr_fe_write(chr_client->fe, binary, sizeof(binary));
    } else {
        quit = true;
    }
}

static int websock_client_can_read(void *opaque)
{
    return 4096;
}

static void char_websock_test(void)
{
    Chardev *chr = qemu_chr_new("server",
                                "websocket:127.0.0.1:0,server=on,wait=off", NULL);
    g_assert_nonnull(chr);
    object_unparent(OBJECT(chr));
}

#ifndef _WIN32
static void char_pipe_test(void)
{
    gchar *tmp_path = g_dir_make_tmp("qemu-test-char.XXXXXX", NULL);
    gchar *in = g_strdup_printf("%s/pipe.in", tmp_path);
    gchar *out = g_strdup_printf("%s/pipe.out", tmp_path);
    g_free(in);
    g_free(out);
    g_rmdir(tmp_path);
    g_free(tmp_path);
}
#endif

typedef struct SocketIdleData {
    GMainLoop *loop;
    Chardev *chr;
    bool conn_expected;
    CharFrontend *fe;
    CharFrontend *client_fe;
} SocketIdleData;

static int make_udp_socket(int *port)
{
    struct sockaddr_in addr = { 0, };
    socklen_t alen = sizeof(addr);
    int ret, sock = qemu_socket(PF_INET, SOCK_DGRAM, 0);
    g_assert_cmpint(sock, >=, 0);
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    addr.sin_port = 0;
    ret = bind(sock, (struct sockaddr *)&addr, sizeof(addr));
    g_assert_cmpint(ret, ==, 0);
    ret = getsockname(sock, (struct sockaddr *)&addr, &alen);
    g_assert_cmpint(ret, ==, 0);
    *port = ntohs(addr.sin_port);
    return sock;
}

static void char_udp_test_internal(Chardev *reuse_chr, int sock)
{
    if (sock >= 0 && !reuse_chr) {
        close(sock);
    }
}

static void char_udp_test(void)
{
    int port;
    int sock = make_udp_socket(&port);
    close(sock);
}

typedef struct {
    int event;
    bool got_pong;
    CharFrontend *fe;
} CharSocketTestData;

static void char_socket_event(void *opaque, QEMUChrEvent event)
{
    CharSocketTestData *data = opaque;
    data->event = event;
}

static void char_socket_discard_read(void *opaque, const uint8_t *buf, int size)
{
}

static void char_socket_server_test(gconstpointer opaque)
{
}

static void char_socket_client_test(gconstpointer opaque)
{
}

static void char_socket_server_two_clients_test(gconstpointer opaque)
{
}

static void char_socket_client_dupid_test(gconstpointer opaque)
{
}

#if defined(HAVE_CHARDEV_SERIAL) && !defined(WIN32)
static void char_serial_test(void)
{
    QemuOpts *opts = qemu_opts_create(qemu_find_opts("chardev"), "serial-id", 1,
                                      &error_abort);
    qemu_opts_del(opts);
}
#endif

#if defined(HAVE_CHARDEV_PARALLEL) && !defined(WIN32)
static void char_parallel_test(void)
{
    QemuOpts *opts = qemu_opts_create(qemu_find_opts("chardev"), "parallel-id", 1,
                                      &error_abort);
    qemu_opts_del(opts);
}
#endif

#ifndef _WIN32
static void char_file_fifo_test(void)
{
}
#endif

static void char_file_test_internal(Chardev *ext_chr, const char *filepath)
{
}

static void char_file_test(void)
{
    char_file_test_internal(NULL, NULL);
}

static void char_null_test(void)
{
    Error *err = NULL;
    Chardev *chr;
    CharFrontend c;
    chr = qemu_chr_find("label-null");
    g_assert_null(chr);
    chr = qemu_chr_new("label-null", "null", NULL);
    g_assert_nonnull(chr);
    qemu_chr_fe_init(&c, chr, &error_abort);
    qemu_chr_fe_init(&c, chr, &err);
    error_free_or_abort(&err);
    qemu_chr_fe_deinit(&c, true);
}

static Chardev *char_modem_new(const char *label, const char *model,
                               Error **errp)
{
    QemuOpts *opts;
    Chardev *chr;
    opts = qemu_opts_create(qemu_find_opts("chardev"), label, 1,
                            &error_abort);
    qemu_opt_set(opts, "backend", "modem", &error_abort);
    if (model && !qemu_opt_set(opts, "model", model, errp)) {
        qemu_opts_del(opts);
        return NULL;
    }
    chr = qemu_chr_new_from_opts(opts, NULL, errp);
    qemu_opts_del(opts);
    return chr;
}

static void char_modem_default_model_test(void)
{
    g_autofree char *filename = NULL;
    Chardev *chr = char_modem_new("modem-default", NULL, &error_abort);
    g_assert_nonnull(chr);
    filename = qemu_chr_get_filename(chr);
    g_assert_cmpstr(filename, ==, "modem:hayes-accura-2400");
    object_unparent(OBJECT(chr));
}

static void char_modem_explicit_model_test(void)
{
    g_autofree char *filename = NULL;
    Chardev *chr = char_modem_new("modem-explicit", "hayes-accura-2400",
                                  &error_abort);
    g_assert_nonnull(chr);
    filename = qemu_chr_get_filename(chr);
    g_assert_cmpstr(filename, ==, "modem:hayes-accura-2400");
    object_unparent(OBJECT(chr));
}

static void char_modem_invalid_model_test(void)
{
    Error *err = NULL;
    Chardev *chr;

    chr = char_modem_new("modem-invalid", "unsupported", &err);
    g_assert_null(chr);
    g_assert_nonnull(err);
    g_assert_nonnull(strstr(error_get_pretty(err),
                            "Unsupported modem model 'unsupported'"));
    error_free(err);
}

static void char_invalid_test(void)
{
    Chardev *chr;
    g_setenv("QTEST_SILENT_ERRORS", "1", 1);
    chr = qemu_chr_new("label-invalid", "invalid", NULL);
    g_assert_null(chr);
    g_unsetenv("QTEST_SILENT_ERRORS");
}

static int chardev_change(void *opaque)
{
    return 0;
}

static int chardev_change_denied(void *opaque)
{
    return -1;
}

static void char_hotswap_test(void)
{
}

static SocketAddress tcpaddr = {
    .type = SOCKET_ADDRESS_TYPE_INET,
    .u.inet.host = (char *)"127.0.0.1",
    .u.inet.port = (char *)"0",
};
#ifndef WIN32
static SocketAddress unixaddr = {
    .type = SOCKET_ADDRESS_TYPE_UNIX,
    .u.q_unix.path = (char *)"test-char.sock",
};
#endif

int main(int argc, char **argv)
{
    bool has_ipv4, has_ipv6;
    qemu_init_main_loop(&error_abort);
    socket_init();
    g_test_init(&argc, &argv, NULL);
    if (socket_check_protocol_support(&has_ipv4, &has_ipv6) < 0) {
        goto end;
    }
    module_call_init(MODULE_INIT_QOM);
    qemu_add_opts(&qemu_chardev_opts);
    g_test_add_func("/char/null", char_null_test);
    g_test_add_func("/char/modem/model/default", char_modem_default_model_test);
    g_test_add_func("/char/modem/model/explicit", char_modem_explicit_model_test);
    g_test_add_func("/char/modem/model/invalid", char_modem_invalid_model_test);
    g_test_add_func("/char/invalid", char_invalid_test);
    g_test_add_func("/char/ringbuf", char_ringbuf_test);
    g_test_add_func("/char/mux", char_mux_test);
    g_test_add_func("/char/hub", char_hub_test);
    g_test_add_func("/char/udp", char_udp_test);
    g_test_add_func("/char/hotswap", char_hotswap_test);
    g_test_add_func("/char/websocket", char_websock_test);
end:
    return g_test_run();
}
