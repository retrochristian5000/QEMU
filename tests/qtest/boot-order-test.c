/*
 * Boot order test cases.
 *
 * Copyright (c) 2013 Red Hat Inc.
 *
 * Authors:
 *  Markus Armbruster <armbru@redhat.com>,
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "libqos/fw_cfg.h"
#include "libqtest.h"
#include "qobject/qdict.h"
#include "standard-headers/linux/qemu_fw_cfg.h"

typedef struct {
    const char *args;
    uint64_t expected_boot;
    uint64_t expected_reboot;
} boot_order_test;

typedef struct {
    const char *agp;
    const char *pci;
} pmac_display_pair;

static void test_a_boot_order(const char *machine,
                              const char *test_args,
                              uint64_t (*read_boot_order)(QTestState *),
                              uint64_t expected_boot,
                              uint64_t expected_reboot)
{
    uint64_t actual;
    QTestState *qts;

    if (!qtest_has_machine(machine)) {
        g_test_skip("Machine is not available");
        return;
    }

    qts = qtest_initf("-nodefaults%s%s %s", machine ? " -M " : "",
                      machine ?: "", test_args);
    actual = read_boot_order(qts);
    g_assert_cmphex(actual, ==, expected_boot);
    qtest_system_reset(qts);
    actual = read_boot_order(qts);
    g_assert_cmphex(actual, ==, expected_reboot);
    qtest_quit(qts);
}

static void test_boot_orders(const char *machine,
                             uint64_t (*read_boot_order)(QTestState *),
                             const boot_order_test *tests)
{
    int i;

    for (i = 0; tests[i].args; i++) {
        test_a_boot_order(machine, tests[i].args,
                          read_boot_order,
                          tests[i].expected_boot,
                          tests[i].expected_reboot);
    }
}

static uint8_t read_mc146818(QTestState *qts, uint16_t port, uint8_t reg)
{
    qtest_outb(qts, port, reg);
    return qtest_inb(qts, port + 1);
}

static uint64_t read_boot_order_pc(QTestState *qts)
{
    uint8_t b1 = read_mc146818(qts, 0x70, 0x38);
    uint8_t b2 = read_mc146818(qts, 0x70, 0x3d);

    return b1 | (b2 << 8);
}

static const boot_order_test test_cases_pc[] = {
    { "",
      0x1230, 0x1230 },
    { "-no-fd-bootchk",
      0x1231, 0x1231 },
    { "-boot c",
      0x0200, 0x0200 },
    { "-boot nda",
      0x3410, 0x3410 },
    { "-boot order=",
      0, 0 },
    { "-boot order= -boot order=c",
      0x0200, 0x0200 },
    { "-boot once=a",
      0x0100, 0x1230 },
    { "-boot once=a -no-fd-bootchk",
      0x0101, 0x1231 },
    { "-boot once=a,order=c",
      0x0100, 0x0200 },
    { "-boot once=d -boot order=nda",
      0x0300, 0x3410 },
    { "-boot once=a -boot once=b -boot once=c",
      0x0200, 0x1230 },
    {}
};

static void test_pc_boot_order(void)
{
    test_boot_orders("pc", read_boot_order_pc, test_cases_pc);
}

static uint64_t read_boot_order_pmac(QTestState *qts)
{
    g_autoptr(QFWCFG) fw_cfg = mm_fw_cfg_init(qts, 0xf0000510);

    return qfw_cfg_get_u16(fw_cfg, FW_CFG_BOOT_DEVICE);
}

static const boot_order_test test_cases_fw_cfg[] = {
    { "", 'c', 'c' },
    { "-boot c", 'c', 'c' },
    { "-boot d", 'd', 'd' },
    { "-boot once=d,order=c", 'd', 'c' },
    {}
};

static const pmac_display_pair powermac3_1_display_pairs[] = {
    { "ati-vga", "cirrus-vga" },
    { "cirrus-vga", "VGA" },
};

static void test_pmac_oldworld_boot_order(void)
{
    test_boot_orders("g3beige", read_boot_order_pmac, test_cases_fw_cfg);
}

static void test_pmac_newworld_boot_order(void)
{
    test_boot_orders("mac99", read_boot_order_pmac, test_cases_fw_cfg);
}

static void test_pmac_powermac3_1_memory_map(void)
{
    static const char agp_io[] =
        "    00000000f0000000-00000000f07fffff (prio 0, i/o): "
        "unin-agp-isa-mmio";
    static const char fw_cfg_ctl[] =
        "      00000000f0000510-00000000f0000511 (prio 0, i/o): "
        "fwcfg.ctl";
    static const char fw_cfg_data[] =
        "      00000000f0000512-00000000f0000512 (prio 0, i/o): "
        "fwcfg.data";
    QTestState *qts;
    g_autofree char *mtree = NULL;
    const char *line;

    if (!qtest_has_machine("powermac3_1")) {
        g_test_skip("Machine is not available");
        return;
    }

    /* Two GiB ends immediately below Sawtooth's 0x80000000 PCI window. */
    qts = qtest_init("-nodefaults -M powermac3_1 -m 2G -boot d");
    g_assert_cmphex(read_boot_order_pmac(qts), ==, 'd');

    mtree = qtest_hmp(qts, "info mtree");
    line = strstr(mtree, agp_io);
    g_assert_nonnull(line);
    line = strchr(line, '\n');
    g_assert_nonnull(line);
    g_assert_true(g_str_has_prefix(++line, fw_cfg_ctl));
    line = strchr(line, '\n');
    g_assert_nonnull(line);
    g_assert_true(g_str_has_prefix(++line, fw_cfg_data));
    qtest_quit(qts);
}

static void test_pmac_powermac3_1_display_pair(gconstpointer data)
{
    const pmac_display_pair *pair = data;
    QTestState *qts;

    if (!qtest_has_machine("powermac3_1")) {
        g_test_skip("Machine is not available");
        return;
    }
    if (!qtest_has_device(pair->agp) || !qtest_has_device(pair->pci)) {
        g_test_skip("Requested display pair is not available");
        return;
    }

    /*
     * Exercise two real card models on Sawtooth's independent display roots.
     * The AGP card occupies the historical device 0x10 slot on pci.0; the
     * unqualified second card uses the normal main PCI root.  Successful
     * realize proves that neither card was flattened into secondary-vga and
     * that their legacy PCI address spaces do not collide across UniNorth.
     */
    qts = qtest_initf("-nodefaults -M powermac3_1 -vga none "
                      "-device %s,bus=pci.0,addr=0x10,id=agp-display "
                      "-device %s,id=pci-display",
                      pair->agp, pair->pci);
    qtest_quit(qts);
}

static uint64_t read_boot_order_sun4m(QTestState *qts)
{
    g_autoptr(QFWCFG) fw_cfg = mm_fw_cfg_init(qts, 0xd00000510ULL);

    return qfw_cfg_get_u16(fw_cfg, FW_CFG_BOOT_DEVICE);
}

static void test_sun4m_boot_order(void)
{
    test_boot_orders("SS-5", read_boot_order_sun4m, test_cases_fw_cfg);
}

static uint64_t read_boot_order_sun4u(QTestState *qts)
{
    g_autoptr(QFWCFG) fw_cfg = io_fw_cfg_init(qts, 0x510);

    return qfw_cfg_get_u16(fw_cfg, FW_CFG_BOOT_DEVICE);
}

static void test_sun4u_boot_order(void)
{
    test_boot_orders("sun4u", read_boot_order_sun4u, test_cases_fw_cfg);
}

int main(int argc, char *argv[])
{
    const char *arch = qtest_get_arch();

    g_test_init(&argc, &argv, NULL);

    if (strcmp(arch, "i386") == 0 || strcmp(arch, "x86_64") == 0) {
        qtest_add_func("boot-order/pc", test_pc_boot_order);
    } else if (strcmp(arch, "ppc") == 0 || strcmp(arch, "ppc64") == 0) {
        qtest_add_func("boot-order/pmac_oldworld",
                       test_pmac_oldworld_boot_order);
        qtest_add_func("boot-order/pmac_newworld",
                       test_pmac_newworld_boot_order);
        qtest_add_func("boot-order/powermac3_1-memory-map",
                       test_pmac_powermac3_1_memory_map);
        qtest_add_data_func("boot-order/powermac3_1-display/ati+cirrus",
                            &powermac3_1_display_pairs[0],
                            test_pmac_powermac3_1_display_pair);
        qtest_add_data_func("boot-order/powermac3_1-display/cirrus+vga",
                            &powermac3_1_display_pairs[1],
                            test_pmac_powermac3_1_display_pair);
    } else if (strcmp(arch, "sparc") == 0) {
        qtest_add_func("boot-order/sun4m", test_sun4m_boot_order);
    } else if (strcmp(arch, "sparc64") == 0) {
        qtest_add_func("boot-order/sun4u", test_sun4u_boot_order);
    }

    return g_test_run();
}
