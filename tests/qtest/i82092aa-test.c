/*
 * QTest for the Intel 82092AA PCI-to-PCMCIA bridge
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "libqtest.h"
#include "libqos/pci.h"
#include "libqos/pci-pc.h"
#include "qobject/qdict.h"
#include "qobject/qlist.h"
#include "hw/pci/pci_ids.h"
#include "hw/pci/pci_regs.h"
#include "hw/pcmcia/i365.h"

#define I82092AA_PCICON         0x40
#define I82092AA_SOCKET_MASK    0x06
#define I82092AA_SOCKET_1       0x02
#define I82092AA_SOCKET_2       0x00
#define I82092AA_SOCKET_4       0x04

#define I82092AA_EXCA_IDENT     0x00
#define I82092AA_EXCA_STATUS    0x01
#define I82092AA_EXCA_POWER     0x02
#define I82092AA_EXCA_INTCTL    0x03
#define I82092AA_EXCA_CSC       0x04
#define I82092AA_EXCA_CSCINT    0x05
#define I82092AA_EXCA_IOCTL     0x07
#define I82092AA_EXCA_ADDRWIN   0x06
#define I82092AA_EXCA_IO0       0x08
#define I82092AA_EXCA_MEM0      0x10
#define I82092AA_SOCKET_STRIDE  0x40


#define WORLDPORT_ATTR_BASE     0x000d0000
#define WORLDPORT_IO_BASE       0x0300
#define WORLDPORT_CONFIG_BASE   0x0200

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

/* Guard the public QOM names and parent hierarchy against type drift. */
static void test_pcmcia_type_names(void)
{
    QTestState *qts;
    QDict *response;
    QList *types;
    QListEntry *entry;
    bool have_bus = false;
    bool have_card = false;
    bool have_controller = false;
    bool have_worldport = false;

    qts = qtest_init("-nodefaults -M pc -display none");
    response = qtest_qmp(qts,
        "{'execute': 'qom-list-types', 'arguments': {'abstract': true}}");
    g_assert_true(qdict_haskey(response, "return"));
    types = qdict_get_qlist(response, "return");

    QLIST_FOREACH_ENTRY(types, entry) {
        QDict *type = qobject_to(QDict, qlist_entry_obj(entry));
        const char *name = qdict_get_str(type, "name");
        const char *parent = qdict_get_try_str(type, "parent");

        if (!strcmp(name, "pcmcia-bus")) {
            g_assert_cmpstr(parent, ==, "bus");
            have_bus = true;
        } else if (!strcmp(name, "pcmcia-card")) {
            g_assert_cmpstr(parent, ==, "device");
            g_assert_true(qdict_get_bool(type, "abstract"));
            have_card = true;
        } else if (!strcmp(name, "i82092aa")) {
            g_assert_cmpstr(parent, ==, "pci-device");
            have_controller = true;
        } else if (!strcmp(name, "usr-worldport-v34")) {
            g_assert_cmpstr(parent, ==, "pcmcia-card");
            have_worldport = true;
        }
    }

    g_assert_true(have_bus);
    g_assert_true(have_card);
    g_assert_true(have_controller);
    if (qtest_has_device("usr-worldport-v34")) {
        g_assert_true(have_worldport);
    }

    qobject_unref(response);
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

static void exca_write(QPCIDevice *dev, QPCIBar bar,
                       uint8_t reg, uint8_t value)
{
    qpci_io_writeb(dev, bar, 0, reg);
    qpci_io_writeb(dev, bar, 1, value);
}

static uint8_t exca_read(QPCIDevice *dev, QPCIBar bar, uint8_t reg)
{
    qpci_io_writeb(dev, bar, 0, reg);
    return qpci_io_readb(dev, bar, 1);
}

/*
 * Explicit PCMCIA bus names must keep their socket numbering.  Socket 1
 * should accept a card independently of the empty socket 0.
 */
static void test_i82092aa_named_socket_bus(void)
{
    QTestState *qts;
    QPCIBus *pcibus;
    QPCIDevice *dev;
    QPCIBar bar;

    qts = qtest_init("-nodefaults -M pc -display none "
                     "-device i82092aa,addr=04.0,sockets=2,id=pcic "
                     "-device usr-worldport-v34,bus=pcic.1");
    pcibus = qpci_new_pc(qts, NULL);
    dev = qpci_device_find(pcibus, QPCI_DEVFN(0x4, 0x0));
    g_assert_nonnull(dev);
    qpci_device_enable(dev);
    bar = qpci_iomap(dev, 0, NULL);

    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_STATUS) &
                    I365_CS_DETECT, ==, 0);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_SOCKET_STRIDE +
                              I82092AA_EXCA_STATUS) & I365_CS_DETECT,
                    ==, I365_CS_DETECT);

    qpci_iounmap(dev, bar);
    g_free(dev);
    qpci_free_pc(pcibus);
    qtest_quit(qts);
}

static void test_i82092aa_worldport(void)
{
    QTestState *qts;
    QPCIBus *pcibus;
    QPCIDevice *dev;
    QPCIBar bar;
    uint8_t status;

    qts = qtest_init("-nodefaults -M pc -display none "
                     "-device i82092aa,addr=04.0,sockets=1,id=pcic "
                     "-device usr-worldport-v34,bus=pcic.0");
    pcibus = qpci_new_pc(qts, NULL);
    dev = qpci_device_find(pcibus, QPCI_DEVFN(0x4, 0x0));
    g_assert_nonnull(dev);
    qpci_device_enable(dev);
    bar = qpci_iomap(dev, 0, NULL);

    /*
     * QOM must recognize the socket as full before attempting to realize a
     * second card on the same 16-bit PCMCIA bus.
     */
    {
        QDict *reply = qtest_qmp(qts,
            "{'execute': 'device_add', 'arguments': {"
            " 'driver': 'usr-worldport-v34', 'id': 'duplicate-card',"
            " 'bus': 'pcic.0'}}");
        QDict *error = qdict_get_qdict(reply, "error");

        g_assert_nonnull(error);
        g_assert_nonnull(strstr(qdict_get_str(error, "desc"),
                                "Bus 'pcic.0' is full"));
        qobject_unref(reply);
    }

    status = exca_read(dev, bar, I82092AA_EXCA_STATUS);
    g_assert_cmphex(status & I365_CS_DETECT, ==, I365_CS_DETECT);
    g_assert_cmphex(status & (I365_CS_READY | I365_CS_POWERON), ==, 0);

    /* Insertion latches detect, but no PCI INTx is sent without a CSC mask. */
    g_assert_cmphex(qpci_config_readw(dev, PCI_STATUS) &
                    PCI_STATUS_INTERRUPT, ==, 0);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_CSC) &
                    I365_CSC_DETECT, ==, I365_CSC_DETECT);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_CSC), ==, 0);

    /* Enable detect/ready change notifications on the PCI interrupt. */
    exca_write(dev, bar, I82092AA_EXCA_CSCINT,
               I365_CSC_DETECT | I365_CSC_READY);
    g_assert_cmphex(qpci_config_readw(dev, PCI_STATUS) &
                    PCI_STATUS_INTERRUPT, ==, 0);

    /*
     * Map a 4 KiB host memory window at 0xd0000 to card attribute address 0.
     * The signed page offset is (0 - 0xd0000) >> 12 == -0xd0 == 0x3f30
     * in the 14-bit ExCA offset field; bit 14 selects attribute memory.
     */
    exca_write(dev, bar, I82092AA_EXCA_MEM0 + 0, 0xd0);
    exca_write(dev, bar, I82092AA_EXCA_MEM0 + 1, 0x00);
    exca_write(dev, bar, I82092AA_EXCA_MEM0 + 2, 0xd0);
    exca_write(dev, bar, I82092AA_EXCA_MEM0 + 3, 0x00);
    exca_write(dev, bar, I82092AA_EXCA_MEM0 + 4, 0x30);
    exca_write(dev, bar, I82092AA_EXCA_MEM0 + 5, 0x7f);
    exca_write(dev, bar, I82092AA_EXCA_ADDRWIN, I365_ENA_MEM(0));

    /* A programmed window is not active until Vcc is on and reset released. */
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_STATUS) &
                    I365_CS_READY, ==, 0);
    exca_write(dev, bar, I82092AA_EXCA_POWER,
               I365_PWR_OUT | I365_VCC_5V);
    status = exca_read(dev, bar, I82092AA_EXCA_STATUS);
    g_assert_cmphex(status & I365_CS_POWERON, ==, I365_CS_POWERON);
    g_assert_cmphex(status & I365_CS_READY, ==, 0);

    exca_write(dev, bar, I82092AA_EXCA_INTCTL, I365_PC_RESET);
    status = exca_read(dev, bar, I82092AA_EXCA_STATUS);
    g_assert_cmphex(status & (I365_CS_DETECT | I365_CS_READY |
                              I365_CS_POWERON), ==,
                    I365_CS_DETECT | I365_CS_READY | I365_CS_POWERON);
    /* A new READY event asserts PCI INTx until CSC is read. */
    g_assert_cmphex(qpci_config_readw(dev, PCI_STATUS) &
                    PCI_STATUS_INTERRUPT, ==, PCI_STATUS_INTERRUPT);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_CSC) &
                    I365_CSC_READY, ==, I365_CSC_READY);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_CSC), ==, 0);
    g_assert_cmphex(qpci_config_readw(dev, PCI_STATUS) &
                    PCI_STATUS_INTERRUPT, ==, 0);
    g_assert_cmphex(qtest_readb(qts, WORLDPORT_ATTR_BASE), ==, 0x15);
    g_assert_cmphex(qtest_readb(qts, WORLDPORT_ATTR_BASE + 1), ==, 0xff);
    g_assert_cmphex(qtest_readb(qts, WORLDPORT_ATTR_BASE + 2), ==, 0x35);

    /* Enable WorldPort configuration index 1 through its COR. */
    qtest_writeb(qts, WORLDPORT_ATTR_BASE + WORLDPORT_CONFIG_BASE, 0x01);
    g_assert_cmphex(qtest_readb(qts,
                               WORLDPORT_ATTR_BASE + WORLDPORT_CONFIG_BASE),
                    ==, 0x01);

    /* Map the controller's first I/O window onto the card's 8-byte UART. */
    exca_write(dev, bar, I82092AA_EXCA_IO0 + 0,
               WORLDPORT_IO_BASE & 0xff);
    exca_write(dev, bar, I82092AA_EXCA_IO0 + 1,
               WORLDPORT_IO_BASE >> 8);
    exca_write(dev, bar, I82092AA_EXCA_IO0 + 2,
               (WORLDPORT_IO_BASE + 7) & 0xff);
    exca_write(dev, bar, I82092AA_EXCA_IO0 + 3,
               (WORLDPORT_IO_BASE + 7) >> 8);
    exca_write(dev, bar, I82092AA_EXCA_ADDRWIN,
               I365_ENA_MEM(0) | I365_ENA_IO(0));

    /* 16550 scratch-register round trip proves host I/O reaches the card. */
    qtest_outb(qts, WORLDPORT_IO_BASE + 7, 0x5a);
    g_assert_cmphex(qtest_inb(qts, WORLDPORT_IO_BASE + 7), ==, 0x5a);

    /*
     * Default ExCA I/O width is 8-bit. A host word write/read must split
     * into byte accesses, with the high byte reaching the UART scratch
     * register at offset 7.
     */
    qtest_outw(qts, WORLDPORT_IO_BASE + 6, 0x6600);
    g_assert_cmphex(qtest_inb(qts, WORLDPORT_IO_BASE + 7), ==, 0x66);
    g_assert_cmphex(qtest_inw(qts, WORLDPORT_IO_BASE + 6) >> 8,
                    ==, 0x66);

    /*
     * 16-bit mode must make one card transaction, rather than combining
     * two 8-bit UART register reads. This serial card returns only a byte
     * from its first register and therefore a zero high byte.
     */
    exca_write(dev, bar, I82092AA_EXCA_IOCTL, 0x01);
    g_assert_cmphex(qtest_inw(qts, WORLDPORT_IO_BASE + 6) >> 8,
                    ==, 0);
    exca_write(dev, bar, I82092AA_EXCA_IOCTL, 0);

    /* Power loss hides card memory/I/O while card-detect remains asserted. */
    exca_write(dev, bar, I82092AA_EXCA_POWER, 0);
    status = exca_read(dev, bar, I82092AA_EXCA_STATUS);
    g_assert_cmphex(status & I365_CS_DETECT, ==, I365_CS_DETECT);
    g_assert_cmphex(status & (I365_CS_READY | I365_CS_POWERON), ==, 0);
    g_assert_cmphex(qpci_config_readw(dev, PCI_STATUS) &
                    PCI_STATUS_INTERRUPT, ==, PCI_STATUS_INTERRUPT);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_CSC) &
                    I365_CSC_READY, ==, I365_CSC_READY);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_CSC), ==, 0);
    g_assert_cmphex(qpci_config_readw(dev, PCI_STATUS) &
                    PCI_STATUS_INTERRUPT, ==, 0);

    /* Powering up again restores READY only while reset stays released. */
    exca_write(dev, bar, I82092AA_EXCA_POWER,
               I365_PWR_OUT | I365_VCC_5V);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_STATUS) &
                    I365_CS_READY, ==, I365_CS_READY);
    (void)exca_read(dev, bar, I82092AA_EXCA_CSC);
    exca_write(dev, bar, I82092AA_EXCA_INTCTL, 0);
    g_assert_cmphex(exca_read(dev, bar, I82092AA_EXCA_STATUS) &
                    I365_CS_READY, ==, 0);

    qpci_iounmap(dev, bar);
    g_free(dev);
    qpci_free_pc(pcibus);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    qtest_add_func("/i82092aa/qom-type-names", test_pcmcia_type_names);
    qtest_add_func("/i82092aa/1-socket", test_i82092aa_1socket);
    qtest_add_func("/i82092aa/2-socket", test_i82092aa_2socket);
    qtest_add_func("/i82092aa/4-socket", test_i82092aa_4socket);
    if (qtest_has_device("usr-worldport-v34")) {
        qtest_add_func("/i82092aa/named-socket-bus",
                       test_i82092aa_named_socket_bus);
        qtest_add_func("/i82092aa/worldport-v34", test_i82092aa_worldport);
    }

    return g_test_run();
}
