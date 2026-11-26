/*
 * qtest I440FX test case
 *
 * Copyright IBM, Corp. 2012-2013
 * Copyright Red Hat, Inc. 2013
 *
 * Authors:
 *  Anthony Liguori   <aliguori@us.ibm.com>
 *  Laszlo Ersek      <lersek@redhat.com>
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"

#include "libqtest-single.h"
#include "libqos/pci.h"
#include "libqos/pci-pc.h"
#include "hw/pci/pci_regs.h"
#include "qobject/qdict.h"

#define BROKEN 1

typedef struct TestData
{
    int num_cpus;
} TestData;

typedef struct FirmwareTestFixture {
    /* decides whether we're testing -bios or -pflash */
    bool is_bios;
} FirmwareTestFixture;

static QPCIBus *test_start_get_bus(const TestData *s)
{
    char *cmdline;

    cmdline = g_strdup_printf("-machine pc -smp %d", s->num_cpus);
    qtest_start(cmdline);
    g_free(cmdline);
    return qpci_new_pc(global_qtest, NULL);
}

static void test_i440fx_defaults(gconstpointer opaque)
{
    const TestData *s = opaque;
    QPCIBus *bus;
    QPCIDevice *dev;
    uint32_t value;

    bus = test_start_get_bus(s);
    dev = qpci_device_find(bus, QPCI_DEVFN(0, 0));
    g_assert(dev != NULL);

    /* 3.2.2 */
    g_assert_cmpint(qpci_config_readw(dev, PCI_VENDOR_ID), ==, 0x8086);
    /* 3.2.3 */
    g_assert_cmpint(qpci_config_readw(dev, PCI_DEVICE_ID), ==, 0x1237);
#ifndef BROKEN
    /* 3.2.4 */
    g_assert_cmpint(qpci_config_readw(dev, PCI_COMMAND), ==, 0x0006);
    /* 3.2.5 */
    g_assert_cmpint(qpci_config_readw(dev, PCI_STATUS), ==, 0x0280);
#endif
    /* 3.2.7 */
    g_assert_cmpint(qpci_config_readb(dev, PCI_CLASS_PROG), ==, 0x00);
    g_assert_cmpint(qpci_config_readw(dev, PCI_CLASS_DEVICE), ==, 0x0600);
    /* 3.2.8 */
    g_assert_cmpint(qpci_config_readb(dev, PCI_LATENCY_TIMER), ==, 0x00);
    /* 3.2.9 */
    g_assert_cmpint(qpci_config_readb(dev, PCI_HEADER_TYPE), ==, 0x00);
    /* 3.2.10 */
    g_assert_cmpint(qpci_config_readb(dev, PCI_BIST), ==, 0x00);

    /* 3.2.11 */
    value = qpci_config_readw(dev, 0x50); /* PMCCFG */
    if (s->num_cpus == 1) { /* WPE */
        g_assert(!(value & (1 << 15)));
    } else {
        g_assert((value & (1 << 15)));
    }

    g_assert(!(value & (1 << 6))); /* EPTE */

    /* 3.2.12 */
    g_assert_cmpint(qpci_config_readb(dev, 0x52), ==, 0x00); /* DETURBO */
    /* 3.2.13 */
#ifndef BROKEN
    g_assert_cmpint(qpci_config_readb(dev, 0x53), ==, 0x80); /* DBC */
#endif
    /* 3.2.14 */
    g_assert_cmpint(qpci_config_readb(dev, 0x54), ==, 0x00); /* AXC */
    /* 3.2.15 */
    g_assert_cmpint(qpci_config_readw(dev, 0x55), ==, 0x0000); /* DRT */
#ifndef BROKEN
    /* 3.2.16 */
    g_assert_cmpint(qpci_config_readb(dev, 0x57), ==, 0x01); /* DRAMC */
    /* 3.2.17 */
    g_assert_cmpint(qpci_config_readb(dev, 0x58), ==, 0x10); /* DRAMT */
#endif
    /* 3.2.18 */
    g_assert_cmpint(qpci_config_readb(dev, 0x59), ==, 0x00); /* PAM0 */
    g_assert_cmpint(qpci_config_readb(dev, 0x5A), ==, 0x00); /* PAM1 */
    g_assert_cmpint(qpci_config_readb(dev, 0x5B), ==, 0x00); /* PAM2 */
    g_assert_cmpint(qpci_config_readb(dev, 0x5C), ==, 0x00); /* PAM3 */
    g_assert_cmpint(qpci_config_readb(dev, 0x5D), ==, 0x00); /* PAM4 */
    g_assert_cmpint(qpci_config_readb(dev, 0x5E), ==, 0x00); /* PAM5 */
    g_assert_cmpint(qpci_config_readb(dev, 0x5F), ==, 0x00); /* PAM6 */
#ifndef BROKEN
    /* 3.2.19 */
    g_assert_cmpint(qpci_config_readb(dev, 0x60), ==, 0x01); /* DRB0 */
    g_assert_cmpint(qpci_config_readb(dev, 0x61), ==, 0x01); /* DRB1 */
    g_assert_cmpint(qpci_config_readb(dev, 0x62), ==, 0x01); /* DRB2 */
    g_assert_cmpint(qpci_config_readb(dev, 0x63), ==, 0x01); /* DRB3 */
    g_assert_cmpint(qpci_config_readb(dev, 0x64), ==, 0x01); /* DRB4 */
    g_assert_cmpint(qpci_config_readb(dev, 0x65), ==, 0x01); /* DRB5 */
    g_assert_cmpint(qpci_config_readb(dev, 0x66), ==, 0x01); /* DRB6 */
    g_assert_cmpint(qpci_config_readb(dev, 0x67), ==, 0x01); /* DRB7 */
#endif
    /* 3.2.20 */
    g_assert_cmpint(qpci_config_readb(dev, 0x68), ==, 0x00); /* FDHC */
    /* 3.2.21 */
    g_assert_cmpint(qpci_config_readb(dev, 0x70), ==, 0x00); /* MTT */
#ifndef BROKEN
    /* 3.2.22 */
    g_assert_cmpint(qpci_config_readb(dev, 0x71), ==, 0x10); /* CLT */
#endif
    /* 3.2.23 */
    g_assert_cmpint(qpci_config_readb(dev, 0x72), ==, 0x02); /* SMRAM */
    /* 3.2.24 */
    g_assert_cmpint(qpci_config_readb(dev, 0x90), ==, 0x00); /* ERRCMD */
    /* 3.2.25 */
    g_assert_cmpint(qpci_config_readb(dev, 0x91), ==, 0x00); /* ERRSTS */
    /* 3.2.26 */
    g_assert_cmpint(qpci_config_readb(dev, 0x93), ==, 0x00); /* TRC */

    g_free(dev);
    qpci_free_pc(bus);
    qtest_end();
}

#define PAM_RE 1
#define PAM_WE 2

static void pam_set(QPCIDevice *dev, int index, int flags)
{
    int regno = 0x59 + (index / 2);
    uint8_t reg;

    reg = qpci_config_readb(dev, regno);
    if (index & 1) {
        reg = (reg & 0x0F) | (flags << 4);
    } else {
        reg = (reg & 0xF0) | flags;
    }
    qpci_config_writeb(dev, regno, reg);
}

static gboolean verify_area(uint32_t start, uint32_t end, uint8_t value)
{
    uint32_t size = end - start + 1;
    gboolean ret = TRUE;
    uint8_t *data;
    int i;

    data = g_malloc0(size);
    memread(start, data, size);

    g_test_message("verify_area: data[0] = 0x%x", data[0]);

    for (i = 0; i < size; i++) {
        if (data[i] != value) {
            ret = FALSE;
            break;
        }
    }

    g_free(data);

    return ret;
}

static void write_area(uint32_t start, uint32_t end, uint8_t value)
{
    uint32_t size = end - start + 1;
    uint8_t *data;

    data = g_malloc(size);
    memset(data, value, size);
    memwrite(start, data, size);

    g_free(data);
}

static void test_i440fx_pam(gconstpointer opaque)
{
    const TestData *s = opaque;
    QPCIBus *bus;
    QPCIDevice *dev;
    int i;
    static struct {
        uint32_t start;
        uint32_t end;
    } pam_area[] = {
        { 0, 0 },             /* Reserved */
        { 0xF0000, 0xFFFFF }, /* BIOS Area */
        { 0xC0000, 0xC3FFF }, /* Option ROM */
        { 0xC4000, 0xC7FFF }, /* Option ROM */
        { 0xC8000, 0xCBFFF }, /* Option ROM */
        { 0xCC000, 0xCFFFF }, /* Option ROM */
        { 0xD0000, 0xD3FFF }, /* Option ROM */
        { 0xD4000, 0xD7FFF }, /* Option ROM */
        { 0xD8000, 0xDBFFF }, /* Option ROM */
        { 0xDC000, 0xDFFFF }, /* Option ROM */
        { 0xE0000, 0xE3FFF }, /* BIOS Extension */
        { 0xE4000, 0xE7FFF }, /* BIOS Extension */
        { 0xE8000, 0xEBFFF }, /* BIOS Extension */
        { 0xEC000, 0xEFFFF }, /* BIOS Extension */
    };

    bus = test_start_get_bus(s);
    dev = qpci_device_find(bus, QPCI_DEVFN(0, 0));
    g_assert(dev != NULL);

    for (i = 0; i < ARRAY_SIZE(pam_area); i++) {
        if (pam_area[i].start == pam_area[i].end) {
            continue;
        }

        g_test_message("Checking area 0x%05x..0x%05x",
                       pam_area[i].start, pam_area[i].end);
        /* Switch to RE for the area */
        pam_set(dev, i, PAM_RE);
        /* Verify the RAM is all zeros */
        g_assert(verify_area(pam_area[i].start, pam_area[i].end, 0));

        /* Switch to WE for the area */
        pam_set(dev, i, PAM_RE | PAM_WE);
        /* Write out a non-zero mask to the full area */
        write_area(pam_area[i].start, pam_area[i].end, 0x42);

        /* Rewriting an unchanged PAM value must preserve the active alias. */
        for (int repeat = 0; repeat < 4; repeat++) {
            pam_set(dev, i, PAM_RE | PAM_WE);
        }
        g_assert(verify_area(pam_area[i].start, pam_area[i].end, 0x42));

#ifndef BROKEN
        /* QEMU only supports a limited form of PAM */

        /* Switch to !RE for the area */
        pam_set(dev, i, PAM_WE);
        /* Verify the area is not our mask */
        g_assert(!verify_area(pam_area[i].start, pam_area[i].end, 0x42));
#endif

        /* Verify the area is our new mask */
        g_assert(verify_area(pam_area[i].start, pam_area[i].end, 0x42));

        /* Write out a new mask */
        write_area(pam_area[i].start, pam_area[i].end, 0x82);

#ifndef BROKEN
        /* QEMU only supports a limited form of PAM */

        /* Verify the area is not our mask */
        g_assert(!verify_area(pam_area[i].start, pam_area[i].end, 0x82));

        /* Switch to RE for the area */
        pam_set(dev, i, PAM_RE | PAM_WE);
#endif
        /* Verify the area is our new mask */
        g_assert(verify_area(pam_area[i].start, pam_area[i].end, 0x82));

        /* Reset area */
        pam_set(dev, i, 0);

        /* Verify the area is not our new mask */
        g_assert(!verify_area(pam_area[i].start, pam_area[i].end, 0x82));
    }

    g_free(dev);
    qpci_free_pc(bus);
    qtest_end();
}

#define BLOB_SIZE ((size_t)65536)
#define ISA_BIOS_MAXSZ ((size_t)(128 * 1024))

/*
 * Create a blob file, and return its absolute pathname as a dynamically
 * allocated string.
 * The file is closed before the function returns.
 * In case of error, the function aborts and prints the error message.
 */
static char *create_blob_file(void)
{
    int i, fd;
    char *pathname;
    GError *error = NULL;
    g_autofree uint8_t *buf = g_malloc(BLOB_SIZE);

    fd = g_file_open_tmp("blob_XXXXXX", &pathname, &error);
    g_assert_no_error(error);
    close(fd);

    for (i = 0; i < BLOB_SIZE; i++) {
        buf[i] = i;
    }

    g_file_set_contents(pathname, (char *)buf, BLOB_SIZE, &error);
    g_assert_no_error(error);

    return pathname;
}

static void test_i440fx_firmware(FirmwareTestFixture *fixture,
                                 gconstpointer user_data)
{
    char *fw_pathname, *cmdline;
    uint8_t *buf;
    size_t i, isa_bios_size;

    fw_pathname = create_blob_file();
    g_assert(fw_pathname != NULL);

    /* Better hope the user didn't put metacharacters in TMPDIR and co. */
    cmdline = g_strdup_printf("-S %s%s", fixture->is_bios
                                         ? "-bios "
                                         : "-drive if=pflash,format=raw,file=",
                              fw_pathname);
    g_test_message("qemu cmdline: %s", cmdline);
    qtest_start(cmdline);
    g_free(cmdline);

    /* QEMU has loaded the firmware (because qtest_start() only returns after
     * the QMP handshake completes). We must unlink the firmware blob right
     * here, because any assertion firing below would leak it in the
     * filesystem. This is also the reason why we recreate the blob every time
     * this function is invoked.
     */
    unlink(fw_pathname);
    g_free(fw_pathname);

    /* check below 4G */
    buf = g_malloc0(BLOB_SIZE);
    memread(0x100000000ULL - BLOB_SIZE, buf, BLOB_SIZE);
    for (i = 0; i < BLOB_SIZE; ++i) {
        g_assert_cmphex(buf[i], ==, (uint8_t)i);
    }

    /* check in ISA space too */
    memset(buf, 0, BLOB_SIZE);
    isa_bios_size = ISA_BIOS_MAXSZ < BLOB_SIZE ? ISA_BIOS_MAXSZ : BLOB_SIZE;
    memread(0x100000 - isa_bios_size, buf, isa_bios_size);
    for (i = 0; i < isa_bios_size; ++i) {
        g_assert_cmphex(buf[i], ==,
                        (uint8_t)((BLOB_SIZE - isa_bios_size) + i));
    }

    g_free(buf);
    qtest_end();
}

static void add_firmware_test(const char *testpath,
                              void (*setup_fixture)(FirmwareTestFixture *f,
                                                    gconstpointer test_data))
{
    qtest_add(testpath, FirmwareTestFixture, NULL, setup_fixture,
              test_i440fx_firmware, NULL);
}

static void request_bios(FirmwareTestFixture *fixture,
                         gconstpointer user_data)
{
    fixture->is_bios = true;
}

static void request_pflash(FirmwareTestFixture *fixture,
                           gconstpointer user_data)
{
    fixture->is_bios = false;
}

static void test_i440fx_cmos_fpu(gconstpointer opaque)
{
    bool fpu = GPOINTER_TO_INT(opaque);
    g_autofree char *args = g_strdup_printf(
        "-M pc -nodefaults -cpu pentium,mmx=off,fpu=%s",
        fpu ? "on" : "off");
    QTestState *qts = qtest_init(args);

    /* The equipment byte must reflect the requested CPU's FPU feature. */
    qtest_outb(qts, 0x70, 0x14);
    g_assert_cmphex(qtest_inb(qts, 0x71) & 0x02, ==, fpu ? 0x02 : 0);

    qtest_quit(qts);
}

static void test_i440fx_isa_serial_indices(void)
{
    QTestState *qts = qtest_init(
        "-M pc -nodefaults -serial none "
        "-chardev null,id=com2 -device isa-serial,index=1,chardev=com2 "
        "-chardev null,id=comauto -device isa-serial,chardev=comauto");

    /* A sparse explicit index must not be reused by an automatic one. */
    qtest_outb(qts, 0x2ff, 0x55);
    qtest_outb(qts, 0x3ff, 0xaa);
    g_assert_cmphex(qtest_inb(qts, 0x2ff), ==, 0x55);
    g_assert_cmphex(qtest_inb(qts, 0x3ff), ==, 0xaa);

    qtest_quit(qts);
}

static void test_i440fx_uart_profile(gconstpointer opaque)
{
    const char *type = opaque;
    bool has_fifo = !strcmp(type, "ns16550a") ||
                    !strcmp(type, "isa-serial");
    QTestState *qts = qtest_initf(
        "-M pc -nodefaults -serial none "
        "-chardev null,id=com1 -device %s,index=0,chardev=com1 "
        "-chardev null,id=com2 -device isa-serial,chardev=com2", type);

    /* Both older parts have the scratch register. The automatic port
     * must select COM2 even when COM1 uses a derived UART type. */
    qtest_outb(qts, 0x3ff, 0x55);
    qtest_outb(qts, 0x2ff, 0xaa);
    g_assert_cmphex(qtest_inb(qts, 0x3ff), ==, 0x55);
    g_assert_cmphex(qtest_inb(qts, 0x2ff), ==, 0xaa);

    /* FIFO enable and disable probe, independent of the scratch test. */
    qtest_outb(qts, 0x3fa, 0xc7);
    g_assert_cmphex(qtest_inb(qts, 0x3fa) & 0xc0, ==,
                    has_fifo ? 0xc0 : 0);
    qtest_outb(qts, 0x3fa, 0);
    g_assert_cmphex(qtest_inb(qts, 0x3fa) & 0xc0, ==, 0);

    /* DLAB retains independent divisor access. */
    qtest_outb(qts, 0x3fb, 0x80);
    qtest_outb(qts, 0x3f8, 12);
    qtest_outb(qts, 0x3f9, 0);
    g_assert_cmphex(qtest_inb(qts, 0x3f8), ==, 12);
    g_assert_cmphex(qtest_inb(qts, 0x3f9), ==, 0);
    qtest_outb(qts, 0x3fb, 3);

    /* In character mode, FCR writes must not clear received data on
     * the two UARTs that do not implement FCR. */
    if (!has_fifo) {
        qtest_outb(qts, 0x3fc, 0x10);
        qtest_outb(qts, 0x3f8, 0x5a);
        g_assert_cmphex(qtest_inb(qts, 0x3fd) & 1, ==, 1);
        qtest_outb(qts, 0x3fa, 7);
        g_assert_cmphex(qtest_inb(qts, 0x3fd) & 1, ==, 1);
        g_assert_cmphex(qtest_inb(qts, 0x3f8), ==, 0x5a);
    }

    qtest_outb(qts, 0x3fa, 1);
    qtest_system_reset(qts);
    g_assert_cmphex(qtest_inb(qts, 0x3fa) & 0xc0, ==, 0);
    qtest_quit(qts);
}

/* Read each response as the guest consumes it, allowing the character
 * backend to deliver the next byte. No real network or phone line.
 */
static void modem_command(QTestState *qts, const char *command,
                          const char *expected)
{
    GString *response = g_string_new(NULL);

    for (const char *p = command; *p; p++) {
        qtest_outb(qts, 0x2f8, *p);
        while (qtest_inb(qts, 0x2fd) & 1) {
            g_assert_cmpuint(response->len, <, 256);
            g_string_append_c(response, qtest_inb(qts, 0x2f8));
        }
    }
    g_assert_nonnull(strstr(response->str, expected));
    g_string_free(response, true);
}

static void test_i440fx_isa_modem(gconstpointer opaque)
{
    const char *model = opaque;
    QTestState *qts = qtest_initf(
        "-M pc -nodefaults -serial none -device %s,index=1,id=modem "
        "-chardev null,id=other -device ns16550a,chardev=other", model);

    /* Modem occupies COM2; a separately attached UART gets COM1. */
    qtest_outb(qts, 0x2ff, 0x55);
    qtest_outb(qts, 0x3ff, 0xaa);
    g_assert_cmphex(qtest_inb(qts, 0x2ff), ==, 0x55);
    g_assert_cmphex(qtest_inb(qts, 0x3ff), ==, 0xaa);

    qtest_outb(qts, 0x2fb, 3);
    qtest_outb(qts, 0x2fc, 0x0b);
    modem_command(qts, "AT\r", "\r\nOK\r\n");
    modem_command(qts, "ATE0\r", "\r\nOK\r\n");
    modem_command(qts, "ATI3\r",
                  !strcmp(model, "hayes-accura-2400") ? "Hayes Accura 2400" :
                  !strcmp(model, "rockwell-voice-14400") ? "Rockwell-compatible" :
                  !strcmp(model, "att-paradyne-dataport-3711") ? "3711" :
                  "3740");
    modem_command(qts, "ATD0\r", "NO DIALTONE");
    modem_command(qts, "ATA\r", "NO CARRIER");
    qtest_system_reset(qts);
    qtest_outb(qts, 0x2fb, 3);
    modem_command(qts, "AT\r", "AT\r\r\nOK");
    qtest_quit(qts);
}

static void test_i440fx_dataport_3740_line(gconstpointer opaque)
{
    bool integrated = GPOINTER_TO_INT(opaque);
    QTestState *qts = qtest_init(integrated ?
        "-M pc -nodefaults -serial none "
        "-device att-paradyne-3740,index=1" :
        "-M pc -nodefaults -serial none "
        "-chardev modem,id=m,model=att-paradyne-3740 "
        "-device ns16550a,index=1,chardev=m");

    qtest_outb(qts, 0x2fb, 3);
    /* Factory CTS follows DTR; DSR remains high, DCD and RI low. */
    qtest_outb(qts, 0x2fc, 8);
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x20);
    qtest_outb(qts, 0x2fc, 9);
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x30);

    modem_command(qts, "ATE0\r", "OK");
    modem_command(qts, "AT\\N7\\Q3%C1S7=60\r", "OK");
    modem_command(qts, "AT\\N8\r", "ERROR");
    modem_command(qts, "AT\\D0\r", "OK");
    qtest_outb(qts, 0x2fc, 8);
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x30);
    modem_command(qts, "AT\\D2\r", "ERROR");
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x30);
    modem_command(qts, "AT\\D1\r", "OK");
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x20);

    modem_command(qts, "AT&C0\r", "OK");
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0x80, ==, 0x80);
    modem_command(qts, "AT&C1\r", "OK");
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0x80, ==, 0);
    modem_command(qts, "ATX4D0\r", "NO DIALTONE");
    modem_command(qts, "ATX0D0\r", "NO CARRIER");
    modem_command(qts, "ATX1D0\r", "NO CARRIER");
    modem_command(qts, "ATX2D0\r", "NO DIALTONE");
    modem_command(qts, "ATX3D0\r", "NO CARRIER");
    modem_command(qts, "ATA\r", "NO CARRIER");
    modem_command(qts, "ATO\r", "NO CARRIER");
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xc0, ==, 0);

    if (integrated) {
        qtest_outb(qts, 0x2fc, 9);
        modem_command(qts, "AT\\D0\r", "OK");
        qtest_system_reset(qts);
        g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x20);
    }
    qtest_quit(qts);
}

static void test_i440fx_dataport_3740_scan(gconstpointer opaque)
{
    bool integrated = GPOINTER_TO_INT(opaque);
    QTestState *qts = qtest_init(integrated ?
        "-M pc -nodefaults -serial none "
        "-device att-paradyne-3740,index=1,acpi-legacy-irq=on" :
        "-M pc -nodefaults -serial none "
        "-chardev modem,id=m,model=att-paradyne-3740 "
        "-device ns16550a,index=1,chardev=m,acpi-legacy-irq=on");

    /* Exercise the serial enumeration framing and DTR/RTS transitions. */
    qtest_outb(qts, 0x2fb, 0x82); /* DLAB, 7N1 */
    qtest_outb(qts, 0x2f8, 96);   /* 1200 baud */
    qtest_outb(qts, 0x2f9, 0);
    qtest_outb(qts, 0x2fb, 2);
    qtest_outb(qts, 0x2fc, 8);
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x20);
    qtest_clock_step(qts, 200000000);
    qtest_outb(qts, 0x2fc, 9);
    qtest_clock_step(qts, 200000000);
    qtest_outb(qts, 0x2fc, 0x0b);
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x30);

    /* A legacy AT probe must still work after enumeration framing. */
    qtest_outb(qts, 0x2fb, 0x83);
    qtest_outb(qts, 0x2f8, 12);   /* 9600 baud */
    qtest_outb(qts, 0x2f9, 0);
    qtest_outb(qts, 0x2fb, 3);
    modem_command(qts, "ATE0Q0V1\r", "OK");
    /* No extra clock step should be needed to drain identification replies. */
    for (unsigned i = 0; i <= 10; i++) {
        g_autofree char *command = g_strdup_printf("ATI%u\r", i);
        const char *expected = i == 0 ? "28800" :
                               i == 3 ? "3740 V.34 V.FC" : "ERROR";

        modem_command(qts, command, expected);
    }
    modem_command(qts, "AT%V\r", "QEMU DataPort Express 3740 profile");
    modem_command(qts, "AT+FCLASS=?\r", "0,1,2");
    modem_command(qts, "AT+FCLASS=1\r", "OK");
    modem_command(qts, "AT+FTM=?\r", "145,146");
    modem_command(qts, "AT+FCLASS=2\r", "OK");
    modem_command(qts, "AT+FMDL?\r", "DataPort Express 3740");
    modem_command(qts, "AT+FDCC?\r", "0,5,0,2,0,0,0,0");
    modem_command(qts, "AT+FCLASS=0\r", "OK");

    /* UART reset must drop DTR even on a separately attached backend. */
    qtest_system_reset(qts);
    g_assert_cmphex(qtest_inb(qts, 0x2fc) & 3, ==, 0);
    g_assert_cmphex(qtest_inb(qts, 0x2fe) & 0xf0, ==, 0x20);
    qtest_quit(qts);
}

static void test_i440fx_cmos_mouse(gconstpointer opaque)
{
    bool enabled = GPOINTER_TO_INT(opaque);
    QTestState *qts = qtest_init(enabled ?
        "-M pc,i8042=on,vmport=off -nodefaults" :
        "-M pc,i8042=off,vmport=off -nodefaults");

    qtest_outb(qts, 0x70, 0x14);
    g_assert_cmphex(qtest_inb(qts, 0x71) & 0x04, ==, enabled ? 0x04 : 0);
    qtest_quit(qts);
}

static void test_i440fx_hpet_intcap(void)
{
    QTestState *qts = qtest_init("-M pc,hpet=on -nodefaults "
                                "-global hpet.hpet-intcap=0x10000");

    /* Timer 0 configuration, upper dword: interrupt routing capability. */
    g_assert_cmphex(qtest_readl(qts, 0xfed00104), ==, 0x10000);
    qtest_quit(qts);
}

static void test_i440fx_timing_config(void)
{
    QTestState *qts = qtest_init("-M pc -nodefaults "
                                "-global i440FX.strict-timing-config=on");
    QPCIBus *bus = qpci_new_pc(qts, NULL);
    QPCIDevice *dev = qpci_device_find(bus, QPCI_DEVFN(0, 0));
    QDict *reply = qtest_qmp(qts,
        "{'execute':'qom-get','arguments':"
        "{'path':'/machine/i440fx','property':'type'}}");

    g_assert_cmpstr(qdict_get_str(reply, "return"), ==, "i440FX-pcihost");
    qobject_unref(reply);
    g_assert_nonnull(dev);
    g_assert_cmphex(qpci_config_readl(dev, PCI_VENDOR_ID), ==, 0x12378086);
    g_assert_cmphex(qpci_config_readb(dev, 0x53), ==, 0x80);
    g_assert_cmphex(qpci_config_readb(dev, 0x58), ==, 0x10);
    g_assert_cmphex(qpci_config_readb(dev, 0x71), ==, 0x10);

    qpci_config_writeb(dev, 0x53, 0x55);
    qpci_config_writeb(dev, 0x58, 0xff);
    qpci_config_writeb(dev, 0x71, 0xff);
    g_assert_cmphex(qpci_config_readb(dev, 0x53), ==, 0x55);
    g_assert_cmphex(qpci_config_readb(dev, 0x58), ==, 0x7f);
    g_assert_cmphex(qpci_config_readb(dev, 0x71), ==, 0x1f);

    qtest_system_reset(qts);
    g_assert_cmphex(qpci_config_readb(dev, 0x53), ==, 0x80);
    g_assert_cmphex(qpci_config_readb(dev, 0x58), ==, 0x10);
    g_assert_cmphex(qpci_config_readb(dev, 0x71), ==, 0x10);

    g_free(dev);
    qpci_free_pc(bus);
    qtest_quit(qts);
}

static void test_piix4_pm_io_decode(void)
{
    QTestState *qts = qtest_init("-M pc -nodefaults "
                                "-global PIIX4_PM.strict-io-decode=on");
    QPCIBus *bus = qpci_new_pc(qts, NULL);
    QPCIDevice *dev = qpci_device_find(bus, QPCI_DEVFN(1, 3));

    g_assert_nonnull(dev);
    g_assert_cmphex(qpci_config_readl(dev, PCI_VENDOR_ID), ==, 0x71138086);
    g_assert_cmphex(qpci_config_readl(dev, 0x40), ==, 1);
    g_assert_cmphex(qpci_config_readl(dev, 0x90), ==, 1);

    /* Reserved bits must not survive PCI configuration writes. */
    qpci_config_writel(dev, 0x40, 0xffff503e);
    qpci_config_writel(dev, 0x90, 0xffff601e);
    g_assert_cmphex(qpci_config_readl(dev, 0x40), ==, 0x5001);
    g_assert_cmphex(qpci_config_readl(dev, 0x90), ==, 0x6011);

    qpci_config_writew(dev, PCI_COMMAND, 0);
    qpci_config_writeb(dev, 0x80, 0xff);
    qpci_config_writeb(dev, 0xd2, 0xf9);
    g_assert_cmphex(qpci_config_readb(dev, 0x80), ==, 1);
    g_assert_cmphex(qpci_config_readb(dev, 0xd2), ==, 9);

    /* PM decode is independent of PCI I/O enable; SMBus is not. */
    qtest_outw(qts, 0x5002, 0x0100);
    g_assert_cmphex(qtest_inw(qts, 0x5002), ==, 0x0100);
    g_assert_cmphex(qtest_inb(qts, 0x6013), ==, 0xff);
    qpci_config_writew(dev, PCI_COMMAND, PCI_COMMAND_IO);
    qtest_outb(qts, 0x6013, 0x5a);
    g_assert_cmphex(qtest_inb(qts, 0x6013), ==, 0x5a);
    g_assert_cmphex(qtest_inb(qts, 0x6003), ==, 0xff);

    /* Relocation removes the old mapping and leaves adjacent ports free. */
    qpci_config_writel(dev, 0x90, 0x6030);
    g_assert_cmphex(qtest_inb(qts, 0x6013), ==, 0xff);
    g_assert_cmphex(qtest_inb(qts, 0x6033), ==, 0x5a);
    g_assert_cmphex(qtest_inb(qts, 0x6043), ==, 0xff);
    qpci_config_writeb(dev, 0xd2, 0);
    g_assert_cmphex(qtest_inb(qts, 0x6033), ==, 0xff);

    qtest_system_reset(qts);
    g_assert_cmphex(qpci_config_readl(dev, 0x40), ==, 1);
    g_assert_cmphex(qpci_config_readl(dev, 0x90), ==, 1);
    g_assert_cmphex(qpci_config_readb(dev, 0x80), ==, 0);
    g_assert_cmphex(qpci_config_readb(dev, 0xd2), ==, 0);
    g_free(dev);
    qpci_free_pc(bus);
    qtest_quit(qts);
}

static void test_piix_pirq_registers(gconstpointer opaque)
{
    bool piix4 = GPOINTER_TO_INT(opaque);
    QTestState *qts = qtest_init(piix4 ?
        "-M pc,x-south-bridge=piix4-isa -nodefaults" :
        "-M pc,x-south-bridge=PIIX3 -nodefaults");
    QPCIBus *bus = qpci_new_pc(qts, NULL);
    QPCIDevice *dev = qpci_device_find(bus, QPCI_DEVFN(1, 0));

    g_assert_nonnull(dev);
    g_assert_cmphex(qpci_config_readl(dev, PCI_VENDOR_ID), ==,
                    piix4 ? 0x71108086 : 0x70008086);
    g_assert_cmphex(qpci_config_readw(dev, PCI_CLASS_DEVICE), ==, 0x0601);
    g_assert_cmphex(qpci_config_readl(dev, 0x60), ==, 0x80808080);

    /* Each byte has four selection bits, a disable bit, and three RO bits. */
    qpci_config_writel(dev, 0x60, 0xffffffffU);
    g_assert_cmphex(qpci_config_readl(dev, 0x60), ==, 0x8f8f8f8fU);
    qpci_config_writel(dev, 0x60, 0x7f7b7a79U);
    g_assert_cmphex(qpci_config_readl(dev, 0x60), ==, 0x0f0b0a09U);
    qpci_config_writeb(dev, 0x61, 0xfa);
    g_assert_cmphex(qpci_config_readl(dev, 0x60), ==, 0x0f0b8a09U);

    qtest_system_reset(qts);
    g_assert_cmphex(qpci_config_readl(dev, 0x60), ==, 0x80808080);
    g_free(dev);
    qpci_free_pc(bus);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    TestData data;

    g_test_init(&argc, &argv, NULL);

    data.num_cpus = 1;

    qtest_add_data_func("i440fx/defaults", &data, test_i440fx_defaults);
    qtest_add_data_func("i440fx/pam", &data, test_i440fx_pam);
    qtest_add_func("i440fx/timing-config", test_i440fx_timing_config);
    if (qtest_has_device("isa-serial")) {
        qtest_add_func("i440fx/isa/serial-indices", test_i440fx_isa_serial_indices);
        const char *const types[] = {
            "isa-serial", "ins8250a", "ns16450", "ns16550a",
        };
        for (unsigned n = 0; n < ARRAY_SIZE(types); n++) {
            if (qtest_has_device(types[n])) {
                g_autofree char *path =
                    g_strdup_printf("i440fx/isa/uart/%s", types[n]);
                qtest_add_data_func(path, types[n], test_i440fx_uart_profile);
            }
        }
    }
    const char *const modems[] = {
        "hayes-accura-2400", "rockwell-voice-14400",
        "att-paradyne-dataport-3711", "att-paradyne-3740",
    };
    for (unsigned n = 0; n < ARRAY_SIZE(modems); n++) {
        if (qtest_has_device(modems[n]) && qtest_has_device("ns16550a")) {
            g_autofree char *path =
                g_strdup_printf("i440fx/isa/modem/%s", modems[n]);
            qtest_add_data_func(path, modems[n], test_i440fx_isa_modem);
        }
    }
    if (qtest_has_device("att-paradyne-3740") &&
        qtest_has_device("ns16550a")) {
        qtest_add_data_func("i440fx/isa/modem/3740-legacy-name",
                            "att-paradyne-dataport-3740", test_i440fx_isa_modem);
        qtest_add_data_func("i440fx/isa/modem/3740-line-integrated",
                            GINT_TO_POINTER(1), test_i440fx_dataport_3740_line);
        qtest_add_data_func("i440fx/isa/modem/3740-line-external",
                            GINT_TO_POINTER(0), test_i440fx_dataport_3740_line);
        qtest_add_data_func("i440fx/isa/modem/3740-scan-integrated",
                            GINT_TO_POINTER(1), test_i440fx_dataport_3740_scan);
        qtest_add_data_func("i440fx/isa/modem/3740-scan-external",
                            GINT_TO_POINTER(0), test_i440fx_dataport_3740_scan);
    }
    qtest_add_data_func("i440fx/cmos/mouse-on", GINT_TO_POINTER(1),
                        test_i440fx_cmos_mouse);
    qtest_add_data_func("i440fx/cmos/mouse-off", GINT_TO_POINTER(0),
                        test_i440fx_cmos_mouse);
    if (qtest_has_device("hpet")) {
        qtest_add_func("i440fx/hpet/intcap", test_i440fx_hpet_intcap);
    }
    qtest_add_data_func("i440fx/cmos/fpu-on", GINT_TO_POINTER(1),
                        test_i440fx_cmos_fpu);
    qtest_add_data_func("i440fx/cmos/fpu-off", GINT_TO_POINTER(0),
                        test_i440fx_cmos_fpu);
    qtest_add_data_func("i440fx/piix3/pirq-registers",
                        GINT_TO_POINTER(0), test_piix_pirq_registers);
    if (qtest_has_device("piix4-isa")) {
        qtest_add_data_func("i440fx/piix4/pirq-registers",
                            GINT_TO_POINTER(1), test_piix_pirq_registers);
    }
    if (qtest_has_device("PIIX4_PM")) {
        qtest_add_func("i440fx/piix4-pm-io-decode", test_piix4_pm_io_decode);
    }
    add_firmware_test("i440fx/firmware/bios", request_bios);
    add_firmware_test("i440fx/firmware/pflash", request_pflash);

    return g_test_run();
}
