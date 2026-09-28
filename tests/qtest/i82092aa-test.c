/*
 * QTest for the Intel 82092AA PCI-to-PCMCIA bridge
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "libqtest.h"
#include "libqos/pci.h"
#include "libqos/pci-pc.h"
#include "hw/pci/pci_ids.h"
#include "hw/pci/pci_regs.h"

#define I82092AA_PCICON         0x40
#define I82092AA_SOCKET_MASK    0x06
#define I82092AA_SOCKET_1       0x02
#define I82092AA_SOCKET_2       0x00
#define I82092AA_SOCKET_4       0x04

#define I82092AA_EXCA_IDENT     0x00
#define I82092AA_SOCKET_STRIDE  0x40

static void check_socket_ident(QPCIDevice *dev, QPCIBar bar,
                               unsigned socket, uint8_t expected)
{
    qpci_io_writeb(dev, bar, 0, socket * I82092AA_SOCKET_STRIDE +
                                I82092AA_EXCA_IDENT);
    g_assert_cmphex(qpci_io_readb(dev, bar, 1), ==, expected);
}

static void test_i82092aa_profile(unsigned sockets, uint8_t socket_strap)
{
    QTestState *qts;
    QPCIBus *pcibus;
    QPCIDevice *dev;
    QPCIBar bar;
    uint64_t bar_size;
    unsigned i;

    qts = qtest_initf("-nodefaults -M pc -display none "
                      "-device i82092aa,addr=04.0,sockets=%u", sockets);
    pcibus = qpci_new_pc(qts, NULL);
    dev = qpci_device_find(pcibus, QPCI_DEVFN(0x4, 0x0));
    g_assert_nonnull(dev);

    g_assert_cmphex(qpci_config_readw(dev, PCI_VENDOR_ID), ==,
                    PCI_VENDOR_ID_INTEL);
    g_assert_cmphex(qpci_config_readw(dev, PCI_DEVICE_ID), ==,
                    PCI_DEVICE_ID_INTEL_82092AA_0);
    g_assert_cmphex(qpci_config_readw(dev, PCI_CLASS_DEVICE), ==,
                    PCI_CLASS_BRIDGE_PCMCIA);
    g_assert_cmphex(qpci_config_readb(dev, PCI_REVISION_ID), ==, 0x01);
    g_assert_cmphex(qpci_config_readb(dev, I82092AA_PCICON) &
                    I82092AA_SOCKET_MASK, ==, socket_strap);

    /*
     * The PPEC I/O BAR has a four-byte PCI aperture.  Only BASE+0/1 are
     * implemented as the ExCA index/data pair.
     */
    qpci_device_enable(dev);
    bar = qpci_iomap(dev, 0, &bar_size);
    g_assert_true(bar.is_io);
    g_assert_cmpuint(bar_size, ==, 4);

    for (i = 0; i < sockets; i++) {
        check_socket_ident(dev, bar, i, 0x84);
    }
    if (sockets < 4) {
        check_socket_ident(dev, bar, sockets, 0xff);
    }

    /*
     * Socket-count bits are read-only straps while PCICON bits 5:3 and 0
     * are writable.
     */
    qpci_config_writeb(dev, I82092AA_PCICON, 0xff);
    g_assert_cmphex(qpci_config_readb(dev, I82092AA_PCICON), ==,
                    socket_strap | 0x39);

    qpci_iounmap(dev, bar);
    g_free(dev);
    qpci_free_pc(pcibus);
    qtest_quit(qts);
}

static void test_i82092aa_1socket(void)
{
    test_i82092aa_profile(1, I82092AA_SOCKET_1);
}

static void test_i82092aa_2socket(void)
{
    test_i82092aa_profile(2, I82092AA_SOCKET_2);
}

static void test_i82092aa_4socket(void)
{
    test_i82092aa_profile(4, I82092AA_SOCKET_4);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    qtest_add_func("/i82092aa/1-socket", test_i82092aa_1socket);
    qtest_add_func("/i82092aa/2-socket", test_i82092aa_2socket);
    qtest_add_func("/i82092aa/4-socket", test_i82092aa_4socket);

    return g_test_run();
}
