/*
 * Tests for the original 16-bit x86 system target.
 *
 * Copyright (c) 2026 Vincent Menezes
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qobject/qdict.h"
#include "qobject/qlist.h"
#include "qobject/qnum.h"
#include "libqtest-single.h"

#define ROM_SIZE (64 * KiB)

static char *create_test_bios(void)
{
    static const uint8_t code[] = {
        0xfa,                         /* cli */
        0x31, 0xc0,                   /* xor ax, ax */
        0x8e, 0xd8,                   /* mov ds, ax */
        0x8e, 0xd0,                   /* mov ss, ax */
        0xbc, 0x00, 0x80,             /* mov sp, 0x8000 */
        0xc7, 0x06, 0x00, 0x02, 0x4a, 0x4a,
                                      /* mov word [0x200], 0x4a4a */
        0xb8, 0xff, 0xff,             /* mov ax, 0xffff */
        0x8e, 0xc0,                   /* mov es, ax */
        0x26, 0x81, 0x3e, 0x10, 0x02, 0x4a, 0x4a,
                                      /* cmp word es:[0x210], 0x4a4a */
        0x75, 0x2d,                   /* jne fail */
        0xc7, 0x06, 0x18, 0x00, 0x40, 0x00,
                                      /* #UD offset = 0x0040 */
        0xc7, 0x06, 0x1a, 0x00, 0x00, 0xf0,
                                      /* #UD segment = 0xf000 */
        0xc6, 0x06, 0x02, 0x02, 0x00, /* phase = 0 */
        0x54,                         /* push sp */
        0x58,                         /* pop ax */
        0x3d, 0xfe, 0x7f,             /* cmp ax, 0x7ffe */
        0x75, 0x15,                   /* jne fail */
        0x0e,                         /* push cs */
        0x0f,                         /* pop cs on 8086/8088 */
        0xc6, 0x06, 0x02, 0x02, 0x01, /* phase = 1 */
        0x60,                         /* PUSHA must raise #UD */
        0xeb, 0x0b,                   /* jmp fail */
        0x80, 0x3e, 0x02, 0x02, 0x01, /* #UD: cmp phase, 1 */
        0x75, 0x04,                   /* jne fail */
        0xb0, 'T',                    /* mov al, 'T' */
        0xeb, 0x02,                   /* jmp output */
        0xb0, 'F',                    /* fail: mov al, 'F' */
        0xba, 0xf8, 0x03,             /* output: mov dx, 0x3f8 */
        0xee,                         /* out dx, al */
        0xf4,                         /* halt: hlt */
        0xeb, 0xfd,                   /* jmp halt */
    };
    static const uint8_t reset_vector[] = {
        0xea, 0x00, 0x00, 0x00, 0xf0, /* ljmp 0xf000:0 */
    };
    g_autofree uint8_t *rom = g_malloc(ROM_SIZE);
    GError *error = NULL;
    char *path = NULL;
    int fd;

    memset(rom, 0xff, ROM_SIZE);
    memcpy(rom, code, sizeof(code));
    memcpy(rom + 0xfff0, reset_vector, sizeof(reset_vector));

    fd = g_file_open_tmp("x86-16bit-rom-XXXXXX", &path, &error);
    g_assert_no_error(error);
    g_assert_cmpint(fd, >=, 0);
    g_assert_cmpint(qemu_write_full(fd, rom, ROM_SIZE), ==, ROM_SIZE);
    close(fd);
    return path;
}

static void test_cpu_model_filter(void)
{
    g_assert_true(qtest_has_cpu_model("8086"));
    g_assert_true(qtest_has_cpu_model("8088"));
    g_assert_false(qtest_has_cpu_model("486"));
    g_assert_false(qtest_has_cpu_model("qemu32"));
    g_assert_false(qtest_has_cpu_model("max"));
}

static uint64_t get_external_bus_width(const char *machine)
{
    g_autofree char *bios = create_test_bios();
    g_autofree char *args = g_strdup_printf("-machine %s -bios %s",
                                            machine, bios);
    QTestState *qts = qtest_init(args);
    QDict *response;
    QDict *cpu;
    QList *cpus;
    g_autofree char *path = NULL;
    uint64_t width;

    response = qtest_qmp(qts, "{ 'execute': 'query-cpus-fast' }");
    cpus = qdict_get_qlist(response, "return");
    cpu = qobject_to(QDict, qlist_peek(cpus));
    path = g_strdup(qdict_get_str(cpu, "qom-path"));

    qobject_unref(response);
    response = qtest_qmp(qts,
                         "{ 'execute': 'qom-get',"
                         "  'arguments': { 'path': %s,"
                         "                 'property':"
                         "                 'external-data-bus-width' } }",
                         path);
    width = qnum_get_uint(qobject_to(QNum,
                                     qdict_get(response, "return")));
    qobject_unref(response);
    qtest_quit(qts);
    unlink(bios);
    return width;
}

static void test_machine_bus_widths(void)
{
    g_assert_cmpuint(get_external_bus_width("x86-8086"), ==, 16);
    g_assert_cmpuint(get_external_bus_width("x86-8088"), ==, 8);
}

static char *run_qemu_expect_failure(char **argv)
{
    GError *error = NULL;
    char *stderr_text = NULL;
    int status;

    g_assert_true(g_spawn_sync(NULL, argv, NULL, G_SPAWN_STDOUT_TO_DEV_NULL,
                               NULL, NULL, NULL, &stderr_text, &status,
                               &error));
    g_assert_no_error(error);
    g_assert_false(g_spawn_check_wait_status(status, &error));
    g_clear_error(&error);
    return stderr_text;
}

static void test_machine_contract_failures(void)
{
    const char *qemu = qtest_qemu_binary(NULL);
    g_autofree char *bios = create_test_bios();
    g_autofree char *stderr_text = NULL;
    char *missing_bios_argv[] = {
        (char *)qemu,
        (char *)"-machine", (char *)"x86-8086",
        (char *)"-accel", (char *)"tcg",
        (char *)"-display", (char *)"none",
        NULL,
    };
    char *mismatch_argv[] = {
        (char *)qemu,
        (char *)"-machine", (char *)"x86-8086",
        (char *)"-cpu", (char *)"8088",
        (char *)"-accel", (char *)"tcg",
        (char *)"-bios", bios,
        (char *)"-display", (char *)"none",
        NULL,
    };

    stderr_text = run_qemu_expect_failure(missing_bios_argv);
    g_assert_nonnull(strstr(stderr_text, "requires -bios FILE"));
    g_clear_pointer(&stderr_text, g_free);

    stderr_text = run_qemu_expect_failure(mismatch_argv);
    g_assert_nonnull(strstr(stderr_text, "Invalid CPU model: 8088"));
    g_assert_nonnull(strstr(stderr_text, "The only valid type is: 8086"));
    unlink(bios);
}

#ifndef _WIN32
static void test_literal_rom(const void *opaque)
{
    const char *machine = opaque;
    const char *qemu = qtest_qemu_binary(NULL);
    g_autofree char *bios = create_test_bios();
    GError *error = NULL;
    GPid pid;
    int stdout_fd, stderr_fd;
    int status;
    char output = 0;
    char errors[1024] = {};
    struct pollfd pfd;
    char *argv[] = {
        (char *)qemu,
        (char *)"-machine", (char *)machine,
        (char *)"-accel", (char *)"tcg",
        (char *)"-bios", bios,
        (char *)"-display", (char *)"none",
        (char *)"-monitor", (char *)"none",
        (char *)"-serial", (char *)"stdio",
        (char *)"-no-reboot",
        NULL,
    };

    g_spawn_async_with_pipes(NULL, argv, NULL, G_SPAWN_DO_NOT_REAP_CHILD,
                             NULL, NULL, &pid, NULL, &stdout_fd, &stderr_fd,
                             &error);
    g_assert_no_error(error);

    pfd.fd = stdout_fd;
    pfd.events = POLLIN;
    if (poll(&pfd, 1, 10000) > 0) {
        g_assert_cmpint(read(stdout_fd, &output, 1), ==, 1);
    }

    kill(pid, SIGTERM);
    waitpid(pid, &status, 0);
    read(stderr_fd, errors, sizeof(errors) - 1);
    close(stdout_fd);
    close(stderr_fd);
    g_spawn_close_pid(pid);
    unlink(bios);

    if (output != 'T') {
        g_test_message("QEMU stderr: %s", errors);
    }
    g_assert_cmpint(output, ==, 'T');
}
#endif

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    qtest_add_func("/x86-16bit/cpu/model-filter", test_cpu_model_filter);
    qtest_add_func("/x86-16bit/machine/bus-widths",
                   test_machine_bus_widths);
    qtest_add_func("/x86-16bit/machine/contract-failures",
                   test_machine_contract_failures);
#ifndef _WIN32
    qtest_add_data_func("/x86-16bit/execute/8086", "x86-8086",
                        test_literal_rom);
    qtest_add_data_func("/x86-16bit/execute/8088", "x86-8088",
                        test_literal_rom);
#endif

    return g_test_run();
}
