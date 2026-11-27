/*
 * qtest fw_cfg test case
 *
 * Copyright IBM, Corp. 2012-2013
 *
 * Authors:
 *  Anthony Liguori   <aliguori@us.ibm.com>
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"

#include "libqtest.h"
#include "standard-headers/linux/qemu_fw_cfg.h"
#include "libqos/fw_cfg.h"
#include "qemu/bswap.h"
#include "qemu/units.h"

static uint64_t ram_size = 128 << 20;
static uint16_t nb_cpus = 1;
static uint16_t max_cpus = 1;
static uint64_t nb_nodes = 0;
static uint16_t boot_menu = 0;

static void test_fw_cfg_signature(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;
    char buf[5];

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    qfw_cfg_get(fw_cfg, FW_CFG_SIGNATURE, buf, 4);
    buf[4] = 0;

    g_assert_cmpstr(buf, ==, "QEMU");
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

/* Selection failures and reads beyond an item must still return zeros. */
static void test_fw_cfg_read_boundaries(void)
{
    QTestState *s = qtest_init("");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint8_t buf[8];
    static const uint8_t expected[8] = { 'Q', 'E', 'M', 'U', 0, 0, 0, 0 };
    static const uint8_t zeros[8] = { 0 };

    qfw_cfg_get(fw_cfg, FW_CFG_SIGNATURE, buf, sizeof(buf));
    g_assert_cmpmem(buf, sizeof(buf), expected, sizeof(expected));

    qfw_cfg_read_data(fw_cfg, buf, sizeof(buf));
    g_assert_cmpmem(buf, sizeof(buf), zeros, sizeof(zeros));

    qfw_cfg_get(fw_cfg, UINT16_MAX, buf, sizeof(buf));
    g_assert_cmpmem(buf, sizeof(buf), zeros, sizeof(zeros));

    /* A valid selection resets the read cursor after an invalid key. */
    qfw_cfg_get(fw_cfg, FW_CFG_SIGNATURE, buf, sizeof(buf));
    g_assert_cmpmem(buf, sizeof(buf), expected, sizeof(expected));

    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_id(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;
    uint32_t id;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    id = qfw_cfg_get_u32(fw_cfg, FW_CFG_ID);
    g_assert((id == 1) ||
             (id == 3));
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_uuid(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;

    uint8_t buf[16];
    static const uint8_t uuid[16] = {
        0x46, 0x00, 0xcb, 0x32, 0x38, 0xec, 0x4b, 0x2f,
        0x8a, 0xcb, 0x81, 0xc6, 0xea, 0x54, 0xf2, 0xd8,
    };

    s = qtest_init("-uuid 4600cb32-38ec-4b2f-8acb-81c6ea54f2d8");
    fw_cfg = pc_fw_cfg_init(s);

    qfw_cfg_get(fw_cfg, FW_CFG_UUID, buf, 16);
    g_assert(memcmp(buf, uuid, sizeof(buf)) == 0);

    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);

}

static void test_fw_cfg_ram_size(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    g_assert_cmpint(qfw_cfg_get_u64(fw_cfg, FW_CFG_RAM_SIZE), ==, ram_size);

    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_nographic(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    g_assert_cmpint(qfw_cfg_get_u16(fw_cfg, FW_CFG_NOGRAPHIC), ==, 0);

    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_nb_cpus(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    g_assert_cmpint(qfw_cfg_get_u16(fw_cfg, FW_CFG_NB_CPUS), ==, nb_cpus);

    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_max_cpus(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    g_assert_cmpint(qfw_cfg_get_u16(fw_cfg, FW_CFG_MAX_CPUS), ==, max_cpus);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_numa(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;
    uint64_t *cpu_mask;
    uint64_t *node_mask;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    g_assert_cmpint(qfw_cfg_get_u64(fw_cfg, FW_CFG_NUMA), ==, nb_nodes);

    cpu_mask = g_new0(uint64_t, max_cpus);
    node_mask = g_new0(uint64_t, nb_nodes);

    qfw_cfg_read_data(fw_cfg, cpu_mask, sizeof(uint64_t) * max_cpus);
    qfw_cfg_read_data(fw_cfg, node_mask, sizeof(uint64_t) * nb_nodes);

    if (nb_nodes) {
        g_assert(cpu_mask[0] & 0x01);
        g_assert_cmpint(node_mask[0], ==, ram_size);
    }

    g_free(node_mask);
    g_free(cpu_mask);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_boot_menu(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;

    s = qtest_init("");
    fw_cfg = pc_fw_cfg_init(s);

    g_assert_cmpint(qfw_cfg_get_u16(fw_cfg, FW_CFG_BOOT_MENU), ==, boot_menu);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_reboot_timeout(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;
    uint32_t reboot_timeout = 0;
    size_t filesize;

    s = qtest_init("-boot reboot-timeout=15");
    fw_cfg = pc_fw_cfg_init(s);

    filesize = qfw_cfg_get_file(fw_cfg, "etc/boot-fail-wait",
                                &reboot_timeout, sizeof(reboot_timeout));
    g_assert_cmpint(filesize, ==, sizeof(reboot_timeout));
    reboot_timeout = le32_to_cpu(reboot_timeout);
    g_assert_cmpint(reboot_timeout, ==, 15);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_no_reboot_timeout(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;
    uint32_t reboot_timeout = 0;
    size_t filesize;

    /* Special value -1 means "don't reboot" */
    s = qtest_init("-boot reboot-timeout=-1");
    fw_cfg = pc_fw_cfg_init(s);

    filesize = qfw_cfg_get_file(fw_cfg, "etc/boot-fail-wait",
                                &reboot_timeout, sizeof(reboot_timeout));
    g_assert_cmpint(filesize, ==, sizeof(reboot_timeout));
    reboot_timeout = le32_to_cpu(reboot_timeout);
    g_assert_cmpint(reboot_timeout, ==, UINT32_MAX);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_host_battery_default_off(void)
{
    QTestState *s = qtest_init("-machine pc,host-battery=off");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint8_t wire[8] = {0};

    /* Generic PC guests must not receive host battery information. */
    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg,
                                     "opt/org.seabios/whp-laptop-apm",
                                     wire, sizeof(wire)), ==, 0);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_fw_cfg_splash_time(void)
{
    QFWCFG *fw_cfg;
    QTestState *s;
    uint16_t splash_time = 0;
    size_t filesize;

    s = qtest_init("-boot splash-time=12");
    fw_cfg = pc_fw_cfg_init(s);

    filesize = qfw_cfg_get_file(fw_cfg, "etc/boot-menu-wait",
                                &splash_time, sizeof(splash_time));
    g_assert_cmpint(filesize, ==, sizeof(splash_time));
    splash_time = le16_to_cpu(splash_time);
    g_assert_cmpint(splash_time, ==, 12);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

/*
 * fw_cfg contains the unrelocated ACPI tables. SeaBIOS will fix addresses
 * and checksums later; test the actual serialized revision and flags here.
 */
static void test_acpi1_fadt(gconstpointer opaque)
{
    bool strict = GPOINTER_TO_INT(opaque);
    QTestState *s = qtest_init(strict ?
        "-M pc -smp 1 -global PIIX4_PM.strict-acpi1-fadt=on" :
        "-M pc -smp 1 -global PIIX4_PM.strict-acpi1-fadt=off");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint8_t rsdp[20];
    uint8_t first;
    size_t len;
    size_t off;
    uint32_t dsdt_len;
    g_autofree uint8_t *tables = NULL;

    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/acpi/rsdp",
                                      rsdp, sizeof(rsdp)), ==, sizeof(rsdp));
    g_assert_cmpmem(rsdp, 8, "RSD PTR ", 8);
    g_assert_cmpuint(rsdp[15], ==, 0);

    len = qfw_cfg_get_file(fw_cfg, "etc/acpi/tables", &first, 1);
    g_assert_cmpuint(len, >=, 64 + 36 + 116);
    g_assert_cmpuint(len, <=, 16 * MiB);
    tables = g_malloc(len);
    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/acpi/tables",
                                      tables, len), ==, len);

    /* The PC builder emits FACS, DSDT, then FADT in this order. */
    g_assert_cmpmem(tables, 4, "FACS", 4);
    g_assert_cmpuint(ldl_le_p(tables + 4), ==, 64);
    g_assert_cmpmem(tables + 64, 4, "DSDT", 4);
    g_assert_cmpuint(tables[64 + 8], ==, 1);
    dsdt_len = ldl_le_p(tables + 64 + 4);
    g_assert_cmpuint(dsdt_len, >=, 36);
    g_assert_cmpuint(dsdt_len, <=, len - 64 - 116);
    off = 64 + dsdt_len;
    g_assert_cmpmem(tables + off, 4, "FACP", 4);
    g_assert_cmpuint(ldl_le_p(tables + off + 4), ==, 116);
    g_assert_cmpuint(tables[off + 8], ==, 1);
    g_assert_cmphex(ldl_le_p(tables + off + 112), ==,
                    strict ? 0x000000a5 : 0x000080a5);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_piix_pic_resources(gconstpointer opaque)
{
    bool enabled = GPOINTER_TO_INT(opaque);
    QTestState *s = qtest_init(enabled ? "-M pc,pic=on -nodefaults" :
                                        "-M pc,pic=off -nodefaults");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    static const uint8_t hid[] = {
        0x08, '_', 'H', 'I', 'D', 0x0c, 0x41, 0xd0, 0x00, 0x00,
    };
    static const uint8_t resources[] = {
        0x47, 1, 0x20, 0, 0x20, 0, 1, 2,
        0x47, 1, 0xa0, 0, 0xa0, 0, 1, 2,
        0x47, 1, 0xd0, 4, 0xd0, 4, 1, 2,
        0x22, 0x04, 0x00,
    };
    uint8_t first;
    size_t len = qfw_cfg_get_file(fw_cfg, "etc/acpi/tables", &first, 1);
    g_autofree uint8_t *tables = NULL;
    unsigned ids = 0, descriptors = 0;
    size_t end;

    g_assert_cmpuint(len, >=, 64 + 36);
    g_assert_cmpuint(len, <=, 16 * MiB);
    tables = g_malloc(len);
    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/acpi/tables",
                                      tables, len), ==, len);
    g_assert_cmpmem(tables + 64, 4, "DSDT", 4);
    end = 64 + (size_t)ldl_le_p(tables + 68);
    g_assert_cmpuint(end, >=, 64 + 36);
    g_assert_cmpuint(end, <=, len);
    for (size_t i = 64 + 36; i < end; i++) {
        if (end - i >= sizeof(hid) &&
            !memcmp(tables + i, hid, sizeof(hid))) {
            ids++;
        }
        if (end - i >= sizeof(resources) &&
            !memcmp(tables + i, resources, sizeof(resources))) {
            descriptors++;
        }
    }
    g_assert_cmpuint(ids, ==, enabled ? 1 : 0);
    g_assert_cmpuint(descriptors, ==, enabled ? 1 : 0);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

/* The generalized mask must reflect realized devices, not default slots. */
static void test_isa_irq_mask(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                              "-device ne2k_isa,iobase=0x300,irq=10 "
                              "-chardev null,id=uart "
                              "-device isa-serial,index=0,irq=11,chardev=uart "
                              "-parallel null");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint16_t mask = 0;

    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/isa-reserved-irq-mask",
                                     &mask, sizeof(mask)), ==, sizeof(mask));
    g_assert_cmphex(le16_to_cpu(mask), ==,
                    (1U << 7) | (1U << 10) | (1U << 11));
    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/isa-ne2000-irq-mask",
                                     &mask, sizeof(mask)), ==, sizeof(mask));
    g_assert_cmphex(le16_to_cpu(mask), ==, 1U << 10);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_isa_irq_mask_empty(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint16_t mask = UINT16_MAX;

    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/isa-reserved-irq-mask",
                                     &mask, sizeof(mask)), ==, sizeof(mask));
    g_assert_cmphex(le16_to_cpu(mask), ==, 0);
    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/isa-ne2000-irq-mask",
                                     &mask, sizeof(mask)), ==, 0);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_isa_pnp_core(gconstpointer data)
{
    const char *machine = data;
    QTestState *s = qtest_initf("-M %s -nodefaults", machine);
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint8_t mask = 0xff;
    uint8_t expected = 0x0f;

    if (strstr(machine, "pic=off")) {
        expected &= ~1;
    }
    if (strstr(machine, "pit=off")) {
        expected &= ~4;
    }
    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/isa-pnp-core-v1",
                                     &mask, sizeof(mask)), ==, sizeof(mask));
    g_assert_cmphex(mask, ==, expected);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

static void test_acpi_root_uid_collision(void)
{
    if (g_test_subprocess()) {
        QTestState *s = qtest_init("-M pc-i440fx-5.1,acpi=on -nodefaults "
                                  "-device pxb,id=expander,bus_nr=1");
        qtest_quit(s);
        return;
    }

    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*ACPI: duplicate PCI root bridge _UID 1*");
}

static void test_acpi_root_uid_distinct(void)
{
    QTestState *s = qtest_init("-M pc-i440fx-5.1,acpi=on -nodefaults "
                              "-device pxb,id=expander,bus_nr=2");
    QFWCFG *fw_cfg = pc_fw_cfg_init(s);
    uint8_t first;

    g_assert_cmpuint(qfw_cfg_get_file(fw_cfg, "etc/acpi/tables",
                                     &first, sizeof(first)), >, 0);
    pc_fw_cfg_uninit(fw_cfg);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    qtest_add_func("fw_cfg/signature", test_fw_cfg_signature);
    if (qtest_has_machine("pc-i440fx-5.1") && qtest_has_device("pxb")) {
        qtest_add_func("fw_cfg/acpi-root-uid/collision",
                       test_acpi_root_uid_collision);
        qtest_add_func("fw_cfg/acpi-root-uid/distinct",
                       test_acpi_root_uid_distinct);
    }
    if (qtest_has_machine("pc") && qtest_has_device("PIIX4_PM")) {
        qtest_add_func("fw_cfg/isa-irq-mask/empty", test_isa_irq_mask_empty);
        qtest_add_data_func("fw_cfg/isa-pnp-core/all", "pc,pic=on,pit=on",
                            test_isa_pnp_core);
        qtest_add_data_func("fw_cfg/isa-pnp-core/no-pic", "pc,pic=off,pit=on",
                            test_isa_pnp_core);
        qtest_add_data_func("fw_cfg/isa-pnp-core/no-pit", "pc,pic=on,pit=off",
                            test_isa_pnp_core);
        qtest_add_data_func("fw_cfg/isa-pnp-core/no-pic-pit",
                            "pc,pic=off,pit=off", test_isa_pnp_core);
        if (qtest_has_device("ne2k_isa") &&
            qtest_has_device("isa-serial") &&
            qtest_has_device("isa-parallel")) {
            qtest_add_func("fw_cfg/isa-irq-mask/devices", test_isa_irq_mask);
        }
    }
    if (qtest_has_machine("pc") && qtest_has_device("PIIX4_PM")) {
        qtest_add_data_func("fw_cfg/acpi1-fadt/default", GINT_TO_POINTER(0),
                            test_acpi1_fadt);
        qtest_add_data_func("fw_cfg/acpi1-fadt/strict", GINT_TO_POINTER(1),
                            test_acpi1_fadt);
        qtest_add_data_func("fw_cfg/piix-pic/present", GINT_TO_POINTER(1),
                            test_piix_pic_resources);
        qtest_add_data_func("fw_cfg/piix-pic/absent", GINT_TO_POINTER(0),
                            test_piix_pic_resources);
    }
    qtest_add_func("fw_cfg/read_boundaries", test_fw_cfg_read_boundaries);
    qtest_add_func("fw_cfg/id", test_fw_cfg_id);
    qtest_add_func("fw_cfg/uuid", test_fw_cfg_uuid);
    qtest_add_func("fw_cfg/ram_size", test_fw_cfg_ram_size);
    qtest_add_func("fw_cfg/nographic", test_fw_cfg_nographic);
    qtest_add_func("fw_cfg/nb_cpus", test_fw_cfg_nb_cpus);
    qtest_add_func("fw_cfg/max_cpus", test_fw_cfg_max_cpus);
    qtest_add_func("fw_cfg/numa", test_fw_cfg_numa);
    qtest_add_func("fw_cfg/boot_menu", test_fw_cfg_boot_menu);
    qtest_add_func("fw_cfg/reboot_timeout", test_fw_cfg_reboot_timeout);
    qtest_add_func("fw_cfg/no_reboot_timeout", test_fw_cfg_no_reboot_timeout);
    qtest_add_func("fw_cfg/splash_time", test_fw_cfg_splash_time);
    qtest_add_func("fw_cfg/host_battery_default_off",
                   test_host_battery_default_off);

    return g_test_run();
}
