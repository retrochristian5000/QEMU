/*
 * QTest testcase for USB xHCI controller
 *
 * Copyright (c) 2014 HUAWEI TECHNOLOGIES CO., LTD.
 *
 * This work is licensed under the terms of the GNU GPL, version 2 or later.
 * See the COPYING file in the top-level directory.
 */

#include "qemu/osdep.h"
#include "libqtest-single.h"
#include "libqos/usb.h"
#include "qobject/qdict.h"

static void wait_device_deleted_event(QTestState *qtest, const char *id)
{
    QDict *resp, *data;
    const char *device;

    /*
     * Other devices might get removed along with the removed device. Skip
     * these. The device of interest will be the last one.
     */
    for (;;) {
        resp = qtest_qmp_eventwait_ref(qtest, "DEVICE_DELETED");
        data = qdict_get_qdict(resp, "data");
        device = data ? qdict_get_try_str(data, "device") : NULL;
        if (device && !strcmp(device, id)) {
            qobject_unref(resp);
            break;
        }
        qobject_unref(resp);
    }
}

/*
 * Regression test for the xHCI-PCI "host" strong-link reference cycle.
 *
 * The xHCI PCI wrapper embeds an xhci-core child whose strong "host" link
 * points back at the PCI device, forming a refcount cycle. If
 * usb_xhci_pci_exit() does not break that cycle, the device's refcount never
 * reaches 0 on unplug, device_finalize() never runs, and therefore the
 * DEVICE_DELETED event (emitted from device_finalize()) is never sent.
 *
 * This test hot-plugs an xHCI controller into an ACPI-hotpluggable bus,
 * requests its removal and waits for DEVICE_DELETED. Without the fix the event
 * is never delivered (device_finalize() is blocked), so the test would
 * hang/time out.
 */
static void test_xhci_unplug_finalize(void)
{
    QTestState *qtest;
    const char *arch = qtest_get_arch();

    if (strcmp(arch, "i386") != 0 && strcmp(arch, "x86_64") != 0) {
        g_test_skip("Test only runs on x86 (ACPI PCI hotplug)");
        return;
    }
    if (!qtest_has_device("nec-usb-xhci")) {
        g_test_skip("Device nec-usb-xhci not available");
        return;
    }

    qtest = qtest_initf("-machine pc");

    qtest_qmp_device_add(qtest, "nec-usb-xhci", "xhci-finalize", "{}");

    /*
     * Request device removal. As the guest is not running, the unplug request
     * won't be processed until the next system reset, which performs the
     * removal and triggers device_finalize() (and thus DEVICE_DELETED).
     */
    qtest_qmp_device_del_send(qtest, "xhci-finalize");
    qtest_system_reset_nowait(qtest);
    wait_device_deleted_event(qtest, "xhci-finalize");

    qtest_quit(qtest);
}

/*
 * Exercise xHCI USB enumeration with historical and modern x86 CPU profiles.
 * CPUID/APIC features do not provide cellular modem support; check both
 * legacy pin interrupts and the MSI/MSI-X-capable controller path.
 * usb-net is a CDC/RNDIS stand-in, not an MBIM/QMI or 5G radio emulator.
 */
typedef struct XHCICpuProfile {
    const char *test_name;
    const char *model;
    const char *features;
    bool legacy_irq;
} XHCICpuProfile;

static const XHCICpuProfile xhci_cpu_profiles[] = {
    { "/xhci/pci/cpu/486/intx", "486", NULL, true },
    { "/xhci/pci/cpu/pentium3/intx", "pentium3", NULL, true },
    { "/xhci/pci/cpu/core2duo/intx", "core2duo", NULL, true },
    { "/xhci/pci/cpu/qemu32/intx", "qemu32", NULL, true },
    { "/xhci/pci/cpu/qemu64/intx", "qemu64", NULL, true },
    { "/xhci/pci/cpu/qemu64/msi", "qemu64", NULL, false },
    { "/xhci/pci/cpu/max/msi", "max", NULL, false },
    { "/xhci/pci/cpu/max/no-x2apic", "max", "x2apic=off", false },
};

static void test_xhci_cpu_profile(const void *opaque)
{
    const XHCICpuProfile *profile = opaque;
    QTestState *qtest;
    const char *irq = profile->legacy_irq ? "off" : "auto";

    if (!qtest_has_cpu_model(profile->model)) {
        g_test_skip("CPU model not available for this QEMU binary");
        return;
    }

    qtest = qtest_initf("-machine pc -nic none -cpu %s%s%s "
                        "-device nec-usb-xhci,id=xhci-profile,"
                        "msi=%s,msix=%s",
                        profile->model,
                        profile->features ? "," : "",
                        profile->features ? profile->features : "",
                        irq, irq);

    /* Smoke-test USB attach/detach with the selected CPU and IRQ mode. */
    usb_test_hotplug(qtest, "xhci-profile", "1", NULL);

    if (qtest_has_device("usb-net")) {
        qtest_qmp_device_add(qtest, "usb-net", "usb-net-profile",
                             "{'bus': 'xhci-profile.0', 'port': '2'}");
        qtest_qmp_device_del(qtest, "usb-net-profile");
    }

    qtest_quit(qtest);
}

static void test_xhci_hotplug(void)
{
    usb_test_hotplug(global_qtest, "xhci", "1", NULL);
}

static void test_usb_uas_hotplug(void)
{
    QTestState *qts = global_qtest;

    qtest_qmp_device_add(qts, "usb-uas", "uas", "{}");
    qtest_qmp_device_add(qts, "scsi-hd", "scsihd", "{'drive': 'drive0'}");

    /* TODO:
        UAS HBA driver in libqos, to check that
        added disk is visible after BUS rescan
    */

    qtest_qmp_device_del(qts, "scsihd");
    qtest_qmp_device_del(qts, "uas");
}

static void test_usb_ccid_hotplug(void)
{
    QTestState *qts = global_qtest;

    qtest_qmp_device_add(qts, "usb-ccid", "ccid", "{}");
    qtest_qmp_device_del(qts, "ccid");
    /* check the device can be added again */
    qtest_qmp_device_add(qts, "usb-ccid", "ccid", "{}");
    qtest_qmp_device_del(qts, "ccid");
}

int main(int argc, char **argv)
{
    int ret;

    g_test_init(&argc, &argv, NULL);

    qtest_add_func("/xhci/pci/hotplug", test_xhci_hotplug);
    qtest_add_func("/xhci/pci/unplug/finalize", test_xhci_unplug_finalize);
    if ((!strcmp(qtest_get_arch(), "i386") ||
         !strcmp(qtest_get_arch(), "x86_64")) &&
        qtest_has_device("nec-usb-xhci")) {
        for (int i = 0; i < G_N_ELEMENTS(xhci_cpu_profiles); i++) {
            qtest_add_data_func(xhci_cpu_profiles[i].test_name,
                                &xhci_cpu_profiles[i], test_xhci_cpu_profile);
        }
    }
    if (qtest_has_device("usb-uas")) {
        qtest_add_func("/xhci/pci/hotplug/usb-uas", test_usb_uas_hotplug);
    }
    if (qtest_has_device("usb-ccid")) {
        qtest_add_func("/xhci/pci/hotplug/usb-ccid", test_usb_ccid_hotplug);
    }

    qtest_start("-device nec-usb-xhci,id=xhci"
                " -drive id=drive0,if=none,file=null-co://,"
                "file.read-zeroes=on,format=raw");
    ret = g_test_run();
    qtest_end();

    return ret;
}
