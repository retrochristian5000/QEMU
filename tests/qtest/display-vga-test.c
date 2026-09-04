/*
 * QTest testcase for vga cards
 *
 * Copyright (c) 2014 Red Hat, Inc
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "hw/display/vga_regs.h"
#include "hw/pci/pci_ids.h"
#include "libqtest.h"
#include "qobject/qdict.h"
#include "qobject/qlist.h"

#define VGA_LEGACY_MEM_BASE 0xa0000

static void pci_multihead(void)
{
    QTestState *qts;

    qts = qtest_init("-vga none -device VGA -device secondary-vga");
    qtest_quit(qts);
}

static void test_vga(gconstpointer data)
{
    QTestState *qts;

    qts = qtest_initf("-vga none -device %s", (const char *)data);
    qtest_quit(qts);
}

static void vga_seq_write(QTestState *qts, uint8_t index, uint8_t value)
{
    qtest_outb(qts, VGA_SEQ_I, index);
    qtest_outb(qts, VGA_SEQ_D, value);
}

static void vga_gfx_write(QTestState *qts, uint8_t index, uint8_t value)
{
    qtest_outb(qts, VGA_GFX_I, index);
    qtest_outb(qts, VGA_GFX_D, value);
}

static void vga_attr_write(QTestState *qts, uint8_t index, uint8_t value)
{
    qtest_inb(qts, VGA_IS1_RC);
    qtest_outb(qts, VGA_ATT_W, index);
    qtest_outb(qts, VGA_ATT_W, value);
}

static uint8_t vga_attr_read(QTestState *qts, uint8_t index)
{
    qtest_inb(qts, VGA_IS1_RC);
    qtest_outb(qts, VGA_ATT_W, index);
    return qtest_inb(qts, VGA_ATT_R);
}

static void vga_prepare_memory_access(QTestState *qts, bool chain4)
{
    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, VGA_SEQ_RESET, 0x03);
    vga_seq_write(qts, VGA_SEQ_PLANE_WRITE, VGA_SR02_ALL_PLANES);
    vga_seq_write(qts, VGA_SEQ_MEMORY_MODE,
                  VGA_SR04_EXT_MEM | VGA_SR04_SEQ_MODE |
                  (chain4 ? VGA_SR04_CHN_4M : 0));
    vga_gfx_write(qts, VGA_GFX_PLANE_READ, 0);
    vga_gfx_write(qts, VGA_GFX_MODE, 0);
    vga_gfx_write(qts, VGA_GFX_MISC, 0);
    vga_gfx_write(qts, VGA_GFX_BIT_MASK, 0xff);
}

static void test_vga_attribute_palette_ipas(void)
{
    QTestState *qts = qtest_init("-vga none -device VGA");

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_attr_write(qts, VGA_ATC_PALETTE3, 0x12);

    qtest_inb(qts, VGA_IS1_RC);
    qtest_outb(qts, VGA_ATT_W,
               VGA_AR_ENABLE_DISPLAY | VGA_ATC_PALETTE3);
    qtest_outb(qts, VGA_ATT_W, 0x2a);

    g_assert_cmphex(vga_attr_read(qts, VGA_ATC_PALETTE3), ==, 0x12);
    qtest_quit(qts);
}

static void test_vga_pel_mask(void)
{
    QTestState *qts = qtest_init("-vga none -device VGA");

    qtest_outb(qts, VGA_PEL_MSK, 0x5a);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0x5a);

    qtest_outb(qts, VGA_PEL_MSK, 0xff);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0xff);
    qtest_quit(qts);
}

static void test_vga_eram_memory_decode(void)
{
    static const bool chain4_modes[] = { false, true };

    for (int i = 0; i < ARRAY_SIZE(chain4_modes); i++) {
        QTestState *qts = qtest_init("-vga none -device VGA");
        uint8_t baseline = chain4_modes[i] ? 0x69 : 0x5a;
        uint8_t blocked = chain4_modes[i] ? 0x96 : 0xa5;

        vga_prepare_memory_access(qts, chain4_modes[i]);
        qtest_writeb(qts, VGA_LEGACY_MEM_BASE, baseline);
        g_assert_cmphex(qtest_readb(qts, VGA_LEGACY_MEM_BASE), ==, baseline);

        qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR);
        qtest_writeb(qts, VGA_LEGACY_MEM_BASE, blocked);
        qtest_outb(qts, VGA_MIS_W,
                   VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);

        g_assert_cmphex(qtest_readb(qts, VGA_LEGACY_MEM_BASE), ==, baseline);
        qtest_quit(qts);
    }
}

static QDict *find_pci_device(QList *buses, const char *qdev_id)
{
    QListEntry *bus_entry;

    QLIST_FOREACH_ENTRY(buses, bus_entry) {
        QDict *bus = qobject_to(QDict, qlist_entry_obj(bus_entry));
        QList *devices = qdict_get_qlist(bus, "devices");
        QListEntry *device_entry;

        QLIST_FOREACH_ENTRY(devices, device_entry) {
            QDict *device = qobject_to(QDict, qlist_entry_obj(device_entry));
            const char *id = qdict_get_try_str(device, "qdev_id");

            if (id && !strcmp(id, qdev_id)) {
                return device;
            }
        }
    }

    return NULL;
}

static void test_sierra_falcon64(gconstpointer data)
{
    unsigned int vram_mb = GPOINTER_TO_UINT(data);
    QTestState *qts;
    QDict *resp;
    QDict *device;
    QDict *id;
    QDict *class_info;
    QList *buses;

    qts = qtest_initf("-vga none "
                      "-device sierra-falcon64,id=falcon,vgamem_mb=%u",
                      vram_mb);

    resp = qtest_qmp(qts, "{'execute': 'query-pci'}");
    g_assert(qdict_haskey(resp, "return"));
    buses = qdict_get_qlist(resp, "return");
    device = find_pci_device(buses, "falcon");
    g_assert_nonnull(device);

    id = qdict_get_qdict(device, "id");
    class_info = qdict_get_qdict(device, "class_info");
    g_assert_cmpint(qdict_get_int(id, "vendor"), ==, PCI_VENDOR_ID_SIERRA);
    g_assert_cmpint(qdict_get_int(id, "device"), ==,
                    PCI_DEVICE_ID_SIERRA_SC15064);
    g_assert_cmpint(qdict_get_int(class_info, "class"), ==,
                    PCI_CLASS_DISPLAY_VGA);

    qobject_unref(resp);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    static const char *devices[] = {
        "cirrus-vga",
        "VGA",
        "secondary-vga",
        "virtio-gpu-pci",
        "virtio-vga"
    };
    static const unsigned int sierra_vram_mb[] = { 1, 2, 4 };
    const char *arch = qtest_get_arch();

    g_test_init(&argc, &argv, NULL);

    for (int i = 0; i < ARRAY_SIZE(devices); i++) {
        if (qtest_has_device(devices[i])) {
            char *testpath = g_strdup_printf("/display/pci/%s", devices[i]);
            qtest_add_data_func(testpath, devices[i], test_vga);
            g_free(testpath);
        }
    }

    if (qtest_has_device("VGA") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_func("/display/vga/attribute-palette-ipas",
                       test_vga_attribute_palette_ipas);
        qtest_add_func("/display/vga/pel-mask", test_vga_pel_mask);
        qtest_add_func("/display/vga/eram-memory-decode",
                       test_vga_eram_memory_decode);
    }

    if (qtest_has_device("sierra-falcon64")) {
        qtest_add_data_func("/display/pci/sierra-falcon64/default",
                            "sierra-falcon64", test_vga);

        for (int i = 0; i < ARRAY_SIZE(sierra_vram_mb); i++) {
            unsigned int vram_mb = sierra_vram_mb[i];
            char *testpath = g_strdup_printf(
                "/display/pci/sierra-falcon64/vram-%u", vram_mb);

            qtest_add_data_func(testpath, GUINT_TO_POINTER(vram_mb),
                                test_sierra_falcon64);
            g_free(testpath);
        }
    }

    if (qtest_has_device("secondary-vga")) {
        qtest_add_func("/display/pci/multihead", pci_multihead);
    }

    return g_test_run();
}
