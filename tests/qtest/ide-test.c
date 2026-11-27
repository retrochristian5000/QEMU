/*
 * IDE test cases
 *
 * Copyright (c) 2013 Kevin Wolf <kwolf@redhat.com>
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"


#include "libqtest.h"
#include "libqos/libqos.h"
#include "libqos/pci-pc.h"
#include "libqos/malloc-pc.h"
#include "qobject/qdict.h"
#include "qemu/bswap.h"
#include "hw/pci/pci_ids.h"
#include "hw/pci/pci_regs.h"

/* Specified by ATA (physical) CHS geometry for ~64 MiB device.  */
#define TEST_IMAGE_SIZE ((130 * 16 * 63) * 512)

#define IDE_PCI_DEV     1
#define IDE_PCI_FUNC    1

#define IDE_BASE 0x1f0
#define IDE_BASE2 0x3f6
#define IDE_PRIMARY_IRQ 14

#define IDE_CTRL_RESET 0x04

#define ATAPI_BLOCK_SIZE 2048

/* How many bytes to receive via ATAPI PIO at one time.
 * Must be less than 0xFFFF. */
#define BYTE_COUNT_LIMIT 5120

enum {
    reg_data        = 0x0,
    reg_feature     = 0x1,
    reg_error       = 0x1,
    reg_nsectors    = 0x2,
    reg_lba_low     = 0x3,
    reg_lba_middle  = 0x4,
    reg_lba_high    = 0x5,
    reg_device      = 0x6,
    reg_status      = 0x7,
    reg_command     = 0x7,
};

enum {
    BSY     = 0x80,
    DRDY    = 0x40,
    DF      = 0x20,
    DRQ     = 0x08,
    ERR     = 0x01,
};

/* Error field */
enum {
    ABRT    = 0x04,
};

enum {
    DEV     = 0x10,
    LBA     = 0x40,
};

enum {
    bmreg_cmd       = 0x0,
    bmreg_status    = 0x2,
    bmreg_prdt      = 0x4,
};

enum {
    CMD_DSM         = 0x06,
    CMD_DEVICE_RESET = 0x08,
    CMD_DIAGNOSE    = 0x90,
    CMD_INIT_DP     = 0x91,  /* INITIALIZE DEVICE PARAMETERS */
    CMD_READ_DMA    = 0xc8,
    CMD_WRITE_DMA   = 0xca,
    CMD_FLUSH_CACHE = 0xe7,
    CMD_IDENTIFY    = 0xec,
    CMD_PACKET      = 0xa0,
    CMD_PACKET_IDENTIFY = 0xa1,
    CMD_READ_NATIVE = 0xf8,  /* READ NATIVE MAX ADDRESS */

    CMDF_ABORT      = 0x100,
    CMDF_NO_BM      = 0x200,
    CMDF_NO_WAIT    = 0x400,
};

enum {
    BM_CMD_START    =  0x1,
    BM_CMD_WRITE    =  0x8, /* write = from device to memory */
};

enum {
    BM_STS_ACTIVE   =  0x1,
    BM_STS_ERROR    =  0x2,
    BM_STS_INTR     =  0x4,
};

enum {
    PRDT_EOT        = 0x80000000,
};

#define assert_bit_set(data, mask) g_assert_cmphex((data) & (mask), ==, (mask))
#define assert_bit_clear(data, mask) g_assert_cmphex((data) & (mask), ==, 0)

static QPCIBus *pcibus = NULL;
static QGuestAllocator guest_malloc;

static char *tmp_path[2];
static char *debug_path;

G_GNUC_PRINTF(1, 2)
static QTestState *ide_test_start(const char *cmdline_fmt, ...)
{
    QTestState *qts;
    g_autofree char *full_fmt = g_strdup_printf("-machine pc %s", cmdline_fmt);
    va_list ap;

    va_start(ap, cmdline_fmt);
    qts = qtest_vinitf(full_fmt, ap);
    va_end(ap);

    pc_alloc_init(&guest_malloc, qts, 0);

    return qts;
}

static void ide_test_quit(QTestState *qts)
{
    if (pcibus) {
        qpci_free_pc(pcibus);
        pcibus = NULL;
    }
    alloc_destroy(&guest_malloc);
    qtest_quit(qts);
}

static QPCIDevice *get_pci_device(QTestState *qts, QPCIBar *bmdma_bar,
                                  QPCIBar *ide_bar)
{
    QPCIDevice *dev;
    uint16_t vendor_id, device_id;

    if (!pcibus) {
        pcibus = qpci_new_pc(qts, NULL);
    }

    /* Find PCI device and verify it's the right one */
    dev = qpci_device_find(pcibus, QPCI_DEVFN(IDE_PCI_DEV, IDE_PCI_FUNC));
    g_assert(dev != NULL);

    vendor_id = qpci_config_readw(dev, PCI_VENDOR_ID);
    device_id = qpci_config_readw(dev, PCI_DEVICE_ID);
    g_assert(vendor_id == PCI_VENDOR_ID_INTEL);
    g_assert(device_id == PCI_DEVICE_ID_INTEL_82371SB_1);

    /* Map bmdma BAR */
    *bmdma_bar = qpci_iomap(dev, 4, NULL);

    *ide_bar = qpci_legacy_iomap(dev, IDE_BASE);

    qpci_device_enable(dev);

    return dev;
}

static void free_pci_device(QPCIDevice *dev)
{
    /* libqos doesn't have a function for this, so free it manually */
    g_free(dev);
}

typedef struct PrdtEntry {
    uint32_t addr;
    uint32_t size;
} QEMU_PACKED PrdtEntry;

#define assert_bit_set(data, mask) g_assert_cmphex((data) & (mask), ==, (mask))
#define assert_bit_clear(data, mask) g_assert_cmphex((data) & (mask), ==, 0)

static uint64_t trim_range_le(uint64_t sector, uint16_t count)
{
    /* 2-byte range, 6-byte LBA */
    return cpu_to_le64(((uint64_t)count << 48) + sector);
}

static uint8_t wait_dma_completion(QTestState *qts, QPCIDevice *dev,
                                   QPCIBar bmdma_bar, QPCIBar ide_bar)
{
    uint8_t status;

    /* Wait for the DMA transfer to complete */
    do {
        status = qpci_io_readb(dev, bmdma_bar, bmreg_status);
    } while ((status & (BM_STS_ACTIVE | BM_STS_INTR)) == BM_STS_ACTIVE);

    g_assert_cmpint(qtest_get_irq(qts, IDE_PRIMARY_IRQ), ==,
                    !!(status & BM_STS_INTR));

    /* Check IDE status code */
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), DRDY);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), BSY | DRQ);

    /* Reading the status register clears the IRQ */
    g_assert(!qtest_get_irq(qts, IDE_PRIMARY_IRQ));

    /* Stop DMA transfer if still active */
    if (status & BM_STS_ACTIVE) {
        qpci_io_writeb(dev, bmdma_bar, bmreg_cmd, 0);
    }

    return status;
}

static int send_dma_request_dev(QTestState *qts, QPCIDevice *dev,
                                QPCIBar bmdma_bar, QPCIBar ide_bar, int cmd,
                                uint64_t sector, int nb_sectors,
                                PrdtEntry *prdt, int prdt_entries,
                                void(*post_exec)(QPCIDevice *dev,
                                                 QPCIBar ide_bar,
                                                 uint64_t sector,
                                                 int nb_sectors))
{
    uintptr_t guest_prdt;
    size_t len;
    bool from_dev;
    uint8_t status;
    int flags;

    flags = cmd & ~0xff;
    cmd &= 0xff;

    switch (cmd) {
    case CMD_READ_DMA:
    case CMD_PACKET:
        /* Assuming we only test data reads w/ ATAPI, otherwise we need to know
         * the SCSI command being sent in the packet, too. */
        from_dev = true;
        break;
    case CMD_DSM:
    case CMD_WRITE_DMA:
        from_dev = false;
        break;
    default:
        g_assert_not_reached();
    }

    if (flags & CMDF_NO_BM) {
        qpci_config_writew(dev, PCI_COMMAND,
                           PCI_COMMAND_IO | PCI_COMMAND_MEMORY);
    }

    /* Select device 0 */
    qpci_io_writeb(dev, ide_bar, reg_device, 0 | LBA);

    /* Stop any running transfer, clear any pending interrupt */
    qpci_io_writeb(dev, bmdma_bar, bmreg_cmd, 0);
    qpci_io_writeb(dev, bmdma_bar, bmreg_status, BM_STS_INTR);

    /* Setup PRDT */
    len = sizeof(*prdt) * prdt_entries;
    guest_prdt = guest_alloc(&guest_malloc, len);
    qtest_memwrite(qts, guest_prdt, prdt, len);
    qpci_io_writel(dev, bmdma_bar, bmreg_prdt, guest_prdt);

    /* ATA DMA command */
    if (cmd == CMD_PACKET) {
        /* Enables ATAPI DMA; otherwise PIO is attempted */
        qpci_io_writeb(dev, ide_bar, reg_feature, 0x01);
    } else {
        if (cmd == CMD_DSM) {
            /* trim bit */
            qpci_io_writeb(dev, ide_bar, reg_feature, 0x01);
        }
        qpci_io_writeb(dev, ide_bar, reg_nsectors, nb_sectors);
        qpci_io_writeb(dev, ide_bar, reg_lba_low,    sector & 0xff);
        qpci_io_writeb(dev, ide_bar, reg_lba_middle, (sector >> 8) & 0xff);
        qpci_io_writeb(dev, ide_bar, reg_lba_high,   (sector >> 16) & 0xff);
    }

    qpci_io_writeb(dev, ide_bar, reg_command, cmd);

    if (post_exec) {
        post_exec(dev, ide_bar, sector, nb_sectors);
    }

    /* Start DMA transfer */
    qpci_io_writeb(dev, bmdma_bar, bmreg_cmd,
                   BM_CMD_START | (from_dev ? BM_CMD_WRITE : 0));

    if (flags & CMDF_ABORT) {
        qpci_io_writeb(dev, bmdma_bar, bmreg_cmd, 0);
    }

    if (flags & CMDF_NO_WAIT) {
        return 0;
    }

    status = wait_dma_completion(qts, dev, bmdma_bar, ide_bar);

    return status;
}

static int send_dma_request(QTestState *qts, int cmd, uint64_t sector,
                            int nb_sectors, PrdtEntry *prdt, int prdt_entries,
                            void(*post_exec)(QPCIDevice *dev, QPCIBar ide_bar,
                                             uint64_t sector, int nb_sectors))
{
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    status = send_dma_request_dev(qts, dev, bmdma_bar, ide_bar,
                                  cmd, sector, nb_sectors, prdt, prdt_entries,
                                  post_exec);
    free_pci_device(dev);

    return status;
}

static QTestState *test_bmdma_setup(void)
{
    QTestState *qts;

    qts = ide_test_start(
        "-drive file=%s,if=ide,cache=writeback,format=raw "
        "-global ide-hd.serial=%s -global ide-hd.ver=%s",
        tmp_path[0], "testdisk", "version");
    qtest_irq_intercept_in(qts, "ioapic");

    return qts;
}

static void test_bmdma_teardown(QTestState *qts)
{
    ide_test_quit(qts);
}

static void test_bmdma_simple_rw(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;
    uint8_t *buf;
    uint8_t *cmpbuf;
    size_t len = 512;
    uintptr_t guest_buf;
    PrdtEntry prdt[1];

    qts = test_bmdma_setup();

    guest_buf  = guest_alloc(&guest_malloc, len);
    prdt[0].addr = cpu_to_le32(guest_buf);
    prdt[0].size = cpu_to_le32(len | PRDT_EOT);

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    buf = g_malloc(len);
    cmpbuf = g_malloc(len);

    /* Write 0x55 pattern to sector 0 */
    memset(buf, 0x55, len);
    qtest_memwrite(qts, guest_buf, buf, len);

    status = send_dma_request(qts, CMD_WRITE_DMA, 0, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    /* Write 0xaa pattern to sector 1 */
    memset(buf, 0xaa, len);
    qtest_memwrite(qts, guest_buf, buf, len);

    status = send_dma_request(qts, CMD_WRITE_DMA, 1, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    /* Read and verify 0x55 pattern in sector 0 */
    memset(cmpbuf, 0x55, len);

    status = send_dma_request(qts, CMD_READ_DMA, 0, 1, prdt, ARRAY_SIZE(prdt),
                              NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    qtest_memread(qts, guest_buf, buf, len);
    g_assert(memcmp(buf, cmpbuf, len) == 0);

    /* Read and verify 0xaa pattern in sector 1 */
    memset(cmpbuf, 0xaa, len);

    status = send_dma_request(qts, CMD_READ_DMA, 1, 1, prdt, ARRAY_SIZE(prdt),
                              NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    qtest_memread(qts, guest_buf, buf, len);
    g_assert(memcmp(buf, cmpbuf, len) == 0);

    free_pci_device(dev);
    g_free(buf);
    g_free(cmpbuf);

    test_bmdma_teardown(qts);
}

static void test_bmdma_trim(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;
    const uint64_t trim_range[] = { trim_range_le(0, 2),
                                    trim_range_le(6, 8),
                                    trim_range_le(10, 1),
                                  };
    const uint64_t bad_range = trim_range_le(TEST_IMAGE_SIZE / 512 - 1, 2);
    size_t len = 512;
    uint8_t *buf;
    uintptr_t guest_buf;
    PrdtEntry prdt[1];

    qts = test_bmdma_setup();

    guest_buf = guest_alloc(&guest_malloc, len);
    prdt[0].addr = cpu_to_le32(guest_buf),
    prdt[0].size = cpu_to_le32(len | PRDT_EOT),

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    buf = g_malloc(len);

    /* Normal request */
    *((uint64_t *)buf) = trim_range[0];
    *((uint64_t *)buf + 1) = trim_range[1];

    qtest_memwrite(qts, guest_buf, buf, 2 * sizeof(uint64_t));

    status = send_dma_request(qts, CMD_DSM, 0, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    /* Request contains invalid range */
    *((uint64_t *)buf) = trim_range[2];
    *((uint64_t *)buf + 1) = bad_range;

    qtest_memwrite(qts, guest_buf, buf, 2 * sizeof(uint64_t));

    status = send_dma_request(qts, CMD_DSM, 0, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);

    free_pci_device(dev);
    g_free(buf);
    test_bmdma_teardown(qts);
}

static void test_bmdma_trim_split_descriptor(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    PrdtEntry prdt[2];
    uint8_t payload[512] = { 0 };
    uint64_t entry;
    uintptr_t first, second;
    uint8_t status;

    qts = test_bmdma_setup();
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /*
     * A 512-byte DSM payload can use multiple DMA PRDs. Split its first
     * 8-byte TRIM range in half: neither PRD contains a complete range.
     * The descriptor must be decoded across the PRD boundary.
     */
    first = guest_alloc(&guest_malloc, 4);
    second = guest_alloc(&guest_malloc, sizeof(payload) - 4);
    prdt[0].addr = cpu_to_le32(first);
    prdt[0].size = cpu_to_le32(4);
    prdt[1].addr = cpu_to_le32(second);
    prdt[1].size = cpu_to_le32((sizeof(payload) - 4) | PRDT_EOT);

    /* The whole split descriptor describes an out-of-range discard. */
    entry = trim_range_le(TEST_IMAGE_SIZE / 512 - 1, 2);
    memcpy(payload, &entry, sizeof(entry));
    qtest_memwrite(qts, first, payload, 4);
    qtest_memwrite(qts, second, payload + 4, sizeof(payload) - 4);

    status = send_dma_request(qts, CMD_DSM, 0, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);

    /* The same split across PRDs must also accept an in-range descriptor. */
    entry = trim_range_le(0, 1);
    memcpy(payload, &entry, sizeof(entry));
    qtest_memwrite(qts, first, payload, 4);
    qtest_memwrite(qts, second, payload + 4, sizeof(payload) - 4);

    status = send_dma_request(qts, CMD_DSM, 0, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    free_pci_device(dev);
    test_bmdma_teardown(qts);
}

static void test_bmdma_trim_reset(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar, ide_bar2;
    uint8_t status;
    const uint64_t trim_range[] = {
        trim_range_le(0, 2),
        trim_range_le(6, 8),
    };
    size_t len = 512;
    uint8_t *buf;
    uintptr_t guest_buf;
    PrdtEntry prdt[1];

    qts = ide_test_start(
        "-blockdev file,filename=%s,node-name=img "
        "-blockdev blkdebug,image=img,node-name=dbg,discard=unmap,"
        "inject-error.0.event=none,inject-error.0.iotype=discard,"
        "inject-error.0.errno=0,inject-error.0.delay-ns=1000000 "
        "-device ide-hd,drive=dbg,bus=ide.0",
        tmp_path[0]);
    qtest_irq_intercept_in(qts, "ioapic");

    guest_buf = guest_alloc(&guest_malloc, len);
    prdt[0].addr = cpu_to_le32(guest_buf),
    prdt[0].size = cpu_to_le32(len | PRDT_EOT),

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    ide_bar2 = qpci_legacy_iomap(dev, IDE_BASE2);

    buf = g_malloc(len);

    /* TRIM request with two segments */
    *((uint64_t *)buf) = trim_range[0];
    *((uint64_t *)buf + 1) = trim_range[1];

    qtest_memwrite(qts, guest_buf, buf, 2 * sizeof(uint64_t));

    send_dma_request_dev(qts, dev, bmdma_bar, ide_bar, CMD_DSM | CMDF_NO_WAIT, 0, 1, prdt,
                     ARRAY_SIZE(prdt), NULL);

    /* Reset the device while the first segment is in flight */
    qpci_io_writeb(dev, ide_bar2, 0, IDE_CTRL_RESET);

    status = wait_dma_completion(qts, dev, bmdma_bar, ide_bar);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    free_pci_device(dev);
    g_free(buf);
    test_bmdma_teardown(qts);
}

/*
 * This test is developed according to the Programming Interface for
 * Bus Master IDE Controller (Revision 1.0 5/16/94)
 */
static void test_bmdma_various_prdts(void)
{
    int sectors = 0;
    uint32_t size = 0;

    for (sectors = 1; sectors <= 256; sectors *= 2) {
        QTestState *qts = NULL;
        QPCIDevice *dev = NULL;
        QPCIBar bmdma_bar, ide_bar;

        qts = test_bmdma_setup();
        dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

        for (size = 0; size < 65536; size += 256) {
            uint32_t req_size = sectors * 512;
            uint32_t prd_size = size & 0xfffe; /* bit 0 is always set to 0 */
            uint8_t ret = 0;
            uint8_t req_status = 0;
            uint8_t abort_req_status = 0;
            PrdtEntry prdt[] = {
                {
                    .addr = 0,
                    .size = cpu_to_le32(size | PRDT_EOT),
                },
            };

            /* A value of zero in PRD size indicates 64K */
            if (prd_size == 0) {
                prd_size = 65536;
            }

            /*
             * 1. If PRDs specified a smaller size than the IDE transfer
             * size, then the Interrupt and Active bits in the Controller
             * status register are not set (Error Condition).
             *
             * 2. If the size of the physical memory regions was equal to
             * the IDE device transfer size, the Interrupt bit in the
             * Controller status register is set to 1, Active bit is set to 0.
             *
             * 3. If PRDs specified a larger size than the IDE transfer size,
             * the Interrupt and Active bits in the Controller status register
             * are both set to 1.
             */
            if (prd_size < req_size) {
                req_status = 0;
                abort_req_status = 0;
            } else if (prd_size == req_size) {
                req_status = BM_STS_INTR;
                abort_req_status = BM_STS_INTR;
            } else {
                req_status = BM_STS_ACTIVE | BM_STS_INTR;
                abort_req_status = BM_STS_INTR;
            }

            /* Test the request */
            ret = send_dma_request(qts, CMD_READ_DMA, 0, sectors,
                                   prdt, ARRAY_SIZE(prdt), NULL);
            g_assert_cmphex(ret, ==, req_status);
            assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

            /* Now test aborting the same request */
            ret = send_dma_request(qts, CMD_READ_DMA | CMDF_ABORT, 0,
                                   sectors, prdt, ARRAY_SIZE(prdt), NULL);
            g_assert_cmphex(ret, ==, abort_req_status);
            assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);
        }

        free_pci_device(dev);
        test_bmdma_teardown(qts);
    }
}

static void test_bmdma_no_busmaster(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;

    qts = test_bmdma_setup();

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* No PRDT_EOT, each entry addr 0/size 64k, and in theory qemu shouldn't be
     * able to access it anyway because the Bus Master bit in the PCI command
     * register isn't set. This is complete nonsense, but it used to be pretty
     * good at confusing and occasionally crashing qemu. */
    PrdtEntry prdt[4096] = { };

    status = send_dma_request(qts, CMD_READ_DMA | CMDF_NO_BM, 0, 512,
                              prdt, ARRAY_SIZE(prdt), NULL);

    /* A disabled PCI bus master must fail the PRD fetch instead of
     * interpreting a failed DMA read as a valid descriptor. */
    g_assert_cmphex(status, ==, BM_STS_ERROR | BM_STS_INTR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
    free_pci_device(dev);
    test_bmdma_teardown(qts);
}

static void string_cpu_to_be16(uint16_t *s, size_t bytes)
{
    g_assert((bytes & 1) == 0);
    bytes /= 2;

    while (bytes--) {
        *s = cpu_to_be16(*s);
        s++;
    }
}

static void test_specify(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint16_t cyls;
    uint8_t heads, spt;

    qts = ide_test_start(
        "-blockdev driver=file,node-name=hda,filename=%s "
        "-device ide-hd,drive=hda,bus=ide.0,unit=0 ",
        tmp_path[0]);

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* Initialize drive with zero sectors per track and one head.  */
    qpci_io_writeb(dev, ide_bar, reg_nsectors, 0);
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_INIT_DP);

    /* READ NATIVE MAX ADDRESS (CHS mode).  */
    qpci_io_writeb(dev, ide_bar, reg_device, 0xa0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_READ_NATIVE);

    heads = qpci_io_readb(dev, ide_bar, reg_device) & 0xf;
    ++heads;
    g_assert_cmpint(heads, ==, 16);

    cyls = qpci_io_readb(dev, ide_bar, reg_lba_high) << 8;
    cyls |= qpci_io_readb(dev, ide_bar, reg_lba_middle);
    ++cyls;
    g_assert_cmpint(cyls, ==, 130);

    spt = qpci_io_readb(dev, ide_bar, reg_lba_low);
    g_assert_cmpint(spt, ==, 63);

    ide_test_quit(qts);
    free_pci_device(dev);
}

/* PIIX bus-master registers accept byte, word and dword I/O accesses. */
static void test_piix_bmdma_access_width(void)
{
    QTestState *qts = ide_test_start("-nodefaults");
    QPCIBar bmdma_bar, ide_bar;
    QPCIDevice *dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    for (unsigned channel = 0; channel < 2; channel++) {
        unsigned base = channel * 8;

        /* Avoid starting DMA: change only direction and capability bits. */
        qpci_io_writew(dev, bmdma_bar, base + bmreg_cmd, BM_CMD_WRITE);
        g_assert_cmphex(qpci_io_readb(dev, bmdma_bar, base + bmreg_cmd),
                        ==, BM_CMD_WRITE);
        g_assert_cmphex(qpci_io_readw(dev, bmdma_bar, base + bmreg_cmd)
                        & 0xff, ==, BM_CMD_WRITE);

        qpci_io_writew(dev, bmdma_bar, base + bmreg_status, 0x20);
        g_assert_cmphex(qpci_io_readb(dev, bmdma_bar, base + bmreg_status),
                        ==, 0x20);
        g_assert_cmphex(qpci_io_readw(dev, bmdma_bar, base + bmreg_status)
                        & 0xff, ==, 0x20);

        /* Ignore reserved bytes but verify both meaningful registers. */
        qpci_io_writel(dev, bmdma_bar, base, 0x00400000);
        g_assert_cmphex(qpci_io_readb(dev, bmdma_bar, base + bmreg_cmd),
                        ==, 0);
        g_assert_cmphex(qpci_io_readb(dev, bmdma_bar, base + bmreg_status),
                        ==, 0x40);
        g_assert_cmphex(qpci_io_readl(dev, bmdma_bar, base) & 0x00ff00ff,
                        ==, 0x00400000);
    }

    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_identify(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t data;
    uint16_t buf[256];
    int i;
    int ret;

    qts = ide_test_start(
        "-drive file=%s,if=ide,cache=writeback,format=raw "
        "-global ide-hd.serial=%s -global ide-hd.ver=%s",
        tmp_path[0], "testdisk", "version");

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* IDENTIFY command on device 0*/
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_IDENTIFY);

    /* Read in the IDENTIFY buffer and check registers */
    data = qpci_io_readb(dev, ide_bar, reg_device);
    g_assert_cmpint(data & DEV, ==, 0);

    for (i = 0; i < 256; i++) {
        data = qpci_io_readb(dev, ide_bar, reg_status);
        assert_bit_set(data, DRDY | DRQ);
        assert_bit_clear(data, BSY | DF | ERR);

        buf[i] = qpci_io_readw(dev, ide_bar, reg_data);
    }

    data = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(data, DRDY);
    assert_bit_clear(data, BSY | DF | ERR | DRQ);

    /* Check serial number/version in the buffer */
    string_cpu_to_be16(&buf[10], 20);
    ret = memcmp(&buf[10], "testdisk            ", 20);
    g_assert(ret == 0);

    string_cpu_to_be16(&buf[23], 8);
    ret = memcmp(&buf[23], "version ", 8);
    g_assert(ret == 0);

    /* Write cache enabled bit */
    assert_bit_set(buf[85], 0x20);

    ide_test_quit(qts);
    free_pci_device(dev);
}

typedef struct AtaHdIdentity {
    const char *type;
    const char *model;
    uint16_t major;
    uint16_t udma;
    const char *options;
} AtaHdIdentity;

static const AtaHdIdentity ata_hd_identities[] = {
    { "ide-hd", "QEMU HARDDISK", 0xf0, 0x3f, "" },
    { "seagate-st31640a", "ST31640A", 0, 0, "" },
    { "seagate-st32140a", "ST32140A", 0, 0, "" },
    { "ibm-dtta-351010", "IBM-DTTA-351010", 0x1e, 7, "" },
    { "ibm-dtta-351010", "Override HDD", 0x1e, 7,
      ",model=Override HDD,rotation_rate=0" },
};

static void read_ata_identify(QPCIDevice *dev, QPCIBar bar, uint16_t *id)
{
    qpci_io_writeb(dev, bar, reg_command, CMD_IDENTIFY);
    for (unsigned i = 0; i < 256; i++) {
        assert_bit_set(qpci_io_readb(dev, bar, reg_status), DRDY | DRQ);
        id[i] = qpci_io_readw(dev, bar, reg_data);
    }
    assert_bit_clear(qpci_io_readb(dev, bar, reg_status), BSY | DRQ | ERR);
}

/* Exercise the legacy drive attachment path, not explicit -device. */
static void test_pc_legacy_hd_model(gconstpointer opaque)
{
    const AtaHdIdentity *profile = opaque;
    g_autofree char *path = NULL;
    int fd = g_file_open_tmp("qemu-ide-model-XXXXXX", &path, NULL);
    int64_t bytes = TEST_IMAGE_SIZE;
    uint16_t id[256];
    char expected[40];

    g_assert_cmpint(fd, >=, 0);
    if (g_str_equal(profile->type, "seagate-st31640a")) {
        bytes = INT64_C(3175200) * 512;
    } else if (g_str_equal(profile->type, "seagate-st32140a")) {
        bytes = INT64_C(4127760) * 512;
    } else if (g_str_equal(profile->type, "ibm-dtta-351010")) {
        bytes = INT64_C(19807200) * 512;
    }
    g_assert_cmpint(ftruncate(fd, bytes), ==, 0);
    close(fd);
    g_autofree char *quoted = g_shell_quote(path);
    QTestState *qts = qtest_initf(
        "-machine pc -nodefaults "
        "-drive if=ide,index=0,format=raw,file=%s", quoted);
    unlink(path);
    qtest_outb(qts, 0x1f6, 0xe0);
    qtest_outb(qts, 0x1f7, CMD_IDENTIFY);
    assert_bit_set(qtest_inb(qts, 0x1f7), DRDY | DRQ);
    for (unsigned i = 0; i < ARRAY_SIZE(id); i++) {
        id[i] = qtest_inw(qts, 0x1f0);
    }
    assert_bit_clear(qtest_inb(qts, 0x1f7), BSY | DRQ | ERR);
    memset(expected, ' ', sizeof(expected));
    memcpy(expected, profile->model, strlen(profile->model));
    string_cpu_to_be16(&id[27], sizeof(expected));
    g_assert_cmpmem(&id[27], sizeof(expected), expected, sizeof(expected));
    g_assert_cmphex(id[80], ==, profile->major);
    g_assert_cmpuint((uint32_t)id[60] | ((uint32_t)id[61] << 16),
                     ==, bytes / 512);
    qtest_quit(qts);
}

static void test_ata_hd_identity(gconstpointer opaque)
{
    const AtaHdIdentity *profile = opaque;
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint16_t buf[256];
    char expected[40];

    qts = ide_test_start("-drive if=none,file=%s,format=raw,id=disk0 "
                         "-device %s,bus=ide.0,unit=0,drive=disk0%s",
                         tmp_path[0], profile->type, profile->options);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_IDENTIFY);
    for (unsigned i = 0; i < ARRAY_SIZE(buf); i++) {
        assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), DRDY | DRQ);
        buf[i] = qpci_io_readw(dev, ide_bar, reg_data);
    }
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DRQ | ERR);

    memset(expected, ' ', sizeof(expected));
    memcpy(expected, profile->model, strlen(profile->model));
    string_cpu_to_be16(&buf[27], sizeof(expected));
    g_assert_cmpmem(&buf[27], sizeof(expected), expected, sizeof(expected));
    g_assert_cmphex(buf[80], ==, profile->major);
    g_assert_cmphex(buf[88] & 0xff, ==, profile->udma);
    g_assert_cmpuint(buf[217], ==, 0);
    g_assert_cmpuint((uint32_t)buf[60] | ((uint32_t)buf[61] << 16),
                     ==, TEST_IMAGE_SIZE / 512);

    /* IDENTIFY must reflect each new multiple-sector count. */
    const uint8_t counts[] = { 1, 8, 0, 16 };

    for (size_t i = 0; i < ARRAY_SIZE(counts); i++) {
        qpci_io_writeb(dev, ide_bar, reg_nsectors, counts[i]);
        qpci_io_writeb(dev, ide_bar, reg_command, 0xc6);
        assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), ERR);
        read_ata_identify(dev, ide_bar, buf);
        g_assert_cmphex(buf[59], ==, 0x100 | counts[i]);
    }

    /* Mode selection must not fabricate supported DMA modes. */
    qpci_io_writeb(dev, ide_bar, reg_feature, 3);
    qpci_io_writeb(dev, ide_bar, reg_nsectors, 0x22);
    qpci_io_writeb(dev, ide_bar, reg_command, 0xef);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), ERR);
    read_ata_identify(dev, ide_bar, buf);
    g_assert_cmphex(buf[63], ==, 0x407);
    g_assert_cmphex(buf[88], ==, profile->udma);

    qpci_io_writeb(dev, ide_bar, reg_feature, 3);
    qpci_io_writeb(dev, ide_bar, reg_nsectors, 0x47);
    qpci_io_writeb(dev, ide_bar, reg_command, 0xef);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
    read_ata_identify(dev, ide_bar, buf);
    g_assert_cmphex(buf[63], ==, 0x407);
    g_assert_cmphex(buf[88], ==, profile->udma);

    if (profile->major != 0xf0) {
        g_assert_cmphex(buf[83] & 0x0400, ==, 0);
        g_assert_cmphex(buf[100] | buf[101] | buf[102] | buf[103], ==, 0);
        g_assert_cmphex(buf[169], ==, 0);
        /* Reject newer commands before any data phase begins. */
        const uint8_t unsupported[] = { 0x24, 0x34, 0x25, 0x35, 0xea, 0x06 };
        for (unsigned i = 0; i < ARRAY_SIZE(unsupported); i++) {
            qpci_io_writeb(dev, ide_bar, reg_command, unsupported[i]);
            assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
            assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);
        }
        /* SET FEATURES: UDMA mode 5 must be rejected by both profiles. */
        qpci_io_writeb(dev, ide_bar, reg_feature, 3);
        qtest_outb(qts, 0x1f2, 0x45);
        qpci_io_writeb(dev, ide_bar, reg_command, 0xef);
        assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
        assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);
        /* UDMA mode 2 works only on the IBM profile. */
        qpci_io_writeb(dev, ide_bar, reg_feature, 3);
        qtest_outb(qts, 0x1f2, 0x42);
        qpci_io_writeb(dev, ide_bar, reg_command, 0xef);
        g_assert_cmpint(!!(qpci_io_readb(dev, ide_bar, reg_status) & ERR),
                        ==, profile->major == 0);
    }

    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_ata_atapi_command_boundary(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;

    qts = ide_test_start(
        "-blockdev driver=file,node-name=hda,filename=%s "
        "-device ide-hd,drive=hda,bus=ide.0,unit=0 "
        "-device ide-cd,bus=ide.0,unit=1", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* ATA disks reject packet-only opcodes. */
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET_IDENTIFY);
    status = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(status, ERR);
    assert_bit_clear(status, BSY | DRQ);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);

    qpci_io_writeb(dev, ide_bar, reg_command, CMD_DEVICE_RESET);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);

    /* A packet device rejects ATA IDENTIFY and reports its signature. */
    qpci_io_writeb(dev, ide_bar, reg_device, DEV);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_IDENTIFY);
    status = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(status, ERR);
    assert_bit_clear(status, BSY | DRQ);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_lba_middle), ==, 0x14);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_lba_high), ==, 0xeb);

    /* DEVICE RESET must interrupt an ATAPI command in its DRQ phase. */
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET_IDENTIFY);
    status = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(status, DRQ);
    assert_bit_clear(status, BSY | ERR);

    qpci_io_writeb(dev, ide_bar, reg_command, CMD_DEVICE_RESET);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_status), ==, 0);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_nsectors), ==, 1);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_lba_low), ==, 1);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_lba_middle), ==, 0x14);
    g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_lba_high), ==, 0xeb);

    /* The ATA disk on the same channel remains usable. */
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_IDENTIFY);
    status = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(status, DRQ);
    assert_bit_clear(status, BSY | ERR);
    for (int i = 0; i < 256; i++) {
        qpci_io_readw(dev, ide_bar, reg_data);
    }
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), BSY | DRQ | ERR);

    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_diagnostic(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t data;

    qts = ide_test_start(
        "-blockdev driver=file,node-name=hda,filename=%s "
        "-blockdev driver=file,node-name=hdb,filename=%s "
        "-device ide-hd,drive=hda,bus=ide.0,unit=0 "
        "-device ide-hd,drive=hdb,bus=ide.0,unit=1 ",
        tmp_path[0], tmp_path[1]);

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* DIAGNOSE command on device 1 */
    qpci_io_writeb(dev, ide_bar, reg_device, DEV);
    data = qpci_io_readb(dev, ide_bar, reg_device);
    g_assert_cmphex(data & DEV, ==, DEV);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_DIAGNOSE);

    /* Verify that DEVICE is now 0 */
    data = qpci_io_readb(dev, ide_bar, reg_device);
    g_assert_cmphex(data & DEV, ==, 0);

    ide_test_quit(qts);
    free_pci_device(dev);
}

/*
 * Write sector 1 with random data to make IDE storage dirty
 * Needed for flush tests so that flushes actually go though the block layer
 */
static void make_dirty(QTestState *qts, uint8_t device)
{
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;
    size_t len = 512;
    uintptr_t guest_buf;
    void* buf;

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    guest_buf = guest_alloc(&guest_malloc, len);
    buf = g_malloc(len);
    memset(buf, rand() % 255 + 1, len);
    g_assert(guest_buf);
    g_assert(buf);

    qtest_memwrite(qts, guest_buf, buf, len);

    PrdtEntry prdt[] = {
        {
            .addr = cpu_to_le32(guest_buf),
            .size = cpu_to_le32(len | PRDT_EOT),
        },
    };

    status = send_dma_request(qts, CMD_WRITE_DMA, 1, 1, prdt,
                              ARRAY_SIZE(prdt), NULL);
    g_assert_cmphex(status, ==, BM_STS_INTR);
    assert_bit_clear(qpci_io_readb(dev, ide_bar, reg_status), DF | ERR);

    g_free(buf);
    free_pci_device(dev);
}

static void test_flush(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t data;

    qts = ide_test_start(
        "-drive file=blkdebug::%s,if=ide,cache=writeback,format=raw",
        tmp_path[0]);

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    qtest_irq_intercept_in(qts, "ioapic");

    /* Dirty media so that CMD_FLUSH_CACHE will actually go to disk */
    make_dirty(qts, 0);

    /* Delay the completion of the flush request until we explicitly do it */
    g_free(qtest_hmp(qts, "qemu-io ide0-hd0 \"break flush_to_os A\""));

    /* FLUSH CACHE command on device 0*/
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_FLUSH_CACHE);

    /* Check status while request is in flight*/
    data = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(data, BSY | DRDY);
    assert_bit_clear(data, DF | ERR | DRQ);

    /* Complete the command */
    g_free(qtest_hmp(qts, "qemu-io ide0-hd0 \"resume A\""));

    /* Check registers */
    data = qpci_io_readb(dev, ide_bar, reg_device);
    g_assert_cmpint(data & DEV, ==, 0);

    do {
        data = qpci_io_readb(dev, ide_bar, reg_status);
    } while (data & BSY);

    assert_bit_set(data, DRDY);
    assert_bit_clear(data, BSY | DF | ERR | DRQ);

    ide_test_quit(qts);
    free_pci_device(dev);
}

static void test_pci_retry_flush(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t data;

    prepare_blkdebug_script(debug_path, "flush_to_disk");

    qts = ide_test_start(
        "-drive file=blkdebug:%s:%s,if=ide,cache=writeback,format=raw,"
        "rerror=stop,werror=stop",
        debug_path, tmp_path[0]);

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    qtest_irq_intercept_in(qts, "ioapic");

    /* Dirty media so that CMD_FLUSH_CACHE will actually go to disk */
    make_dirty(qts, 0);

    /* FLUSH CACHE command on device 0*/
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_FLUSH_CACHE);

    /* Check status while request is in flight*/
    data = qpci_io_readb(dev, ide_bar, reg_status);
    assert_bit_set(data, BSY | DRDY);
    assert_bit_clear(data, DF | ERR | DRQ);

    qtest_qmp_eventwait(qts, "STOP");

    /* Complete the command */
    qtest_qmp_assert_success(qts, "{'execute':'cont' }");

    /* Check registers */
    data = qpci_io_readb(dev, ide_bar, reg_device);
    g_assert_cmpint(data & DEV, ==, 0);

    do {
        data = qpci_io_readb(dev, ide_bar, reg_status);
    } while (data & BSY);

    assert_bit_set(data, DRDY);
    assert_bit_clear(data, BSY | DF | ERR | DRQ);

    ide_test_quit(qts);
    free_pci_device(dev);
}

static void test_flush_nodev(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;

    qts = ide_test_start("%s", "");

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* FLUSH CACHE command on device 0*/
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_FLUSH_CACHE);

    /* Just testing that qemu doesn't crash... */

    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_flush_empty_drive(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;

    qts = ide_test_start("-device ide-cd,bus=ide.0");
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* FLUSH CACHE command on device 0 */
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_FLUSH_CACHE);

    /* Just testing that qemu doesn't crash... */

    free_pci_device(dev);
    ide_test_quit(qts);
}

typedef struct Read10CDB {
    uint8_t opcode;
    uint8_t flags;
    uint32_t lba;
    uint8_t reserved;
    uint16_t nblocks;
    uint8_t control;
    uint16_t padding;
} __attribute__((__packed__)) Read10CDB;

static void send_scsi_cdb_read10(QPCIDevice *dev, QPCIBar ide_bar,
                                 uint64_t lba, int nblocks)
{
    Read10CDB pkt = { .padding = 0 };
    int i;

    g_assert_cmpint(lba, <=, UINT32_MAX);
    g_assert_cmpint(nblocks, <=, UINT16_MAX);
    g_assert_cmpint(nblocks, >=, 0);

    /* Construct SCSI CDB packet */
    pkt.opcode = 0x28;
    pkt.lba = cpu_to_be32(lba);
    pkt.nblocks = cpu_to_be16(nblocks);

    /* Send Packet */
    for (i = 0; i < sizeof(Read10CDB)/2; i++) {
        qpci_io_writew(dev, ide_bar, reg_data,
                       le16_to_cpu(((uint16_t *)&pkt)[i]));
    }
}

static void send_scsi_cdb_read_cd(QPCIDevice *dev, QPCIBar ide_bar,
                                  uint64_t lba, int nblocks)
{
    uint8_t pkt[12] = { 0xbe, 0x08 };

    g_assert_cmpuint(lba, <=, UINT32_MAX);
    g_assert_cmpint(nblocks, >, 0);
    g_assert_cmpint(nblocks, <=, 0xffffff);
    stl_be_p(pkt + 2, lba);
    pkt[6] = nblocks >> 16;
    pkt[7] = nblocks >> 8;
    pkt[8] = nblocks;
    pkt[9] = 0xf8;
    for (int i = 0; i < sizeof(pkt); i += 2) {
        qpci_io_writew(dev, ide_bar, reg_data, lduw_le_p(pkt + i));
    }
}

static void nsleep(QTestState *qts, int64_t nsecs)
{
    const struct timespec val = { .tv_nsec = nsecs };
    nanosleep(&val, NULL);
    qtest_clock_set(qts, nsecs);
}

static uint8_t ide_wait_clear(QTestState *qts, uint8_t flag)
{
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t data;
    time_t st;

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);

    /* Wait with a 5 second timeout */
    time(&st);
    while (true) {
        data = qpci_io_readb(dev, ide_bar, reg_status);
        if (!(data & flag)) {
            free_pci_device(dev);
            return data;
        }
        if (difftime(time(NULL), st) > 5.0) {
            break;
        }
        nsleep(qts, 400);
    }
    g_assert_not_reached();
}

static void ide_wait_intr(QTestState *qts, int irq)
{
    time_t st;
    bool intr;

    time(&st);
    while (true) {
        intr = qtest_get_irq(qts, irq);
        if (intr) {
            return;
        }
        if (difftime(time(NULL), st) > 5.0) {
            break;
        }
        nsleep(qts, 400);
    }

    g_assert_not_reached();
}

static void test_pic_model_names(void)
{
    g_assert_true(qtest_has_device("i8259a"));
    g_assert_true(qtest_has_device("isa-i8259"));
}

static void test_pic_ide_special_mask(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    FILE *fh = fopen(tmp_path[0], "wb");

    g_assert_nonnull(fh);
    g_assert_cmpint(ftruncate(fileno(fh), 16 * ATAPI_BLOCK_SIZE), ==, 0);
    fclose(fh);

    qts = ide_test_start(
        "-drive if=none,file=%s,format=raw,id=hd0 "
        "-device ide-hd,drive=hd0,bus=ide.0 "
        "-device ide-cd,bus=ide.1", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    /* Initialize both PICs in edge-triggered, cascaded 8086 mode. */
    qtest_outb(qts, 0x20, 0x11);
    qtest_outb(qts, 0xa0, 0x11);
    qtest_outb(qts, 0x21, 0x08);
    qtest_outb(qts, 0xa1, 0x70);
    qtest_outb(qts, 0x21, 0x04);
    qtest_outb(qts, 0xa1, 0x02);
    qtest_outb(qts, 0x21, 0x01);
    qtest_outb(qts, 0xa1, 0x01);
    qtest_outb(qts, 0x21, 0xfb); /* Enable the cascade only. */
    qtest_outb(qts, 0xa1, 0x3f); /* Enable IRQ14 and IRQ15. */

    /* Acknowledge IRQ14 via PIC polling, leaving it in service. */
    qtest_outb(qts, 0x1f0 + reg_device, 0);
    qtest_outb(qts, 0x1f0 + reg_command, CMD_IDENTIFY);
    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    qtest_outb(qts, 0x20, 0x0c);
    g_assert_cmphex(qtest_inb(qts, 0x20), ==, 0x82);
    qtest_outb(qts, 0xa0, 0x0c);
    g_assert_cmphex(qtest_inb(qts, 0xa0), ==, 0x86);
    qtest_inb(qts, 0x1f0 + reg_status);

    /* Mask the in-service IRQ14 and queue the lower-priority IRQ15. */
    qtest_outb(qts, 0xa1, 0x7f);
    qtest_outb(qts, 0x170 + reg_device, 0);
    qtest_outb(qts, 0x170 + reg_command, CMD_PACKET_IDENTIFY);
    ide_wait_intr(qts, IDE_PRIMARY_IRQ + 1);

    qtest_outb(qts, 0xa0, 0x0a); /* Read slave IRR. */
    assert_bit_set(qtest_inb(qts, 0xa0), 0x80);
    qtest_outb(qts, 0x20, 0x0a); /* Read master IRR. */
    assert_bit_clear(qtest_inb(qts, 0x20), 0x04);

    /* OCW3 alone must release the pending request onto the cascade. */
    qtest_outb(qts, 0xa0, 0x68);
    assert_bit_set(qtest_inb(qts, 0x20), 0x04);

    /* End the master cascade service and acknowledge IRQ15. */
    qtest_outb(qts, 0x20, 0x62);
    qtest_outb(qts, 0x20, 0x0c);
    g_assert_cmphex(qtest_inb(qts, 0x20), ==, 0x82);
    qtest_outb(qts, 0xa0, 0x0c);
    g_assert_cmphex(qtest_inb(qts, 0xa0), ==, 0x87);
    qtest_inb(qts, 0x170 + reg_status);

    qtest_outb(qts, 0xa0, 0x67);
    qtest_outb(qts, 0xa0, 0x66);
    qtest_outb(qts, 0x20, 0x62);
    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_piix_channel_irq_reset(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    static const unsigned base[] = { 0x1f0, 0x170 };
    static const unsigned control[] = { 0x3f6, 0x376 };
    FILE *fh = fopen(tmp_path[0], "wb");

    g_assert_nonnull(fh);
    g_assert_cmpint(ftruncate(fileno(fh), 16 * ATAPI_BLOCK_SIZE), ==, 0);
    fclose(fh);
    qts = ide_test_start(
        "-drive if=none,file=%s,format=raw,id=hd0 "
        "-device ide-hd,drive=hd0,bus=ide.0 "
        "-device ide-cd,bus=ide.1", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    /* Both channels have an unacknowledged IDENTIFY data-ready IRQ. */
    for (unsigned i = 0; i < ARRAY_SIZE(base); i++) {
        qtest_outb(qts, base[i] + reg_device, 0);
        qtest_outb(qts, base[i] + reg_command,
                   i == 0 ? CMD_IDENTIFY : CMD_PACKET_IDENTIFY);
        ide_wait_intr(qts, IDE_PRIMARY_IRQ + i);
        assert_bit_set(qtest_inb(qts, control[i]), DRQ);
        g_assert_true(qtest_get_irq(qts, IDE_PRIMARY_IRQ + i));
    }

    /* Resetting one channel must not acknowledge the other channel. */
    for (unsigned i = 0; i < ARRAY_SIZE(base); i++) {
        int irq = IDE_PRIMARY_IRQ + i;
        int64_t deadline;

        qtest_outb(qts, control[i], IDE_CTRL_RESET);
        g_assert_false(qtest_get_irq(qts, irq));
        if (i == 0) {
            g_assert_true(qtest_get_irq(qts, IDE_PRIMARY_IRQ + 1));
        }
        qtest_clock_step(qts, 5000);
        qtest_outb(qts, control[i], 0);
        qtest_clock_step(qts, 2000000);
        deadline = g_get_monotonic_time() + 5 * G_TIME_SPAN_SECOND;
        while (qtest_inb(qts, control[i]) & BSY) {
            g_assert_cmpint(g_get_monotonic_time(), <, deadline);
        }
        g_assert_false(qtest_get_irq(qts, irq));
    }

    /* A new command can assert each interrupt, and status clears it. */
    for (unsigned i = 0; i < ARRAY_SIZE(base); i++) {
        qtest_outb(qts, base[i] + reg_device, 0);
        qtest_outb(qts, base[i] + reg_command,
                   i == 0 ? CMD_IDENTIFY : CMD_PACKET_IDENTIFY);
        ide_wait_intr(qts, IDE_PRIMARY_IRQ + i);
        assert_bit_set(qtest_inb(qts, base[i] + reg_status), DRQ);
        g_assert_false(qtest_get_irq(qts, IDE_PRIMARY_IRQ + i));
    }

    free_pci_device(dev);
    ide_test_quit(qts);
}

static void cdrom_pio_impl(int nblocks, uint16_t byte_count_limit)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    FILE *fh;
    int patt_blocks = MAX(16, nblocks);
    size_t patt_len = ATAPI_BLOCK_SIZE * patt_blocks;
    char *pattern = g_malloc(patt_len);
    size_t rxsize = ATAPI_BLOCK_SIZE * nblocks;
    uint16_t *rx = g_malloc0(rxsize);
    int i, j;
    uint8_t data;
    uint16_t limit;
    size_t ret;

    /* Prepopulate the CDROM with an interesting pattern */
    generate_pattern(pattern, patt_len, ATAPI_BLOCK_SIZE);
    fh = fopen(tmp_path[0], "wb+");
    ret = fwrite(pattern, ATAPI_BLOCK_SIZE, patt_blocks, fh);
    g_assert_cmpint(ret, ==, patt_blocks);
    fclose(fh);

    qts = ide_test_start(
            "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0,index=0 "
            "-device ide-cd,drive=sr0,bus=ide.0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    /* PACKET command on device 0 */
    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_lba_middle, byte_count_limit & 0xFF);
    qpci_io_writeb(dev, ide_bar, reg_lba_high, (byte_count_limit >> 8 & 0xFF));
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET);
    /* HP0: Check_Status_A State */
    nsleep(qts, 400);
    data = ide_wait_clear(qts, BSY);
    /* HP1: Send_Packet State */
    assert_bit_set(data, DRQ | DRDY);
    assert_bit_clear(data, ERR | DF | BSY);

    /* SCSI CDB (READ10) -- read n*2048 bytes from block 0 */
    send_scsi_cdb_read10(dev, ide_bar, 0, nblocks);

    /* Read data back: occurs in bursts of 'byte_count_limit' bytes.
     * If byte_count_limit is odd, we transfer byte_count_limit - 1 bytes.
     * We allow an odd limit only when the remaining transfer size is
     * less than byte_count_limit. However, SCSI's read10 command can only
     * request n blocks, so our request size is always even.
     * For this reason, we assume there is never a hanging byte to fetch. */
    g_assert(!(rxsize & 1));
    limit = byte_count_limit & ~1;
    for (i = 0; i < DIV_ROUND_UP(rxsize, limit); i++) {
        size_t offset = i * (limit / 2);
        size_t rem = (rxsize / 2) - offset;

        /* HP3: INTRQ_Wait */
        ide_wait_intr(qts, IDE_PRIMARY_IRQ);

        /* HP2: Check_Status_B (and clear IRQ) */
        data = ide_wait_clear(qts, BSY);
        assert_bit_set(data, DRQ | DRDY);
        assert_bit_clear(data, ERR | DF | BSY);

        /* HP4: Transfer_Data */
        for (j = 0; j < MIN((limit / 2), rem); j++) {
            rx[offset + j] = cpu_to_le16(qpci_io_readw(dev, ide_bar,
                                                       reg_data));
        }
    }

    /* Check for final completion IRQ */
    ide_wait_intr(qts, IDE_PRIMARY_IRQ);

    /* Sanity check final state */
    data = ide_wait_clear(qts, DRQ);
    assert_bit_set(data, DRDY);
    assert_bit_clear(data, DRQ | ERR | DF | BSY);

    g_assert_cmpint(memcmp(pattern, rx, rxsize), ==, 0);
    g_free(pattern);
    g_free(rx);
    test_bmdma_teardown(qts);
    free_pci_device(dev);
}

static void test_oak_identify_model(const void *opaque)
{
    const char *profile = opaque;
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t model[40];
    bool early = g_str_equal(profile, "oti-011");
    const char *expected = early ? "NEC CD-ROM DRIVE:260" :
                           g_str_equal(profile, "oti-910") ?
                           "QEMU OTI-910 CD-ROM" : "QEMU DVD-ROM";

    g_assert_true(qtest_has_device(profile));
    qts = ide_test_start("-device %s,bus=ide.0,unit=0", profile);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET_IDENTIFY);
    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    assert_bit_set(ide_wait_clear(qts, BSY), DRQ);
    for (int i = 0; i < 256; i++) {
        uint16_t word = qpci_io_readw(dev, ide_bar, reg_data);

        if (i >= 27 && i < 47) {
            model[2 * (i - 27)] = word;
            model[2 * (i - 27) + 1] = word >> 8;
        }
    }
    assert_bit_clear(ide_wait_clear(qts, BSY), DRQ | ERR);
    for (int i = 0; i < sizeof(model); i++) {
        unsigned index = early ? i : i ^ 1;

        g_assert_cmphex(model[i], ==,
                        index < strlen(expected) ? expected[index] : ' ');
    }
    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_pc_legacy_cd_model(const void *opaque)
{
    const char *profile = opaque;
    bool early = g_str_equal(profile, "oti-011");
    bool is_default = g_str_equal(profile, "default");
    bool toshiba = is_default || g_str_equal(profile, "toshiba-xm-6202b");
    const char *expected = toshiba ? "TOSHIBA CD-ROM XM-6202B" :
                           early ? "NEC CD-ROM DRIVE:260" :
                           g_str_equal(profile, "oti-910") ?
                           "QEMU OTI-910 CD-ROM" : "QEMU DVD-ROM";
    g_autofree char *machine = is_default ? g_strdup("pc") :
        g_strdup_printf("pc,ide-cd-model=%s", profile);
    QTestState *qts = qtest_initf(
        "-machine %s -nodefaults "
        "-drive if=ide,index=0,media=cdrom", machine);
    uint8_t model[40];

    qtest_outb(qts, 0x1f6, 0xe0);
    qtest_outb(qts, 0x1f7, CMD_PACKET_IDENTIFY);
    assert_bit_set(qtest_inb(qts, 0x1f7), DRQ);
    for (int i = 0; i < 256; i++) {
        uint16_t word = qtest_inw(qts, 0x1f0);

        if (i >= 27 && i < 47) {
            model[2 * (i - 27)] = word;
            model[2 * (i - 27) + 1] = word >> 8;
        }
    }
    assert_bit_clear(qtest_inb(qts, 0x1f7), BSY | DRQ | ERR);
    for (unsigned i = 0; i < sizeof(model); i++) {
        unsigned index = early ? i : i ^ 1;

        g_assert_cmphex(model[i], ==,
                        index < strlen(expected) ? expected[index] : ' ');
    }
    qtest_quit(qts);
}

static void test_xm6202b_capabilities(void)
{
    QTestState *qts = qtest_init(
        "-machine pc -nodefaults -device toshiba-xm-6202b,bus=ide.0,unit=0");
    uint16_t id[256];
    const uint8_t packet[12] = { 0x5a, 0, 0x2a, 0, 0, 0, 0, 0, 30 };
    uint8_t reply[30];

    qtest_outb(qts, 0x1f6, 0xa0);
    qtest_outb(qts, 0x1f7, CMD_PACKET_IDENTIFY);
    assert_bit_set(qtest_inb(qts, 0x1f7), DRQ);
    for (unsigned i = 0; i < ARRAY_SIZE(id); i++) {
        id[i] = qtest_inw(qts, 0x1f0);
    }
    g_assert_cmpuint(id[21], ==, 512);
    g_assert_cmphex(id[49] & 0x100, ==, 0);
    g_assert_cmphex(id[62] | id[63] | id[88], ==, 0);
    g_assert_cmphex(id[64], ==, 3);
    g_assert_cmpuint(id[68], ==, 120);

    qtest_outb(qts, 0x1f1, 3);
    qtest_outb(qts, 0x1f2, 0x0c); /* PIO mode 4 */
    qtest_outb(qts, 0x1f7, 0xef);
    assert_bit_clear(qtest_inb(qts, 0x1f7), ERR);
    qtest_outb(qts, 0x1f1, 3);
    qtest_outb(qts, 0x1f2, 0x22); /* MWDMA mode 2 */
    qtest_outb(qts, 0x1f7, 0xef);
    assert_bit_set(qtest_inb(qts, 0x1f7), ERR);
    qtest_outb(qts, 0x1f1, 1);
    qtest_outb(qts, 0x1f7, CMD_PACKET);
    assert_bit_set(qtest_inb(qts, 0x1f7), ERR);

    qtest_outb(qts, 0x1f1, 0);
    qtest_outb(qts, 0x1f4, sizeof(reply));
    qtest_outb(qts, 0x1f5, 0);
    qtest_outb(qts, 0x1f7, CMD_PACKET);
    assert_bit_set(qtest_inb(qts, 0x1f7), DRQ);
    for (unsigned i = 0; i < sizeof(packet); i += 2) {
        qtest_outw(qts, 0x1f0, packet[i] | (packet[i + 1] << 8));
    }
    assert_bit_set(qtest_inb(qts, 0x1f7), DRQ);
    for (unsigned i = 0; i < sizeof(reply); i += 2) {
        uint16_t word = qtest_inw(qts, 0x1f0);
        reply[i] = word;
        reply[i + 1] = word >> 8;
    }
    assert_bit_clear(qtest_inb(qts, 0x1f7), BSY | DRQ | ERR);
    g_assert_cmphex(reply[10], ==, 0); /* No DVD media support. */
    g_assert_cmpuint((reply[16] << 8) | reply[17], ==, 4800);
    g_assert_cmpuint((reply[20] << 8) | reply[21], ==, 256);
    qtest_quit(qts);
}

static void test_oti910_profile(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t packet[12] = { 0x46, 0, 0, 0, 0, 0, 0, 0, 32 };
    uint8_t reply[16];
    FILE *fh = fopen(tmp_path[0], "wb");

    g_assert_nonnull(fh);
    g_assert_cmpint(ftruncate(fileno(fh), 16 * ATAPI_BLOCK_SIZE), ==, 0);
    fclose(fh);
    g_assert_true(qtest_has_device("oti-910"));
    qts = ide_test_start(
        "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0 "
        "-device oti-910,drive=sr0,bus=ide.0,unit=0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    qpci_io_writeb(dev, ide_bar, reg_device, 0);
    qpci_io_writeb(dev, ide_bar, reg_feature, 0);
    qpci_io_writeb(dev, ide_bar, reg_lba_middle, 32);
    qpci_io_writeb(dev, ide_bar, reg_lba_high, 0);
    qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET);
    assert_bit_set(ide_wait_clear(qts, BSY), DRQ);
    for (int i = 0; i < sizeof(packet); i += 2) {
        qpci_io_writew(dev, ide_bar, reg_data,
                       packet[i] | ((uint16_t)packet[i + 1] << 8));
    }

    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    assert_bit_set(ide_wait_clear(qts, BSY), DRQ);
    g_assert_cmpuint(qpci_io_readb(dev, ide_bar, reg_lba_middle), ==, 16);
    for (int i = 0; i < sizeof(reply); i += 2) {
        uint16_t word = qpci_io_readw(dev, ide_bar, reg_data);

        reply[i] = word;
        reply[i + 1] = word >> 8;
    }
    ide_wait_intr(qts, IDE_PRIMARY_IRQ);
    assert_bit_clear(ide_wait_clear(qts, BSY), DRQ | ERR);
    g_assert_cmphex(reply[3], ==, 12); /* Response length minus four. */
    g_assert_cmphex(reply[7], ==, 8);  /* Current CD-ROM profile. */
    g_assert_cmphex(reply[11], ==, 4); /* One profile descriptor. */
    g_assert_cmphex(reply[13], ==, 8); /* CD-ROM, no DVD descriptor. */
    g_assert_cmphex(reply[14], ==, 1);

    free_pci_device(dev);
    ide_test_quit(qts);
}

static void test_cdrom_subchannel_header(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t packet[12] = { 0x42, 0, 0, 1, 0, 0, 0, 0, 4 };
    uint8_t status;
    FILE *fh = fopen(tmp_path[0], "wb");

    g_assert_nonnull(fh);
    g_assert_cmpint(ftruncate(fileno(fh), 16 * ATAPI_BLOCK_SIZE), ==, 0);
    fclose(fh);
    qts = ide_test_start(
        "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0,index=0 "
        "-device ide-cd,drive=sr0,bus=ide.0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    for (int i = 0; i < 3; i++) {
        packet[2] = i == 2 ? 0x40 : 0;
        packet[8] = i == 1 ? 0 : 4;
        qpci_io_writeb(dev, ide_bar, reg_device, 0);
        qpci_io_writeb(dev, ide_bar, reg_feature, 0);
        qpci_io_writeb(dev, ide_bar, reg_lba_middle, 4);
        qpci_io_writeb(dev, ide_bar, reg_lba_high, 0);
        qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET);
        status = ide_wait_clear(qts, BSY);
        assert_bit_set(status, DRQ);
        for (int j = 0; j < sizeof(packet); j += 2) {
            qpci_io_writew(dev, ide_bar, reg_data,
                           packet[j] | ((uint16_t)packet[j + 1] << 8));
        }
        ide_wait_intr(qts, IDE_PRIMARY_IRQ);
        status = ide_wait_clear(qts, BSY);
        if (i == 0) {
            assert_bit_set(status, DRQ);
            assert_bit_clear(status, ERR);
            g_assert_cmphex(qpci_io_readw(dev, ide_bar, reg_data), ==, 0);
            g_assert_cmphex(qpci_io_readw(dev, ide_bar, reg_data), ==, 0);
            ide_wait_intr(qts, IDE_PRIMARY_IRQ);
            status = ide_wait_clear(qts, BSY);
        }
        assert_bit_clear(status, DRQ | BSY);
        if (i == 2) {
            assert_bit_set(status, ERR);
            g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_error) >> 4,
                            ==, 5);
        } else {
            assert_bit_clear(status, ERR);
        }
    }
    test_bmdma_teardown(qts);
    free_pci_device(dev);
}

static void test_cdrom_invalid_bcl(void)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    const uint8_t inquiry[12] = { 0x12, 0, 0, 0, 36 };
    FILE *fh = fopen(tmp_path[0], "wb");

    g_assert_nonnull(fh);
    g_assert_cmpint(ftruncate(fileno(fh), 16 * ATAPI_BLOCK_SIZE), ==, 0);
    fclose(fh);
    qts = ide_test_start(
        "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0,index=0 "
        "-device ide-cd,drive=sr0,bus=ide.0", tmp_path[0]);
    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    qtest_irq_intercept_in(qts, "ioapic");

    /* Exercise both sector data and buffered packet replies. */
    for (int cmd = 0; cmd < 2; cmd++) {
        for (int limit = 0; limit <= 1; limit++) {
            uint8_t status;

            qpci_io_writeb(dev, ide_bar, reg_device, 0);
            qpci_io_writeb(dev, ide_bar, reg_feature, 0);
            qpci_io_writeb(dev, ide_bar, reg_lba_middle, limit);
            qpci_io_writeb(dev, ide_bar, reg_lba_high, 0);
            qpci_io_writeb(dev, ide_bar, reg_command, CMD_PACKET);
            status = ide_wait_clear(qts, BSY);
            assert_bit_set(status, DRQ);
            if (cmd == 0) {
                send_scsi_cdb_read10(dev, ide_bar, 0, 1);
            } else {
                for (int j = 0; j < sizeof(inquiry); j += 2) {
                    qpci_io_writew(dev, ide_bar, reg_data,
                                   inquiry[j] | ((uint16_t)inquiry[j + 1] << 8));
                }
            }
            ide_wait_intr(qts, IDE_PRIMARY_IRQ);
            status = ide_wait_clear(qts, BSY);
            assert_bit_set(status, ERR);
            assert_bit_clear(status, BSY | DRQ);
            assert_bit_set(qpci_io_readb(dev, ide_bar, reg_error), ABRT);
            g_assert_cmphex(qpci_io_readb(dev, ide_bar, reg_nsectors) & 7,
                            ==, 3);
        }
    }

    test_bmdma_teardown(qts);
    free_pci_device(dev);
}

static void test_cdrom_pio(void)
{
    cdrom_pio_impl(1, BYTE_COUNT_LIMIT);
}

static void test_cdrom_pio_large(void)
{
    /* Test a few loops of the PIO DRQ mechanism. */
    cdrom_pio_impl(BYTE_COUNT_LIMIT * 4 / ATAPI_BLOCK_SIZE,
                   BYTE_COUNT_LIMIT);
}


static void test_cdrom_pio_linux_limit(void)
{
    /* Legacy Linux ide-cd uses a 32 KiB packet byte-count limit. */
    cdrom_pio_impl(40, 32768);
}

static void test_cdrom_dma(void)
{
    QTestState *qts;
    static const size_t len = ATAPI_BLOCK_SIZE;
    size_t ret;
    char *pattern = g_malloc(ATAPI_BLOCK_SIZE * 16);
    char *rx = g_malloc0(len);
    uintptr_t guest_buf;
    PrdtEntry prdt[1];
    FILE *fh;

    qts = ide_test_start(
            "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0,index=0 "
            "-device ide-cd,drive=sr0,bus=ide.0", tmp_path[0]);
    qtest_irq_intercept_in(qts, "ioapic");

    guest_buf = guest_alloc(&guest_malloc, len);
    prdt[0].addr = cpu_to_le32(guest_buf);
    prdt[0].size = cpu_to_le32(len | PRDT_EOT);

    generate_pattern(pattern, ATAPI_BLOCK_SIZE * 16, ATAPI_BLOCK_SIZE);
    fh = fopen(tmp_path[0], "wb+");
    ret = fwrite(pattern, ATAPI_BLOCK_SIZE, 16, fh);
    g_assert_cmpint(ret, ==, 16);
    fclose(fh);

    send_dma_request(qts, CMD_PACKET, 0, 1, prdt, 1, send_scsi_cdb_read10);

    /* Read back data from guest memory into local qtest memory */
    qtest_memread(qts, guest_buf, rx, len);
    g_assert_cmpint(memcmp(pattern, rx, len), ==, 0);

    g_free(pattern);
    g_free(rx);
    test_bmdma_teardown(qts);
}

/* Both reads cross the 128 KiB staging-buffer boundary. */
static void test_cdrom_dma_batched(gconstpointer opaque)
{
    bool raw = GPOINTER_TO_INT(opaque);
    const int nblocks = 70;
    const int sector_size = raw ? 2352 : ATAPI_BLOCK_SIZE;
    const size_t len = nblocks * sector_size;
    const size_t payload_len = nblocks * ATAPI_BLOCK_SIZE;
    g_autofree uint8_t *pattern = g_malloc(payload_len);
    g_autofree uint8_t *rx = g_malloc0(len);
    const size_t chunk = 4096;
    const size_t entries = DIV_ROUND_UP(len, chunk);
    g_autofree PrdtEntry *prdt = g_new0(PrdtEntry, entries);
    g_autofree uintptr_t *buffers = g_new(uintptr_t, entries);
    FILE *fh = fopen(tmp_path[0], "wb");
    QTestState *qts;

    g_assert_nonnull(fh);
    generate_pattern((char *)pattern, payload_len, ATAPI_BLOCK_SIZE);
    g_assert_cmpuint(fwrite(pattern, 1, payload_len, fh), ==, payload_len);
    fclose(fh);
    qts = ide_test_start(
        "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0,index=0 "
        "-device ide-cd,drive=sr0,bus=ide.0", tmp_path[0]);
    qtest_irq_intercept_in(qts, "ioapic");

    for (size_t i = 0; i < entries; i++) {
        size_t bytes = MIN(chunk, len - i * chunk);

        buffers[i] = guest_alloc(&guest_malloc, chunk);
        prdt[i].addr = cpu_to_le32(buffers[i]);
        prdt[i].size = cpu_to_le32(bytes |
                                  (i == entries - 1 ? PRDT_EOT : 0));
    }
    g_assert_cmphex(send_dma_request(qts, CMD_PACKET, 0, nblocks, prdt,
                                    entries, raw ? send_scsi_cdb_read_cd :
                                                   send_scsi_cdb_read10),
                    ==, BM_STS_INTR);
    for (size_t i = 0; i < entries; i++) {
        qtest_memread(qts, buffers[i], rx + i * chunk,
                      MIN(chunk, len - i * chunk));
        guest_free(&guest_malloc, buffers[i]);
    }
    for (int i = 0; i < nblocks; i++) {
        const uint8_t *sector = rx + i * sector_size;

        if (raw) {
            g_assert_cmphex(sector[0], ==, 0);
            g_assert_cmphex(sector[1], ==, 0xff);
            g_assert_cmphex(sector[11], ==, 0);
            g_assert_cmphex(sector[15], ==, 1);
            sector += 16;
        }
        g_assert_cmpmem(sector, ATAPI_BLOCK_SIZE,
                        pattern + i * ATAPI_BLOCK_SIZE, ATAPI_BLOCK_SIZE);
    }
    test_bmdma_teardown(qts);
}

static void test_cdrom_dma_fault(bool no_busmaster)
{
    QTestState *qts;
    QPCIDevice *dev;
    QPCIBar bmdma_bar, ide_bar;
    uint8_t status;
    char pattern[ATAPI_BLOCK_SIZE] = { 0 };
    FILE *fh;
    uintptr_t guest_buf;
    PrdtEntry prdt[1];

    fh = fopen(tmp_path[0], "wb+");
    g_assert_nonnull(fh);
    g_assert_cmpuint(fwrite(pattern, 1, sizeof(pattern), fh),
                     ==, sizeof(pattern));
    fclose(fh);

    qts = ide_test_start(
        "-drive if=none,file=%s,media=cdrom,format=raw,id=sr0,index=0 "
        "-device ide-cd,drive=sr0,bus=ide.0", tmp_path[0]);
    qtest_irq_intercept_in(qts, "ioapic");

    if (no_busmaster) {
        guest_buf = guest_alloc(&guest_malloc, ATAPI_BLOCK_SIZE);
        prdt[0].addr = cpu_to_le32(guest_buf);
    } else {
        /* PC guest RAM is below this address; DMA must report a fault
         * instead of pretending the ATAPI data was transferred. */
        prdt[0].addr = cpu_to_le32(0xe0000000);
    }
    prdt[0].size = cpu_to_le32(ATAPI_BLOCK_SIZE | PRDT_EOT);

    dev = get_pci_device(qts, &bmdma_bar, &ide_bar);
    status = send_dma_request_dev(qts, dev, bmdma_bar, ide_bar,
                                  CMD_PACKET | (no_busmaster ? CMDF_NO_BM : 0),
                                  0, 1,
                                  prdt, ARRAY_SIZE(prdt),
                                  send_scsi_cdb_read10);
    g_assert_cmphex(status, ==, BM_STS_ERROR | BM_STS_INTR);
    assert_bit_set(qpci_io_readb(dev, ide_bar, reg_status), ERR);

    free_pci_device(dev);
    test_bmdma_teardown(qts);
}

static void test_cdrom_dma_no_busmaster(void)
{
    test_cdrom_dma_fault(true);
}

static void test_cdrom_dma_bad_buffer(void)
{
    test_cdrom_dma_fault(false);
}

static void test_piix4_timing_registers(void)
{
    QTestState *qts = qtest_init("-M pc,x-south-bridge=piix4-isa "
                                "-global piix4-ide.strict-timing-regs=on");
    QPCIBus *bus = qpci_new_pc(qts, NULL);
    QPCIDevice *dev = qpci_device_find(bus, QPCI_DEVFN(IDE_PCI_DEV,
                                                     IDE_PCI_FUNC));

    g_assert_nonnull(dev);
    g_assert_cmphex(qpci_config_readw(dev, PCI_VENDOR_ID), ==,
                    PCI_VENDOR_ID_INTEL);
    g_assert_cmphex(qpci_config_readw(dev, PCI_DEVICE_ID), ==,
                    PCI_DEVICE_ID_INTEL_82371AB);

    for (unsigned reg = 0x40; reg < 0x4c; reg += 4) {
        g_assert_cmphex(qpci_config_readl(dev, reg), ==, 0);
        qpci_config_writel(dev, reg, UINT32_MAX);
    }

    g_assert_cmphex(qpci_config_readl(dev, 0x40), ==, 0xf3fff3ff);
    g_assert_cmphex(qpci_config_readl(dev, 0x44), ==, 0x000000ff);
    g_assert_cmphex(qpci_config_readl(dev, 0x48), ==, 0x3333000f);

    /* Per-drive UDMA control and timings are independently writable. */
    qpci_config_writeb(dev, 0x48, 0x05);
    qpci_config_writew(dev, 0x4a, 0x1201);
    g_assert_cmphex(qpci_config_readl(dev, 0x48), ==, 0x12010005);

    qtest_system_reset(qts);
    for (unsigned reg = 0x40; reg < 0x4c; reg += 4) {
        g_assert_cmphex(qpci_config_readl(dev, reg), ==, 0);
    }

    free_pci_device(dev);
    qpci_free_pc(bus);
    qtest_quit(qts);
}

static void assert_single_legacy_drive_pair(const char *tree)
{
    g_autoptr(GRegex) hd = g_regex_new("dev: ide-hd,", 0, 0, NULL);
    g_autoptr(GRegex) cd = g_regex_new("dev: ide-cd,", 0, 0, NULL);
    g_auto(GStrv) hd_parts = g_regex_split(hd, tree, 0);
    g_auto(GStrv) cd_parts = g_regex_split(cd, tree, 0);

    g_assert_cmpuint(g_strv_length(hd_parts), ==, 2);
    g_assert_cmpuint(g_strv_length(cd_parts), ==, 2);
}

static void test_piix4_onboard_drive_pair(void)
{
    g_autofree char *disk = g_shell_quote(tmp_path[0]);
    g_autofree char *cd = g_shell_quote(tmp_path[1]);
    QTestState *qts = qtest_initf("-M pc,x-south-bridge=piix4-isa "
                                  "-nodefaults -snapshot -hda %s -cdrom %s",
                                  disk, cd);
    g_autofree char *tree = qtest_hmp(qts, "info qtree");

    assert_single_legacy_drive_pair(tree);
    qtest_quit(qts);
}

static void test_legacy_drive_controller(gconstpointer opaque)
{
    const char *model = opaque;
    const bool sata = !strcmp(model, "ich9-ahci");
    g_autofree char *disk = g_shell_quote(tmp_path[0]);
    g_autofree char *cd = g_shell_quote(tmp_path[1]);
    QTestState *qts;
    g_autofree char *tree = NULL;

    /*
     * The machine has no default SATA controller. Shortcuts must survive
     * board initialization and attach only to the explicit controller.
     * Put the selector last to check option-order independence.
     */
    qts = qtest_initf("-M q35,sata=off -nodefaults -snapshot "
                      "-cdrom %s -hda %s -device %s,id=alt "
                      "-legacy-drive-controller alt", cd, disk, model);
    tree = qtest_hmp(qts, "info qtree");
    assert_single_legacy_drive_pair(tree);
    g_assert_true(g_regex_match_simple(
        "bus: alt\\.0\\s+type IDE\\s+dev: ide-hd,", tree, 0, 0));
    g_assert_true(g_regex_match_simple(
        sata ? "bus: alt\\.2\\s+type IDE\\s+dev: ide-cd,"
             : "bus: alt\\.1\\s+type IDE\\s+dev: ide-cd,",
        tree, 0, 0));
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    const char *base;
    int i;
    int fd;
    int ret;

    /*
     * "base" stores the starting point where we create temporary files.
     *
     * On Windows, this is set to the relative path of current working
     * directory, because the absolute path causes the blkdebug filename
     * parser fail to parse "blkdebug:path/to/config:path/to/image".
     */
#ifndef _WIN32
    base = g_get_tmp_dir();
#else
    base = ".";
#endif

    /* Create temporary blkdebug instructions */
    debug_path = g_strdup_printf("%s/qtest-blkdebug.XXXXXX", base);
    fd = g_mkstemp(debug_path);
    g_assert(fd >= 0);
    close(fd);

    /* Create a temporary raw image */
    for (i = 0; i < 2; ++i) {
        tmp_path[i] = g_strdup_printf("%s/qtest.XXXXXX", base);
        fd = g_mkstemp(tmp_path[i]);
        g_assert(fd >= 0);
        ret = ftruncate(fd, TEST_IMAGE_SIZE);
        g_assert(ret == 0);
        close(fd);
    }

    /* Run the tests */
    g_test_init(&argc, &argv, NULL);

    qtest_add_func("/ide/read_native", test_specify);

    qtest_add_func("/ide/identify", test_identify);
    for (unsigned i = 0; i < ARRAY_SIZE(ata_hd_identities); i++) {
        const AtaHdIdentity *profile = &ata_hd_identities[i];
        g_autofree char *name = g_strdup_printf("/ide/hdd-identity/%s/%u",
                                                profile->type, i);

        qtest_add_data_func(name, profile, test_ata_hd_identity);
        if (!profile->options[0] && qtest_has_machine("pc")) {
            g_autofree char *legacy = g_strdup_printf(
                "/ide/legacy-model/%s", profile->type);
            qtest_add_data_func(legacy, profile, test_pc_legacy_hd_model);
        }
    }
    if (qtest_has_machine("q35")) {
        if (qtest_has_device("piix4-ide")) {
            qtest_add_data_func("/ide/legacy-controller/piix4",
                                "piix4-ide", test_legacy_drive_controller);
        }
        if (qtest_has_device("ich9-ahci")) {
            qtest_add_data_func("/ide/legacy-controller/ahci",
                                "ich9-ahci", test_legacy_drive_controller);
        }
    }
    qtest_add_func("/ide/piix/bmdma-access-width",
                   test_piix_bmdma_access_width);
    qtest_add_func("/ide/piix/channel-irq-reset", test_piix_channel_irq_reset);
    if (qtest_has_machine("pc") && qtest_has_device("piix4-ide") &&
        qtest_has_device("piix4-isa")) {
        qtest_add_func("/ide/piix4/timing-registers",
                       test_piix4_timing_registers);
        qtest_add_func("/ide/piix4/onboard-drive-pair",
                       test_piix4_onboard_drive_pair);
    }
    qtest_add_func("/ide/pic/model-names", test_pic_model_names);
    qtest_add_func("/ide/pic/special-mask", test_pic_ide_special_mask);
    qtest_add_func("/ide/ata-atapi-command-boundary",
                   test_ata_atapi_command_boundary);

    qtest_add_func("/ide/diagnostic", test_diagnostic);

    qtest_add_func("/ide/bmdma/simple_rw", test_bmdma_simple_rw);
    qtest_add_func("/ide/bmdma/trim", test_bmdma_trim);
    qtest_add_func("/ide/bmdma/trim_split_descriptor",
                   test_bmdma_trim_split_descriptor);
    qtest_add_func("/ide/bmdma/trim_reset", test_bmdma_trim_reset);
    qtest_add_func("/ide/bmdma/various_prdts", test_bmdma_various_prdts);
    qtest_add_func("/ide/bmdma/no_busmaster", test_bmdma_no_busmaster);

    qtest_add_func("/ide/flush", test_flush);
    qtest_add_func("/ide/flush/nodev", test_flush_nodev);
    qtest_add_func("/ide/flush/empty_drive", test_flush_empty_drive);
    qtest_add_func("/ide/flush/retry_pci", test_pci_retry_flush);

    if (qtest_has_machine("pc")) {
        qtest_add_data_func("/ide/legacy-model/default-cd", "default",
                            test_pc_legacy_cd_model);
        qtest_add_data_func("/ide/legacy-model/toshiba-xm-6202b",
                            "toshiba-xm-6202b", test_pc_legacy_cd_model);
        qtest_add_func("/ide/toshiba-xm-6202b/capabilities",
                       test_xm6202b_capabilities);
        qtest_add_data_func("/ide/legacy-model/ide-cd", "ide-cd",
                            test_pc_legacy_cd_model);
        qtest_add_data_func("/ide/legacy-model/oti-910", "oti-910",
                            test_pc_legacy_cd_model);
        qtest_add_data_func("/ide/legacy-model/oti-011", "oti-011",
                            test_pc_legacy_cd_model);
    }
    qtest_add_func("/ide/oti-910/profile", test_oti910_profile);
    qtest_add_data_func("/ide/oti-011/identify", "oti-011",
                        test_oak_identify_model);
    qtest_add_data_func("/ide/oti-910/identify", "oti-910",
                        test_oak_identify_model);
    qtest_add_data_func("/ide/cdrom/identify-model", "ide-cd",
                        test_oak_identify_model);
    qtest_add_func("/ide/cdrom/subchannel-header", test_cdrom_subchannel_header);
    qtest_add_func("/ide/cdrom/invalid-bcl", test_cdrom_invalid_bcl);
    qtest_add_func("/ide/cdrom/pio", test_cdrom_pio);
    qtest_add_func("/ide/cdrom/pio_large", test_cdrom_pio_large);
    qtest_add_func("/ide/cdrom/pio-linux-limit", test_cdrom_pio_linux_limit);
    qtest_add_func("/ide/cdrom/dma", test_cdrom_dma);
    qtest_add_data_func("/ide/cdrom/dma-batched-cooked", GINT_TO_POINTER(0),
                        test_cdrom_dma_batched);
    qtest_add_data_func("/ide/cdrom/dma-batched-raw", GINT_TO_POINTER(1),
                        test_cdrom_dma_batched);
    qtest_add_func("/ide/cdrom/dma_no_busmaster",
                   test_cdrom_dma_no_busmaster);
    qtest_add_func("/ide/cdrom/dma_bad_buffer",
                   test_cdrom_dma_bad_buffer);

    ret = g_test_run();

    /* Cleanup */
    for (i = 0; i < 2; ++i) {
        unlink(tmp_path[i]);
        g_free(tmp_path[i]);
    }
    unlink(debug_path);
    g_free(debug_path);

    return ret;
}
