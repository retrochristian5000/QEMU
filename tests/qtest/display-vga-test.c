/*
 * QTest testcase for vga cards
 *
 * Copyright (c) 2014 Red Hat, Inc
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "hw/pci/pci_ids.h"
#include "libqtest.h"
#include "qobject/qdict.h"
#include "qobject/qlist.h"

typedef struct VGAMultiheadPair {
    const char *primary;
    const char *secondary;
} VGAMultiheadPair;

static void pci_multihead(void)
{
    QTestState *qts;

    qts = qtest_init("-vga none -device VGA -device secondary-vga");
    qtest_quit(qts);
}

static void pci_mixed_multihead(gconstpointer data)
{
    const VGAMultiheadPair *pair = data;
    QTestState *qts;

    qts = qtest_initf("-vga none "
                      "-device %s,id=primary "
                      "-device %s,id=secondary,legacy-vga-decode=off",
                      pair->primary, pair->secondary);
    qtest_quit(qts);
}

static void test_vga(gconstpointer data)
{
    QTestState *qts;

    qts = qtest_initf("-vga none -device %s", (const char *)data);
    qtest_quit(qts);
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
    static const VGAMultiheadPair multihead_pairs[] = {
        { "VGA", "cirrus-vga" },
        { "ati-vga", "cirrus-vga" },
        { "cirrus-vga", "VGA" },
        { "cirrus-vga", "ati-vga" },
    };
    static const unsigned int sierra_vram_mb[] = { 1, 2, 4 };

    g_test_init(&argc, &argv, NULL);

    for (int i = 0; i < ARRAY_SIZE(devices); i++) {
        if (qtest_has_device(devices[i])) {
            char *testpath = g_strdup_printf("/display/pci/%s", devices[i]);
            qtest_add_data_func(testpath, devices[i], test_vga);
            g_free(testpath);
        }
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

    for (int i = 0; i < ARRAY_SIZE(multihead_pairs); i++) {
        const VGAMultiheadPair *pair = &multihead_pairs[i];

        if (qtest_has_device(pair->primary) &&
            qtest_has_device(pair->secondary)) {
            char *testpath = g_strdup_printf("/display/pci/multihead/%s+%s",
                                             pair->primary,
                                             pair->secondary);

            qtest_add_data_func(testpath, pair, pci_mixed_multihead);
            g_free(testpath);
        }
    }

    return g_test_run();
}
