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

static QDict *find_pci_device(QList *buses, const char *qdev_id);

static void pci_multihead(void)
{
    QTestState *qts;
    QDict *resp;
    QList *buses;

    qts = qtest_init("-vga none -device VGA,id=video0"
                     " -device secondary-vga,id=video1");

    /* A second host window is not enough: the guest must enumerate
     * two distinct PCI display adapters. */
    resp = qtest_qmp(qts, "{'execute': 'query-pci'}");
    g_assert(qdict_haskey(resp, "return"));
    buses = qdict_get_qlist(resp, "return");
    g_assert_nonnull(find_pci_device(buses, "video0"));
    g_assert_nonnull(find_pci_device(buses, "video1"));
    qobject_unref(resp);
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

static uint8_t vga_seq_read(QTestState *qts, uint8_t index)
{
    qtest_outb(qts, VGA_SEQ_I, index);
    return qtest_inb(qts, VGA_SEQ_D);
}

static uint8_t vga_crtc_read(QTestState *qts, uint8_t index)
{
    qtest_outb(qts, VGA_CRT_IC, index);
    return qtest_inb(qts, VGA_CRT_DC);
}

static void vga_gfx_write(QTestState *qts, uint8_t index, uint8_t value)
{
    qtest_outb(qts, VGA_GFX_I, index);
    qtest_outb(qts, VGA_GFX_D, value);
}

static uint8_t vga_gfx_read(QTestState *qts, uint8_t index)
{
    qtest_outb(qts, VGA_GFX_I, index);
    return qtest_inb(qts, VGA_GFX_D);
}

static void test_isa_cirrus_profile_for(const char *model, uint8_t chip_id)
{
    QTestState *qts = qtest_initf("-vga none -device %s", model);

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);

    g_assert_cmphex(vga_crtc_read(qts, 0x27), ==, chip_id);
    g_assert_cmphex(vga_seq_read(qts, 0x17), ==, 0x38);
    g_assert_cmphex(vga_seq_read(qts, 0x0f) & 0x18, ==, 0x18);

    vga_gfx_write(qts, 0x2a, 0x3f);
    vga_gfx_write(qts, 0x2e, 0x3f);
    g_assert_cmphex(vga_gfx_read(qts, 0x2a), ==, 0x1f);
    g_assert_cmphex(vga_gfx_read(qts, 0x2e), ==, 0x1f);

    /* Later GR33 mode extensions are not implemented by GD5426/5428. */
    vga_gfx_write(qts, 0x33, 0x07);
    g_assert_cmphex(vga_gfx_read(qts, 0x33), ==, 0xff);

    /*
     * SR17[2] enables BitBLT MMIO on later Cirrus chips, but the
     * CL-GD5426/5428 predate that capability.  Keep the B8000 aperture
     * unmapped even if software sets the otherwise writable bit.
     */
    vga_gfx_write(qts, 0x00, 0x5a);
    vga_seq_write(qts, 0x07, 0x01);
    vga_seq_write(qts, 0x17, 0x04);
    g_assert_cmphex(qtest_readb(qts, VGA_LEGACY_MEM_BASE + 0x18000),
                    ==, 0xff);

    qtest_quit(qts);
}

static void test_isa_cirrus_profile(void)
{
    test_isa_cirrus_profile_for("cirrus-vga-generic-isa", 0x98);
}

static void test_isa_cirrus_gd5428_profile(void)
{
    test_isa_cirrus_profile_for("gd5428", 0x98);
}

static void test_isa_cirrus_gd5426_profile(void)
{
    test_isa_cirrus_profile_for("gd5426", 0x90);
}

static void test_isa_cirrus_gd5422_profile(void)
{
    QTestState *qts = qtest_init("-vga none -device gd5422");

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);

    g_assert_cmphex(vga_crtc_read(qts, 0x27), ==, 0x8c);
    g_assert_cmphex(vga_seq_read(qts, 0x17), ==, 0x38);
    g_assert_cmphex(vga_seq_read(qts, 0x0f) & 0x18, ==, 0x10);

    /* GD5422 has no BitBLT engine: a start request cannot leave it busy. */
    vga_gfx_write(qts, 0x31, 0x02);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x03, ==, 0);

    qtest_quit(qts);
}

static void test_vlb_cirrus_decoder(gconstpointer data)
{
    uint32_t base = GPOINTER_TO_UINT(data);
    QTestState *qts = qtest_initf(
        "-m 128 -vga none -device gd5430-vlb,lfb-base=0x%x", base);

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);

    g_assert_cmphex(vga_crtc_read(qts, 0x27), ==, 0xa0);
    g_assert_cmphex(vga_seq_read(qts, 0x17) & 0x38, ==, 0x10);

    /* At 64 MiB, disabled decoding must expose the underlying RAM. */
    if (base == 0x04000000U) {
        qtest_writeb(qts, base + 0x1234, 0x39);
    }

    /* SR07[7:4] enables the VLB window even when the low nibble is 0. */
    vga_seq_write(qts, 0x07, 0x10);
    qtest_writeb(qts, base + 0x1234, 0x56);
    g_assert_cmphex(qtest_readb(qts, base + 0x1234), ==, 0x56);
    /* The 4 MiB VLB window wraps around the GD5430's 2 MiB VRAM. */
    g_assert_cmphex(qtest_readb(qts, base + 0x200000 + 0x1234), ==, 0x56);

    vga_seq_write(qts, 0x07, 0x00);
    if (base == 0x04000000U) {
        g_assert_cmphex(qtest_readb(qts, base + 0x1234), ==, 0x39);
    }
    vga_seq_write(qts, 0x07, 0x80);
    g_assert_cmphex(qtest_readb(qts, base + 0x1234), ==, 0x56);

    qtest_quit(qts);
}

static void test_gd5430_vlb_1mb(void)
{
    const uint32_t base = 0x04000000U;
    QTestState *qts = qtest_init("-m 128 -vga none "
                                  "-device gd5430-vlb,vgamem_mb=1");

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);
    g_assert_cmphex(vga_seq_read(qts, 0x15), ==, 2);
    g_assert_cmphex(vga_seq_read(qts, 0x0f) & 0x18, ==, 0x10);
    vga_seq_write(qts, 0x07, 0x10);
    qtest_writeb(qts, base + 0x1234, 0x56);
    g_assert_cmphex(qtest_readb(qts, base + 0x101234), ==, 0x56);
    g_assert_cmphex(qtest_readb(qts, base + 0x301234), ==, 0x56);
    qtest_quit(qts);
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

static void test_cirrus_gray_palette(void)
{
    QTestState *qts = qtest_init("-vga none -device cirrus-vga-generic");

    /* The mask must not alter the DAC RGB values or hidden DAC register. */
    qtest_inb(qts, VGA_PEL_IW);
    qtest_outb(qts, VGA_PEL_MSK, 0x0f);
    for (int i = 0; i < 4; i++) {
        g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0x0f);
    }
    qtest_outb(qts, VGA_PEL_MSK, 0x00); /* hidden DAC write */
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0x0f);
    qtest_inb(qts, VGA_PEL_IW);

    qtest_outb(qts, VGA_PEL_IW, 0x37);
    for (int i = 0; i < 3; i++) {
        qtest_outb(qts, VGA_PEL_D, 0x2a);
    }
    qtest_outb(qts, VGA_PEL_IR, 0x37);
    for (int i = 0; i < 3; i++) {
        g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0x2a);
    }

    qtest_outb(qts, VGA_PEL_MSK, 0xff);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0xff);
    qtest_quit(qts);
}

static void cirrus_dac_unlock(QTestState *qts, uint8_t mask)
{
    for (int i = 0; i < 4; i++) {
        g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, mask);
    }
}

static void test_gd5446_dac_sequence(void)
{
    static const uint16_t ports[] = {
        VGA_PEL_IR, VGA_PEL_IW, VGA_PEL_D,
    };
    QTestState *qts = qtest_init("-M pc -vga none -device gd5446-pci");

    /* The reset state must not require a dummy address-port read. */
    cirrus_dac_unlock(qts, 0xff);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0);
    qtest_outb(qts, VGA_PEL_MSK, 0x5a);
    cirrus_dac_unlock(qts, 0x5a);
    qtest_outb(qts, VGA_PEL_MSK, 0xc1);
    cirrus_dac_unlock(qts, 0x5a);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0xc1);

    /* Both directions of palette I/O must cancel a pending HDR access. */
    for (int i = 0; i < ARRAY_SIZE(ports); i++) {
        for (int write = 0; write < 2; write++) {
            qtest_outb(qts, VGA_PEL_IW, 0);
            cirrus_dac_unlock(qts, 0x5a);
            if (write) {
                qtest_outb(qts, ports[i], 0);
            } else {
                qtest_inb(qts, ports[i]);
            }
            qtest_outb(qts, VGA_PEL_MSK, 0xa5);
            cirrus_dac_unlock(qts, 0xa5);
            g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0xc1);
            qtest_outb(qts, VGA_PEL_MSK, 0x5a);
        }
    }

    /* An ordinary mask write also terminates a partial unlock. */
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0x5a);
    qtest_outb(qts, VGA_PEL_MSK, 0xff);
    cirrus_dac_unlock(qts, 0xff);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0xc1);

    /* The separate cursor DAC palette must not overwrite the normal LUT. */
    vga_seq_write(qts, 0x06, 0x12);
    vga_seq_write(qts, 0x12, 0);
    qtest_outb(qts, VGA_PEL_IW, 0x0f);
    qtest_outb(qts, VGA_PEL_D, 0x11);
    qtest_outb(qts, VGA_PEL_D, 0x22);
    qtest_outb(qts, VGA_PEL_D, 0x33);
    vga_seq_write(qts, 0x12, 2);
    qtest_outb(qts, VGA_PEL_IW, 0xff);
    qtest_outb(qts, VGA_PEL_D, 0x3f);
    qtest_outb(qts, VGA_PEL_D, 0);
    qtest_outb(qts, VGA_PEL_D, 0x15);
    qtest_outb(qts, VGA_PEL_IR, 0x0f);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0x3f);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0x15);
    vga_seq_write(qts, 0x12, 0);
    qtest_outb(qts, VGA_PEL_IR, 0x0f);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0x11);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0x22);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_D), ==, 0x33);

    qtest_system_reset(qts);
    cirrus_dac_unlock(qts, 0xff);
    g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0);
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

static void test_gd5430_default_rom(void)
{
    const uint32_t rom_base = 0xe0000000;
    QTestState *qts = qtest_init("-M pc -nodefaults -vga none "
                                "-device gd5430-pci,addr=4");
    uint32_t rom_mask;
    uint16_t pcir;
    unsigned int size;
    uint8_t checksum = 0;
    g_autofree uint8_t *rom = NULL;

    /* A default option ROM must expose a PCI expansion ROM BAR. */
    qtest_outl(qts, 0xcf8, 0x80002030);
    qtest_outl(qts, 0xcfc, 0xfffffffe);
    rom_mask = qtest_inl(qts, 0xcfc) & 0xfffff800;
    g_assert_cmphex(rom_mask, !=, 0);
    g_assert_cmphex(rom_mask, !=, 0xfffff800);
    qtest_outl(qts, 0xcfc, rom_base | 1);
    qtest_outl(qts, 0xcf8, 0x80002004);
    qtest_outw(qts, 0xcfc, 0x0002);

    g_assert_cmphex(qtest_readw(qts, rom_base), ==, 0xaa55);
    size = qtest_readb(qts, rom_base + 2) * 512U;
    pcir = qtest_readw(qts, rom_base + 0x18);
    g_assert_cmpuint(size, >, 0);
    g_assert_cmpuint(size, <=, (uint32_t)(~rom_mask + 1));
    g_assert_cmpuint(pcir + 8U, <=, size);
    rom = g_malloc(size);
    qtest_memread(qts, rom_base, rom, size);
    g_assert_cmpmem(rom + pcir, 4, "PCIR", 4);
    g_assert_cmphex(rom[pcir + 4] | (rom[pcir + 5] << 8), ==, 0x1013);
    g_assert_cmphex(rom[pcir + 6] | (rom[pcir + 7] << 8), ==, 0x00a0);
    for (unsigned int i = 0; i < size; i++) {
        checksum += rom[i];
    }
    g_assert_cmphex(checksum, ==, 0);
    qtest_quit(qts);
}

static void test_cirrus_named_pci_profile(gconstpointer opaque)
{
    unsigned int gd5430_mb = GPOINTER_TO_UINT(opaque);
    bool gd5430 = gd5430_mb != 0;
    const char *model = gd5430 ? "gd5430-pci" : "gd5446-pci";
    unsigned chip = gd5430 ? 0xa0 : 0xb8;
    QTestState *qts = qtest_initf("-M pc -nodefaults -vga none "
                                  "-device %s,addr=4,romfile=,vgamem_mb=%u",
                                  model, gd5430 ? gd5430_mb : 4);

    qtest_outl(qts, 0xcf8, 0x80002000);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, (chip << 16) | 0x1013);

    /* BAR sizing must distinguish the Alpine and GD5446 layouts. */
    qtest_outl(qts, 0xcf8, 0x80002010);
    qtest_outl(qts, 0xcfc, 0xffffffff);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==,
                    gd5430 ? 0xff000008 : 0xfe000008);
    qtest_outl(qts, 0xcfc, 0);
    qtest_outl(qts, 0xcf8, 0x80002014);
    qtest_outl(qts, 0xcfc, 0xffffffff);
    if (gd5430) {
        g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0);
    }
    qtest_outl(qts, 0xcfc, 0);

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);
    g_assert_cmphex(vga_crtc_read(qts, 0x27), ==, chip);
    g_assert_cmphex(vga_seq_read(qts, 0x17) & 0x38, ==, 0x20);
    g_assert_cmphex(vga_seq_read(qts, 0x15), ==,
                    gd5430 ? gd5430_mb + 1 : 4);
    if (gd5430) {
        g_assert_cmphex(vga_seq_read(qts, 0x0f) & 0x18, ==,
                        gd5430_mb == 1 ? 0x10 : 0x18);
    }

    vga_gfx_write(qts, 0x12, 0x5a);
    g_assert_cmphex(vga_gfx_read(qts, 0x12), ==, gd5430 ? 0xff : 0x5a);
    vga_gfx_write(qts, 0x33, 0x04);
    g_assert_cmphex(vga_gfx_read(qts, 0x33) & 0x04, ==, gd5430 ? 0 : 4);
    vga_gfx_write(qts, 0x31, 0x80);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x80, ==, gd5430 ? 0 : 0x80);

    qtest_quit(qts);
}

static void test_cirrus_pci_identity(gconstpointer opaque)
{
    const char *model = opaque;
    bool rev_b = !strcmp(model, "gd5446b-pci");
    /* The explicit profile must also suppress the default VGA device. */
    QTestState *qts = qtest_initf("-device %s,id=cirrus", model);
    QDict *resp = qtest_qmp(qts, "{'execute': 'query-pci'}");
    QDict *device;
    QDict *id;
    QDict *class_info;

    g_assert(qdict_haskey(resp, "return"));
    device = find_pci_device(qdict_get_qlist(resp, "return"), "cirrus");
    g_assert_nonnull(device);
    id = qdict_get_qdict(device, "id");
    class_info = qdict_get_qdict(device, "class_info");
    g_assert_cmphex(qdict_get_int(id, "vendor"), ==, PCI_VENDOR_ID_CIRRUS);
    g_assert_cmphex(qdict_get_int(id, "device"), ==, 0x00b8);
    g_assert_cmphex(qdict_get_int(class_info, "class"), ==,
                    PCI_CLASS_DISPLAY_VGA);
    qobject_unref(resp);

    /* The VGA probe must agree with PCI enumeration. */
    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);
    g_assert_cmphex(vga_crtc_read(qts, 0x27) & 0xfc, ==, 0xb8);
    g_assert_cmphex(vga_seq_read(qts, 0x17) & 0x38, ==, rev_b ? 0 : 0x20);

    /* Chip ID is fixed; revision B repurposes SR17[3]. */
    qtest_outb(qts, VGA_CRT_IC, 0x27);
    qtest_outb(qts, VGA_CRT_DC, 0x98);
    g_assert_cmphex(vga_crtc_read(qts, 0x27) & 0xfc, ==, 0xb8);
    vga_seq_write(qts, 0x17, 0x38);
    g_assert_cmphex(vga_seq_read(qts, 0x17) & 0x38, ==, rev_b ? 8 : 0x20);

    qtest_quit(qts);
}

static void cirrus_pci_command(QTestState *qts, uint32_t address,
                               uint16_t command)
{
    qtest_outl(qts, 0xcf8, address | 0x04);
    qtest_outw(qts, 0xcfc, command);
}

static void test_cirrus_pci_legacy_decode(void)
{
    QTestState *qts = qtest_init("-M pc -vga none "
                                "-device cirrus-vga-generic,id=cirrus,pci-legacy-decode=on");
    QDict *resp = qtest_qmp(qts, "{'execute': 'query-pci'}");
    QDict *device;
    uint32_t address;
    uint16_t command;

    g_assert(qdict_haskey(resp, "return"));
    device = find_pci_device(qdict_get_qlist(resp, "return"), "cirrus");
    g_assert_nonnull(device);
    g_assert_cmpint(qdict_get_int(device, "bus"), ==, 0);
    address = 0x80000000U | (qdict_get_int(device, "slot") << 11) |
              (qdict_get_int(device, "function") << 8);
    qobject_unref(resp);

    qtest_outl(qts, 0xcf8, address);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0x00b81013);
    qtest_outl(qts, 0xcf8, address | 0x04);
    command = qtest_inw(qts, 0xcfc) & ~3;

    /* PCI configuration space is visible even with legacy decoding off. */
    cirrus_pci_command(qts, address, command);
    g_assert_cmphex(qtest_inb(qts, VGA_SEQ_I), ==, 0xff);

    cirrus_pci_command(qts, address, command | 3);
    vga_prepare_memory_access(qts, true);
    vga_seq_write(qts, 0x06, 0x12);
    g_assert_cmphex(vga_crtc_read(qts, 0x27) & 0xfc, ==, 0xb8);
    qtest_writeb(qts, VGA_LEGACY_MEM_BASE, 0x5a);
    g_assert_cmphex(qtest_readb(qts, VGA_LEGACY_MEM_BASE), ==, 0x5a);

    /* Disable memory only: port reads still work, VRAM is not changed. */
    cirrus_pci_command(qts, address, command | 1);
    g_assert_cmphex(vga_crtc_read(qts, 0x27) & 0xfc, ==, 0xb8);
    qtest_writeb(qts, VGA_LEGACY_MEM_BASE, 0xa5);

    /* Disable ports only: memory still works, register writes are ignored. */
    cirrus_pci_command(qts, address, command | 2);
    g_assert_cmphex(qtest_inb(qts, VGA_SEQ_I), ==, 0xff);
    qtest_outb(qts, VGA_SEQ_I, 0x17);
    g_assert_cmphex(qtest_readb(qts, VGA_LEGACY_MEM_BASE), ==, 0x5a);
    qtest_writeb(qts, VGA_LEGACY_MEM_BASE, 0x69);

    cirrus_pci_command(qts, address, command | 3);
    g_assert_cmphex(qtest_inb(qts, VGA_SEQ_I), ==, 0x06);
    g_assert_cmphex(qtest_readb(qts, VGA_LEGACY_MEM_BASE), ==, 0x69);
    g_assert_cmphex(vga_seq_read(qts, 0x17) & 0x38, ==, 0x20);
    qtest_quit(qts);
}

static void test_gd5446_revision(gconstpointer opaque)
{
    bool rev_a = GPOINTER_TO_INT(opaque);
    const char *model = rev_a ? "gd5446a-pci" : "gd5446b-pci";
    const uint32_t config = 0x80002000U;
    const uint32_t lfb = 0xe0000000U;
    const uint32_t mmio = 0xe2000000U;
    const uint32_t dst = lfb + 0x100;
    const uint32_t source = rev_a ? 0xbc000 : lfb + 0x1000000;
    QTestState *qts = qtest_initf("-M pc -device %s,addr=4,romfile=", model);

    qtest_outl(qts, 0xcf8, config);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0x00b81013);
    cirrus_pci_command(qts, config, 0);

    /* Both chips share the device ID, but expose different PCI resources. */
    qtest_outl(qts, 0xcf8, config | 0x10);
    qtest_outl(qts, 0xcfc, 0xffffffff);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==,
                    rev_a ? 0xff000008 : 0xfe000000);
    qtest_outl(qts, 0xcfc, lfb);
    qtest_outl(qts, 0xcf8, config | 0x14);
    qtest_outl(qts, 0xcfc, 0xffffffff);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==,
                    rev_a ? 0 : 0xfffff000);
    qtest_outl(qts, 0xcfc, mmio);
    qtest_outl(qts, 0xcf8, config | 0x18);
    qtest_outl(qts, 0xcfc, 0xffffffff);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0);
    if (rev_a) {
        qtest_outl(qts, 0xcf8, config | 0x2c);
        g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0);
    }

    cirrus_pci_command(qts, config, 3);
    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);
    g_assert_cmphex(vga_crtc_read(qts, 0x27), ==, 0xb8);
    vga_seq_write(qts, 0x07, 1);
    vga_gfx_write(qts, 0x0b, 0);
    if (rev_a) {
        /* A's optional legacy MMIO window aliases every 256 bytes. */
        vga_seq_write(qts, 0x17, 4);
        qtest_writeb(qts, 0xb8104, 0x77);
        g_assert_cmphex(vga_gfx_read(qts, 1), ==, 0x77);
        vga_seq_write(qts, 0x17, 0);
    } else {
        /* B exposes relocated VGA/DAC ports in BAR1. */
        qtest_writeb(qts, mmio + 6, 0x5a);
        g_assert_cmphex(qtest_inb(qts, VGA_PEL_MSK), ==, 0x5a);
        qtest_outb(qts, VGA_PEL_MSK, 0xff);
    }

    /* 32-pixel color expansion, alternate source selected via GR31[6]. */
    vga_gfx_write(qts, 0, 0x11);
    vga_gfx_write(qts, 1, 0x77);
    vga_gfx_write(qts, 0x20, 31);
    vga_gfx_write(qts, 0x22, 0);
    vga_gfx_write(qts, 0x24, 32);
    vga_gfx_write(qts, 0x29, 1);
    vga_gfx_write(qts, 0x30, 0x84);
    vga_gfx_write(qts, 0x32, 0x0d);
    vga_gfx_write(qts, 0x33, 1);
    vga_gfx_write(qts, 0x31, 0x42);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 1, ==, 1);

    /* Framebuffer writes must not be mistaken for the BitBLT source. */
    qtest_writel(qts, lfb + 0x200, 0x5a5a5a5aU);
    g_assert_cmphex(qtest_readb(qts, lfb + 0x200), ==, 0x5a);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 1, ==, 1);
    qtest_writel(qts, source, 0xffffffffU);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 1, ==, 0);
    for (unsigned i = 0; i < 32; i++) {
        g_assert_cmphex(qtest_readb(qts, dst + i), ==, 0x77);
    }

    qtest_quit(qts);
}

static void test_gd5446b_pc97(void)
{
    const uint32_t config = 0x80002000U;
    const uint32_t mmio = 0xe2000000U;
    uint32_t original;
    QTestState *qts = qtest_init("-M pc -device gd5446b-pci,addr=4,romfile=,"
                                "pci-legacy-decode=on");

    qtest_outl(qts, 0xcf8, config | 4);
    g_assert_cmphex(qtest_inw(qts, 0xcfe) & 0x600, ==, 0x200);
    qtest_outl(qts, 0xcf8, config | 0x3c);
    g_assert_cmphex(qtest_inb(qts, 0xcfd), ==, 0);
    qtest_outl(qts, 0xcf8, config | 0x14);
    qtest_outl(qts, 0xcfc, mmio);
    cirrus_pci_command(qts, config, 3);

    qtest_outl(qts, 0xcf8, config | 0x2c);
    original = qtest_inl(qts, 0xcfc);
    g_assert_cmphex(original >> 24, ==, 0);
    g_assert_cmphex(original & 0xffff, !=, 0);
    qtest_outl(qts, 0xcfc, 0x12345678);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, original);

    vga_seq_write(qts, 0x06, 0x12);
    vga_seq_write(qts, 0x17, 0x39);
    g_assert_cmphex(vga_seq_read(qts, 0x17), ==, 8);
    qtest_outl(qts, 0xcfc, 0x12345678);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0x12345678);
    qtest_outw(qts, 0xcfc, 0x1013);
    qtest_outb(qts, 0xcfe, 0xab);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0x12ab1013);

    /* PCI memory enable alone permits the relocated register interface. */
    cirrus_pci_command(qts, config, 2);
    g_assert_cmphex(qtest_inb(qts, VGA_SEQ_I), ==, 0xff);
    qtest_writeb(qts, mmio + 4, 0x17);
    qtest_writeb(qts, mmio + 5, 0);
    g_assert_cmphex(qtest_readb(qts, mmio + 5), ==, 0);
    qtest_outl(qts, 0xcf8, config | 0x2c);
    qtest_outl(qts, 0xcfc, 0);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0x12ab1013);

    qtest_system_reset(qts);
    qtest_outl(qts, 0xcf8, config | 0x2c);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, original);
    cirrus_pci_command(qts, config, 3);
    vga_seq_write(qts, 0x06, 0x12);
    g_assert_cmphex(vga_seq_read(qts, 0x17) & 8, ==, 0);
    qtest_quit(qts);
}

static void test_gd5446b_blt_pause(gconstpointer opaque)
{
    const bool alternate = GPOINTER_TO_INT(opaque);
    const uint32_t config = 0x80002000U;
    const uint32_t lfb = 0xe0000000U;
    const uint32_t mmio = 0xe2000000U;
    const uint32_t source = lfb + (alternate ? 0x1000000U : 0);
    const uint8_t control = alternate ? 0x40 : 0;
    static const uint8_t expected[] = {
        0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88,
    };
    QTestState *qts = qtest_init("-M pc -device gd5446b-pci,addr=4,romfile=");

    cirrus_pci_command(qts, config, 0);
    qtest_outl(qts, 0xcf8, config | 0x10);
    qtest_outl(qts, 0xcfc, lfb);
    qtest_outl(qts, 0xcf8, config | 0x14);
    qtest_outl(qts, 0xcfc, mmio);
    cirrus_pci_command(qts, config, 3);
    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);
    vga_seq_write(qts, 0x07, 1);
    vga_gfx_write(qts, 0x0b, 0);

    /* One 8-byte row, with only the first source DWORD supplied. */
    vga_gfx_write(qts, 0x20, 7);
    vga_gfx_write(qts, 0x22, 0);
    vga_gfx_write(qts, 0x24, 8);
    vga_gfx_write(qts, 0x29, 1);
    vga_gfx_write(qts, 0x30, 4);
    vga_gfx_write(qts, 0x32, 0x0d);
    qtest_writel(qts, lfb + 0x100, 0xa5a5a5a5U);
    qtest_writel(qts, lfb + 0x104, 0xa5a5a5a5U);
    vga_gfx_write(qts, 0x31, control | 2);
    qtest_writel(qts, source, 0x44332211U);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 3, ==, 3);

    /* Pausing via relocated MMIO must not discard the first DWORD. */
    qtest_writeb(qts, mmio + 0x140, control | 0x20);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x21, ==, 0x20);
    qtest_writel(qts, lfb + 0x200, 0x5a5a5a5aU);
    g_assert_cmphex(qtest_readl(qts, lfb + 0x200), ==, 0x5a5a5a5aU);
    if (alternate) {
        qtest_writel(qts, source, 0xeeeeeeeeU);
    }
    g_assert_cmphex(qtest_readl(qts, lfb + 0x100), ==, 0xa5a5a5a5U);
    g_assert_cmphex(qtest_readl(qts, lfb + 0x104), ==, 0xa5a5a5a5U);

    vga_gfx_write(qts, 0x31, control);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 0x21, ==, 1);
    qtest_writel(qts, source, 0x88776655U);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 3, ==, 0);
    for (unsigned i = 0; i < sizeof(expected); i++) {
        g_assert_cmphex(qtest_readb(qts, lfb + 0x100 + i), ==, expected[i]);
    }
    g_assert_cmphex(qtest_readl(qts, lfb + 0x200), ==, 0x5a5a5a5aU);
    qtest_quit(qts);
}

static void test_cirrus_pci_dword_expand(void)
{
    const uint32_t config = 0x80000000U | (5U << 11);
    const uint32_t lfb = 0xe0000000U;
    const uint32_t mmio = 0xe2000000U;
    const uint32_t dst = lfb + 0x100;
    QTestState *qts = qtest_init("-M pc -vga none -nodefaults "
                                "-device cirrus-vga-generic,addr=05.0");

    /* Program PCI BARs directly; no BIOS or guest driver is required. */
    qtest_outl(qts, 0xcf8, config);
    g_assert_cmphex(qtest_inl(qts, 0xcfc), ==, 0x00b81013);
    cirrus_pci_command(qts, config, 0);
    qtest_outl(qts, 0xcf8, config | 0x10);
    qtest_outl(qts, 0xcfc, lfb);
    qtest_outl(qts, 0xcf8, config | 0x14);
    qtest_outl(qts, 0xcfc, mmio);
    cirrus_pci_command(qts, config, 3);
    vga_seq_write(qts, 0x06, 0x12);
    vga_seq_write(qts, 0x07, 0x01);
    vga_gfx_write(qts, 0x0b, 0);

    /* Two 32-pixel, 8-bpp rows; each consumes four source bytes. */
    qtest_writeb(qts, mmio + 0x100, 0x11);
    qtest_writeb(qts, mmio + 0x104, 0x77);
    qtest_writew(qts, mmio + 0x108, 31);
    qtest_writew(qts, mmio + 0x10a, 1);
    qtest_writew(qts, mmio + 0x10c, 32);
    qtest_writel(qts, mmio + 0x110, 0x100);
    qtest_writeb(qts, mmio + 0x117, 0); /* No left-side clipping. */
    qtest_writeb(qts, mmio + 0x118, 0x84);
    qtest_writeb(qts, mmio + 0x11a, 0x0d);
    qtest_writeb(qts, mmio + 0x11b, 1);
    g_assert_cmphex(vga_gfx_read(qts, 0x33), ==, 1);

    /* BUSY and buffered-command status are not writable, nor is bit 3. */
    vga_gfx_write(qts, 0x31, 0x19);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 0x19, ==, 0);
    qtest_writeb(qts, mmio + 0x140, 0x19);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x19, ==, 0);
    qtest_writeb(qts, mmio + 0x140, 2);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 1, ==, 1);

    /* Source stream through the first PCI linear aperture. */
    qtest_writeb(qts, lfb + 0x1000, 0xff);
    /* A control-register write or repeat START must not discard data. */
    vga_gfx_write(qts, 0x31, 0);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 0x13, ==, 3);
    qtest_writeb(qts, mmio + 0x140, 2);
    qtest_writeb(qts, lfb + 0x1001, 0x00);
    qtest_writeb(qts, lfb + 0x1002, 0x00);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 1, ==, 1);
    qtest_writeb(qts, lfb + 0x1003, 0x00);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 1, ==, 1);
    qtest_writel(qts, lfb + 0x1004, 0xffffff00U);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x140) & 1, ==, 0);

    for (unsigned i = 0; i < 32; i++) {
        g_assert_cmphex(qtest_readb(qts, dst + i), ==,
                        i < 8 ? 0x77 : 0x11);
        g_assert_cmphex(qtest_readb(qts, dst + 32 + i), ==,
                        i < 8 ? 0x11 : 0x77);
    }

    /* Abort a partially supplied scanline on assertion, not release. */
    qtest_writeb(qts, mmio + 0x140, 2);
    qtest_writeb(qts, lfb + 0x1000, 0x00);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 1, ==, 1);
    qtest_writeb(qts, mmio + 0x140, 4);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x17, ==, 4);
    qtest_writeb(qts, mmio + 0x140, 6);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x17, ==, 4);
    qtest_writeb(qts, mmio + 0x140, 0);
    qtest_writeb(qts, lfb + 0x1000, 0x5a);
    g_assert_cmphex(qtest_readb(qts, lfb + 0x1000), ==, 0x5a);
    g_assert_cmphex(qtest_readb(qts, dst), ==, 0x77);

    /* A fresh operation must start with an empty source buffer. */
    qtest_writeb(qts, mmio + 0x140, 2);
    qtest_writel(qts, lfb + 0x1000, 0xffffffffU);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 1, ==, 1);
    qtest_writel(qts, lfb + 0x1004, 0xffffffffU);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 0x13, ==, 0);
    for (unsigned i = 0; i < 64; i++) {
        g_assert_cmphex(qtest_readb(qts, dst + i), ==, 0x77);
    }
    qtest_quit(qts);
}

static void test_cirrus_pci_blt_dimensions(void)
{
    const uint32_t config = 0x80000000U | (5U << 11);
    const uint32_t mmio = 0xe2000000U;
    QTestState *qts = qtest_init("-M pc -vga none -nodefaults "
                                "-device cirrus-vga-generic,addr=05.0");

    cirrus_pci_command(qts, config, 0);
    qtest_outl(qts, 0xcf8, config | 0x14);
    qtest_outl(qts, 0xcfc, mmio);
    cirrus_pci_command(qts, config, 3);
    vga_seq_write(qts, 0x06, 0x12);

    /* Width and pitch retain 13 bits; height retains only 11. */
    vga_gfx_write(qts, 0x21, 0xff);
    vga_gfx_write(qts, 0x23, 0xff);
    vga_gfx_write(qts, 0x25, 0xff);
    vga_gfx_write(qts, 0x27, 0xff);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x109), ==, 0x1f);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x10b), ==, 0x07);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x10d), ==, 0x1f);
    g_assert_cmphex(qtest_readb(qts, mmio + 0x10f), ==, 0x1f);

    qtest_writew(qts, mmio + 0x10a, 0xf812);
    g_assert_cmphex(vga_gfx_read(qts, 0x22), ==, 0x12);
    g_assert_cmphex(vga_gfx_read(qts, 0x23), ==, 0);
    qtest_system_reset(qts);
    g_assert_cmphex(vga_gfx_read(qts, 0x23), ==, 0);
    qtest_quit(qts);
}

static void test_cirrus_pci_solidfill_completion(void)
{
    const uint32_t config = 0x80000000U | (5U << 11);
    const uint32_t lfb = 0xe0000000U;
    QTestState *qts = qtest_init("-M pc -vga none -nodefaults "
                                "-device cirrus-vga-generic,addr=05.0");

    cirrus_pci_command(qts, config, 0);
    qtest_outl(qts, 0xcf8, config | 0x10);
    qtest_outl(qts, 0xcfc, lfb);
    cirrus_pci_command(qts, config, 3);
    vga_seq_write(qts, 0x06, 0x12);
    vga_seq_write(qts, 0x07, 1);
    vga_gfx_write(qts, 0x0b, 0);

    /* Two four-byte rows, solid foreground color. */
    vga_gfx_write(qts, 0x01, 0x5a);
    vga_gfx_write(qts, 0x20, 3);
    vga_gfx_write(qts, 0x22, 1);
    vga_gfx_write(qts, 0x28, 0x40);
    vga_gfx_write(qts, 0x30, 0xc0);
    vga_gfx_write(qts, 0x32, 0x0d);
    vga_gfx_write(qts, 0x33, 4);

    /* An operation rejected by the existing geometry checks must end. */
    vga_gfx_write(qts, 0x31, 2);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 3, ==, 0);

    /* The driver can issue a fresh, supported operation without reset. */
    vga_gfx_write(qts, 0x24, 4);
    vga_gfx_write(qts, 0x31, 2);
    g_assert_cmphex(vga_gfx_read(qts, 0x31) & 3, ==, 0);
    for (unsigned i = 0; i < 8; i++) {
        g_assert_cmphex(qtest_readb(qts, lfb + 0x40 + i), ==, 0x5a);
    }
    qtest_quit(qts);
}

static void cirrus_crtc_write(QTestState *qts, uint8_t index, uint8_t value)
{
    qtest_outb(qts, VGA_CRT_IC, index);
    qtest_outb(qts, VGA_CRT_DC, value);
}

static void test_cirrus_pci_timing(void)
{
    QTestState *qts = qtest_init("-M pc -vga none -nodefaults "
                                "-device cirrus-vga-generic,precise-timing=on");

    qtest_outb(qts, VGA_MIS_W, VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS);
    vga_seq_write(qts, 0x06, 0x12);
    vga_seq_write(qts, VGA_SEQ_CLOCK_MODE, 1);
    /* 100 characters per line, 100 lines per frame; no overflow bits. */
    cirrus_crtc_write(qts, VGA_CRTC_V_SYNC_END, 4);
    cirrus_crtc_write(qts, VGA_CRTC_H_TOTAL, 95);
    cirrus_crtc_write(qts, VGA_CRTC_V_TOTAL, 98);
    cirrus_crtc_write(qts, VGA_CRTC_OVERFLOW, 0);
    cirrus_crtc_write(qts, VGA_CRTC_MAX_SCAN, 0);
    cirrus_crtc_write(qts, VGA_CRTC_H_BLANK_START, 80);
    cirrus_crtc_write(qts, VGA_CRTC_H_BLANK_END, 3);
    cirrus_crtc_write(qts, VGA_CRTC_H_SYNC_END, 0x80);
    cirrus_crtc_write(qts, VGA_CRTC_V_BLANK_START, 80);
    cirrus_crtc_write(qts, VGA_CRTC_V_BLANK_END, 90);
    cirrus_crtc_write(qts, VGA_CRTC_V_SYNC_START, 80);

    /* VCLK0 = 14.31818 MHz * 60 / 30 = 28.63636 MHz. */
    vga_seq_write(qts, 0x0b, 60);
    vga_seq_write(qts, 0x1b, 60);
    qtest_clock_set(qts, 2300000);
    /* Character 8232: vertical sync and blanking are active. */
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 9);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 9);

    /*
     * HDR 0x4a and SR7[3:0] = 7 select two indexed pixels per CRTC
     * clock. At this virtual time the divided clock is not blanking.
     * Verify that either register can be the last one programmed.
     */
    qtest_inb(qts, VGA_PEL_IW);
    cirrus_dac_unlock(qts, 0xff);
    qtest_outb(qts, VGA_PEL_MSK, 0x4a);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 9);
    vga_seq_write(qts, 0x07, 7);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 0);
    cirrus_dac_unlock(qts, 0xff);
    qtest_outb(qts, VGA_PEL_MSK, 0xc1);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 9);
    cirrus_dac_unlock(qts, 0xff);
    qtest_outb(qts, VGA_PEL_MSK, 0x4a);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 0);
    vga_seq_write(qts, 0x07, 0);
    cirrus_dac_unlock(qts, 0xff);
    qtest_outb(qts, VGA_PEL_MSK, 0);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 9);

    /* Doubling the numerator changes the derived phase without a delay. */
    vga_seq_write(qts, 0x0b, 120);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 0);

    /* The SR1 clock divider returns to the original clock rate. */
    vga_seq_write(qts, VGA_SEQ_CLOCK_MODE, 9);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 9);

    /* Moving VSYNC start immediately changes bit 3, not blanking bit 0. */
    cirrus_crtc_write(qts, VGA_CRTC_V_SYNC_START, 83);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 9, ==, 1);

    /* Select the unprogrammed VCLK2: documented default 41.165 MHz. */
    vga_seq_write(qts, VGA_SEQ_CLOCK_MODE, 1);
    vga_seq_write(qts, 0x0d, 0);
    vga_seq_write(qts, 0x1d, 0);
    cirrus_crtc_write(qts, VGA_CRTC_V_SYNC_START, 18);
    qtest_outb(qts, VGA_MIS_W,
               VGA_MIS_COLOR | VGA_MIS_ENB_MEM_ACCESS | 8);
    g_assert_cmphex(qtest_inb(qts, VGA_IS1_RC) & 8, ==, 8);

    qtest_quit(qts);
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
        "cirrus-vga-generic",
        "cirrus-vga-generic-pci",
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

    if (qtest_has_device("cirrus-vga-generic") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_data_func("/display/pci/cirrus-identity",
                            "cirrus-vga-generic", test_cirrus_pci_identity);
        if (qtest_has_device("cirrus-vga-generic-pci")) {
            qtest_add_data_func("/display/pci/cirrus-explicit-pci-identity",
                                "cirrus-vga-generic-pci",
                                test_cirrus_pci_identity);
        }
        if (qtest_has_machine("pc")) {
            qtest_add_func("/display/pci/cirrus-legacy-decode",
                           test_cirrus_pci_legacy_decode);
        }
        qtest_add_func("/display/pci/cirrus-gray-palette",
                       test_cirrus_gray_palette);
        if (qtest_has_machine("pc")) {
            qtest_add_func("/display/pci/cirrus-dword-expand",
                           test_cirrus_pci_dword_expand);
            qtest_add_func("/display/pci/cirrus-blt-dimensions",
                           test_cirrus_pci_blt_dimensions);
            qtest_add_func("/display/pci/cirrus-solidfill-completion",
                           test_cirrus_pci_solidfill_completion);
            qtest_add_func("/display/pci/cirrus-precise-timing",
                           test_cirrus_pci_timing);
        }
    }

    if (qtest_has_device("cirrus-vga-generic-isa") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_func("/display/isa/cirrus-profile",
                       test_isa_cirrus_profile);
    }

    if (qtest_has_machine("pc") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        if (qtest_has_device("gd5430-pci")) {
            qtest_add_func("/display/pci/cirrus-gd5430-default-rom",
                           test_gd5430_default_rom);
            qtest_add_data_func("/display/pci/cirrus-gd5430-profile",
                                GUINT_TO_POINTER(2),
                                test_cirrus_named_pci_profile);
            qtest_add_data_func("/display/pci/cirrus-gd5430-1mb",
                                GUINT_TO_POINTER(1),
                                test_cirrus_named_pci_profile);
        }
        if (qtest_has_device("gd5446a-pci")) {
            qtest_add_data_func("/display/pci/cirrus-gd5446a-revision",
                                GINT_TO_POINTER(1), test_gd5446_revision);
            qtest_add_data_func("/display/pci/cirrus-gd5446a-identity",
                                "gd5446a-pci", test_cirrus_pci_identity);
        }
        if (qtest_has_device("gd5446b-pci")) {
            qtest_add_func("/display/pci/cirrus-gd5446b-pc97",
                           test_gd5446b_pc97);
            qtest_add_data_func("/display/pci/cirrus-gd5446b-pause-primary",
                                GINT_TO_POINTER(0), test_gd5446b_blt_pause);
            qtest_add_data_func("/display/pci/cirrus-gd5446b-pause-alternate",
                                GINT_TO_POINTER(1), test_gd5446b_blt_pause);
            qtest_add_data_func("/display/pci/cirrus-gd5446b-revision",
                                GINT_TO_POINTER(0), test_gd5446_revision);
            qtest_add_data_func("/display/pci/cirrus-gd5446b-identity",
                                "gd5446b-pci", test_cirrus_pci_identity);
        }
        if (qtest_has_device("gd5446-pci")) {
            qtest_add_func("/display/pci/cirrus-gd5446-dac-sequence",
                           test_gd5446_dac_sequence);
            qtest_add_data_func("/display/pci/cirrus-gd5446-profile",
                                GINT_TO_POINTER(0),
                                test_cirrus_named_pci_profile);
        }
    }

    if (qtest_has_device("gd5428") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_func("/display/isa/cirrus-gd5428-profile",
                       test_isa_cirrus_gd5428_profile);
    }

    if (qtest_has_device("gd5426") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_func("/display/isa/cirrus-gd5426-profile",
                       test_isa_cirrus_gd5426_profile);
    }

    if (qtest_has_device("gd5422") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_func("/display/isa/cirrus-gd5422-profile",
                       test_isa_cirrus_gd5422_profile);
    }

    if (qtest_has_device("gd5430-vlb") &&
        (!strcmp(arch, "i386") || !strcmp(arch, "x86_64"))) {
        qtest_add_data_func("/display/vlb/gd5430/64mb",
                            GUINT_TO_POINTER(0x04000000U),
                            test_vlb_cirrus_decoder);
        qtest_add_data_func("/display/vlb/gd5430/2gb",
                            GUINT_TO_POINTER(0x80000000U),
                            test_vlb_cirrus_decoder);
        qtest_add_func("/display/vlb/gd5430/1mb", test_gd5430_vlb_1mb);
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
