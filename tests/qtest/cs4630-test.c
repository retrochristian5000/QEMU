/*
 * QTest coverage for the Cirrus Logic Crystal SoundFusion CS4630
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "libqtest-single.h"
#include "libqos/pci.h"
#include "libqos/pci-pc.h"
#include "hw/pci/pci_regs.h"

#define CS4630_VENDOR_ID 0x1013
#define CS4630_DEVICE_ID 0x6003

#define BA0_HISR         0x000
#define BA0_HICR         0x008
#define BA0_ACCTL        0x460
#define BA0_ACSTS        0x464
#define BA0_ACCAD        0x46c
#define BA0_ACISV        0x474
#define BA0_ACSDA        0x47c

#define HICR_IEV         0x00000001
#define HICR_CHGM        0x00000002
#define HISR_INTENA      0x80000000

#define ACCTL_RSTN       0x00000001
#define ACCTL_ESYN       0x00000002
#define ACCTL_VFRM       0x00000004
#define ACCTL_DCV        0x00000008
#define ACCTL_CRW        0x00000010
#define ACSTS_CRDY       0x00000001
#define ACISV_ISV3       0x00000001
#define ACISV_ISV4       0x00000002

#define BA1_SP_PMEM      0x20000
#define BA1_SPCR         0x30000
#define SPCR_RUN         0x00000001
#define SPCR_RSTSP       0x00000040

static void test_cs4630_basic(void)
{
    QPCIBus *bus;
    QPCIDevice *dev;
    QPCIBar ba0, ba1;
    uint64_t ba0_size, ba1_size;

    qtest_start("-machine pc -nodefaults -device cs4630,addr=05.0");
    bus = qpci_new_pc(global_qtest, NULL);
    dev = qpci_device_find(bus, QPCI_DEVFN(5, 0));
    g_assert_nonnull(dev);

    g_assert_cmphex(qpci_config_readw(dev, PCI_VENDOR_ID), ==,
                    CS4630_VENDOR_ID);
    g_assert_cmphex(qpci_config_readw(dev, PCI_DEVICE_ID), ==,
                    CS4630_DEVICE_ID);
    g_assert_cmphex(qpci_config_readb(dev, PCI_REVISION_ID), ==, 0x01);
    g_assert_cmphex(qpci_config_readw(dev, PCI_CLASS_DEVICE), ==,
                    PCI_CLASS_MULTIMEDIA_AUDIO);
    g_assert_cmphex(qpci_config_readw(dev, PCI_SUBSYSTEM_VENDOR_ID), ==,
                    CS4630_VENDOR_ID);
    g_assert_cmphex(qpci_config_readw(dev, PCI_SUBSYSTEM_ID), ==,
                    CS4630_DEVICE_ID);

    qpci_device_enable(dev);
    ba0 = qpci_iomap(dev, 0, &ba0_size);
    ba1 = qpci_iomap(dev, 1, &ba1_size);
    g_assert_cmphex(ba0_size, ==, 0x1000);
    g_assert_cmphex(ba1_size, ==, 0x100000);

    /* HICR CHGM changes the interrupt-enable value reflected in HISR. */
    qpci_io_writel(dev, ba0, BA0_HICR, HICR_CHGM | HICR_IEV);
    g_assert_cmphex(qpci_io_readl(dev, ba0, BA0_HISR) & HISR_INTENA,
                    ==, HISR_INTENA);
    qpci_io_writel(dev, ba0, BA0_HICR, HICR_CHGM);
    g_assert_cmphex(qpci_io_readl(dev, ba0, BA0_HISR) & HISR_INTENA,
                    ==, 0);

    /* Bring up the host-controlled AC-link. */
    qpci_io_writel(dev, ba0, BA0_ACCTL, ACCTL_RSTN | ACCTL_ESYN);
    g_assert_cmphex(qpci_io_readl(dev, ba0, BA0_ACSTS) & ACSTS_CRDY,
                    ==, ACSTS_CRDY);
    qpci_io_writel(dev, ba0, BA0_ACCTL,
                   ACCTL_RSTN | ACCTL_ESYN | ACCTL_VFRM);
    g_assert_cmphex(qpci_io_readl(dev, ba0, BA0_ACISV) &
                    (ACISV_ISV3 | ACISV_ISV4),
                    ==, ACISV_ISV3 | ACISV_ISV4);

    /* The default companion-codec personality reports Crystal's vendor ID. */
    qpci_io_writel(dev, ba0, BA0_ACCAD, 0x7c);
    qpci_io_writel(dev, ba0, BA0_ACCTL,
                   ACCTL_RSTN | ACCTL_ESYN | ACCTL_VFRM |
                   ACCTL_DCV | ACCTL_CRW);
    g_assert_cmphex(qpci_io_readl(dev, ba0, BA0_ACSDA), ==, 0x4352);

    /* DSP program/data memory is retained even though execution is TODO. */
    qpci_io_writel(dev, ba1, BA1_SP_PMEM, 0x12345678);
    g_assert_cmphex(qpci_io_readl(dev, ba1, BA1_SP_PMEM), ==, 0x12345678);

    /* Resetting the SP prevents RUN from remaining asserted. */
    qpci_io_writel(dev, ba1, BA1_SPCR, SPCR_RUN | SPCR_RSTSP);
    g_assert_cmphex(qpci_io_readl(dev, ba1, BA1_SPCR), ==, SPCR_RSTSP);

    qpci_iounmap(dev, ba1);
    qpci_iounmap(dev, ba0);
    g_free(dev);
    qpci_free_pc(bus);
    qtest_end();
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/cs4630/basic", test_cs4630_basic);
    return g_test_run();
}
