/*
 * QTest testcase for the NewWorld PowerMac KeyLargo timer
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "libqtest.h"
#include "hw/pci/pci.h"
#include "hw/pci-host/uninorth.h"
#include "qemu/bswap.h"

#define UNINORTH_CONFIG_ADDR     0xf2800000
#define UNINORTH_CONFIG_DATA     0xf2c00000
#define UNINORTH_AGP_CONFIG_ADDR 0xf0800000
#define UNINORTH_AGP_CONFIG_DATA 0xf0c00000
#define UNINORTH_REG_BASE        0xf8000000
#define UNINORTH_AGP_HOST_SLOT   11
#define MACIO_BAR_BASE       0x80000000
#define MACIO_TIMER_LOW      (MACIO_BAR_BASE + 0x15038)
#define MACIO_SCREAMER_CTRL   (MACIO_BAR_BASE + 0x14000)
#define MACIO_SCREAMER_CODEC  (MACIO_BAR_BASE + 0x14010)
#define MACIO_SCREAMER_STATUS (MACIO_BAR_BASE + 0x14020)
#define MACIO_SCREAMER_SWAP   (MACIO_BAR_BASE + 0x14040)
#define SCREAMER_STATUS_FIXED  0x00403100U
#define SAWTOOTH_BRIDGE_SLOT    13
#define SAWTOOTH_SECONDARY_BUS  1
#define SAWTOOTH_MACIO_SLOT     7
#define KEYLARGO_TIMER_FREQ  18432000ULL
#define TIMER_PROBE_NS       1899

static uint32_t read_le32(QTestState *qts, uint64_t addr)
{
    uint8_t buf[4];

    qtest_memread(qts, addr, buf, sizeof(buf));
    return ldl_le_p(buf);
}

static void write_le32(QTestState *qts, uint64_t addr, uint32_t value)
{
    uint8_t buf[4];

    stl_le_p(buf, value);
    qtest_memwrite(qts, addr, buf, sizeof(buf));
}

static uint32_t read_be32(QTestState *qts, uint64_t addr)
{
    uint8_t buf[4];

    qtest_memread(qts, addr, buf, sizeof(buf));
    return ldl_be_p(buf);
}

static void write_be32(QTestState *qts, uint64_t addr, uint32_t value)
{
    uint8_t buf[4];

    stl_be_p(buf, value);
    qtest_memwrite(qts, addr, buf, sizeof(buf));
}

static void write_le16(QTestState *qts, uint64_t addr, uint16_t value)
{
    uint8_t buf[2];

    stw_le_p(buf, value);
    qtest_memwrite(qts, addr, buf, sizeof(buf));
}

static void uninorth_select(QTestState *qts, unsigned slot, unsigned reg)
{
    write_le32(qts, UNINORTH_CONFIG_ADDR,
               (1U << slot) | (reg & ~7U));
}

static void uninorth_agp_select(QTestState *qts, unsigned reg)
{
    write_le32(qts, UNINORTH_AGP_CONFIG_ADDR,
               (1U << 31) | (PCI_DEVFN(UNINORTH_AGP_HOST_SLOT, 0) << 8) |
               (reg & ~3U));
}

static uint32_t uninorth_agp_read(QTestState *qts, unsigned reg)
{
    uninorth_agp_select(qts, reg);
    return read_le32(qts, UNINORTH_AGP_CONFIG_DATA + (reg & 3));
}

static void uninorth_agp_write(QTestState *qts, unsigned reg, uint32_t value)
{
    uninorth_agp_select(qts, reg);
    write_le32(qts, UNINORTH_AGP_CONFIG_DATA + (reg & 3), value);
}

static unsigned find_keylargo_slot(QTestState *qts)
{
    uint32_t keylargo_id =
        (PCI_DEVICE_ID_APPLE_UNI_N_KEYL << 16) | PCI_VENDOR_ID_APPLE;
    unsigned slot;

    for (slot = 11; slot < 32; slot++) {
        uninorth_select(qts, slot, 0);
        if (read_le32(qts, UNINORTH_CONFIG_DATA) == keylargo_id) {
            return slot;
        }
    }

    g_assert_not_reached();
}

static void map_keylargo(QTestState *qts, unsigned slot)
{
    uninorth_select(qts, slot, PCI_BASE_ADDRESS_0);
    write_le32(qts, UNINORTH_CONFIG_DATA, MACIO_BAR_BASE);

    uninorth_select(qts, slot, PCI_COMMAND);
    write_le16(qts, UNINORTH_CONFIG_DATA + (PCI_COMMAND & 7),
               PCI_COMMAND_MEMORY);
}

static void uninorth_select_cfa1(QTestState *qts, unsigned bus,
                                 unsigned slot, unsigned reg)
{
    write_le32(qts, UNINORTH_CONFIG_ADDR,
               1U | (bus << 16) | (PCI_DEVFN(slot, 0) << 8) |
               (reg & ~7U));
}

static uint32_t uninorth_read_cfa1(QTestState *qts, unsigned bus,
                                   unsigned slot, unsigned reg)
{
    uninorth_select_cfa1(qts, bus, slot, reg);
    return read_le32(qts, UNINORTH_CONFIG_DATA + (reg & 7));
}

static void map_sawtooth_keylargo(QTestState *qts)
{
    /*
     * PowerMac3,1 puts KeyLargo at bus 1, device 7 behind the DEC 21154
     * at root device 13.  Program the bridge exactly far enough for qtest
     * to reach and map MacIO; firmware normally performs this enumeration.
     */
    uninorth_select(qts, SAWTOOTH_BRIDGE_SLOT, PCI_PRIMARY_BUS);
    write_le32(qts, UNINORTH_CONFIG_DATA,
               (SAWTOOTH_SECONDARY_BUS << 8) |
               (SAWTOOTH_SECONDARY_BUS << 16));

    uninorth_select(qts, SAWTOOTH_BRIDGE_SLOT, PCI_MEMORY_BASE);
    write_le32(qts, UNINORTH_CONFIG_DATA, 0x80008000U);

    uninorth_select(qts, SAWTOOTH_BRIDGE_SLOT, PCI_COMMAND);
    write_le16(qts, UNINORTH_CONFIG_DATA + (PCI_COMMAND & 7),
               PCI_COMMAND_MEMORY | PCI_COMMAND_MASTER);

    g_assert_cmphex(
        uninorth_read_cfa1(qts, SAWTOOTH_SECONDARY_BUS,
                           SAWTOOTH_MACIO_SLOT, PCI_VENDOR_ID),
        ==,
        (PCI_DEVICE_ID_APPLE_UNI_N_KEYL << 16) | PCI_VENDOR_ID_APPLE);

    uninorth_select_cfa1(qts, SAWTOOTH_SECONDARY_BUS,
                         SAWTOOTH_MACIO_SLOT, PCI_BASE_ADDRESS_0);
    write_le32(qts, UNINORTH_CONFIG_DATA, MACIO_BAR_BASE);

    uninorth_select_cfa1(qts, SAWTOOTH_SECONDARY_BUS,
                         SAWTOOTH_MACIO_SLOT, PCI_COMMAND);
    write_le16(qts, UNINORTH_CONFIG_DATA + (PCI_COMMAND & 7),
               PCI_COMMAND_MEMORY | PCI_COMMAND_MASTER);
}

static void test_keylargo_timer_precision(void)
{
    QTestState *qts;
    uint64_t expected;
    uint32_t actual;
    unsigned slot;

    if (g_str_equal(qtest_get_arch(), "ppc64")) {
        g_test_skip("32-bit mac99 uses the UniNorth main PCI config window");
        return;
    }

    qts = qtest_init("-M mac99 -nodefaults -boot c");
    slot = find_keylargo_slot(qts);
    map_keylargo(qts, slot);

    g_assert_cmpint(qtest_clock_set(qts, 0), ==, 0);
    g_assert_cmpint(qtest_clock_set(qts, TIMER_PROBE_NS), ==, TIMER_PROBE_NS);

    expected = TIMER_PROBE_NS * KEYLARGO_TIMER_FREQ / 1000000000ULL;
    actual = read_le32(qts, MACIO_TIMER_LOW);
    g_assert_cmpuint(actual, ==, expected);

    qtest_quit(qts);
}

/*
 * QTest MMIO accesses are not issued by a guest execution thread.  Mac99
 * nevertheless has a valid bootstrap CPU_NUMBER (zero) for its sole CPU,
 * independent of the absent current_cpu context.
 */
static void test_mac99_uninorth_boot_cpu(void)
{
    QTestState *qts = qtest_init("-M mac99 -nodefaults");

    g_assert_cmphex(read_be32(qts, UNINORTH_REG_BASE +
                                   UNINORTH_REG_CPU_NUMBER),
                    ==, UNINORTH_CPU_NUMBER_BOOT);
    g_assert_cmphex(read_be32(qts, UNINORTH_REG_BASE +
                                   UNINORTH_REG_VERSION),
                    ==, UNINORTH_VERSION_10A);
    /* Repeated accesses must not inherit a stale vCPU context. */
    g_assert_cmphex(read_be32(qts, UNINORTH_REG_BASE +
                                   UNINORTH_REG_CPU_NUMBER),
                    ==, UNINORTH_CPU_NUMBER_BOOT);

    qtest_quit(qts);
}

static void test_sawtooth_uninorth_registers(void)
{
    QTestState *qts;
    uint32_t clocks = UNINORTH_CLOCK_CNTL_PCI |
                      UNINORTH_CLOCK_CNTL_GMAC |
                      UNINORTH_CLOCK_CNTL_FW;
    uint32_t ctrl = UNINORTH_GART_CTRL_ENABLE |
                    UNINORTH_GART_CTRL_INVAL |
                    UNINORTH_GART_CTRL_2XRESET;

    if (g_str_equal(qtest_get_arch(), "ppc64")) {
        g_test_skip("PowerMac3,1 uses UniNorth 1.0.10, not U3");
        return;
    }

    qts = qtest_init("-M powermac3_1 -nodefaults -boot c");

    g_assert_cmphex(read_be32(qts, UNINORTH_REG_BASE + UNINORTH_REG_VERSION),
                    ==, UNINORTH_VERSION_10A);
    g_assert_cmphex(read_be32(qts,
                             UNINORTH_REG_BASE + UNINORTH_REG_CPU_NUMBER),
                    ==, UNINORTH_CPU_NUMBER_BOOT);

    write_be32(qts, UNINORTH_REG_BASE + UNINORTH_REG_CLOCK_CNTL, clocks);
    g_assert_cmphex(read_be32(qts,
                             UNINORTH_REG_BASE + UNINORTH_REG_CLOCK_CNTL),
                    ==, clocks);

    uninorth_agp_write(qts, UNINORTH_CFG_GART_BASE, 0x12345020U);
    g_assert_cmphex(uninorth_agp_read(qts, UNINORTH_CFG_GART_BASE),
                    ==, 0x12345020U);

    uninorth_agp_write(qts, UNINORTH_CFG_AGP_BASE, 0x90000000U);
    g_assert_cmphex(uninorth_agp_read(qts, UNINORTH_CFG_AGP_BASE),
                    ==, 0x90000000U);

    uninorth_agp_write(qts, UNINORTH_CFG_GART_CTRL, ctrl | 0x80000000U);
    g_assert_cmphex(uninorth_agp_read(qts, UNINORTH_CFG_GART_CTRL),
                    ==, ctrl);

    g_assert_cmphex(uninorth_agp_read(qts, UNINORTH_CFG_INTERNAL_STATUS),
                    ==, 0);
    uninorth_agp_write(qts, UNINORTH_CFG_INTERNAL_STATUS, 0xffffffffU);
    g_assert_cmphex(uninorth_agp_read(qts, UNINORTH_CFG_INTERNAL_STATUS),
                    ==, 0);

    qtest_quit(qts);
}

static void test_sawtooth_screamer_registers(void)
{
    QTestState *qts;
    uint32_t codec_write = (1U << 24) | (1U << 12) | 0x84;

    if (g_str_equal(qtest_get_arch(), "ppc64")) {
        g_test_skip("PowerMac3,1 is a 32-bit NewWorld machine");
        return;
    }

    qts = qtest_init("-M powermac3_1 -nodefaults -boot c");
    map_sawtooth_keylargo(qts);

    g_assert_cmphex(read_le32(qts, MACIO_SCREAMER_STATUS),
                    ==, SCREAMER_STATUS_FIXED);

    write_le32(qts, MACIO_SCREAMER_CTRL, 0x211);
    g_assert_cmphex(read_le32(qts, MACIO_SCREAMER_CTRL), ==, 0x211);

    write_le32(qts, MACIO_SCREAMER_CODEC, codec_write);
    g_assert_cmphex(read_le32(qts, MACIO_SCREAMER_CODEC),
                    ==, codec_write & ~(1U << 24));

    write_le32(qts, MACIO_SCREAMER_SWAP, 1);
    g_assert_cmphex(read_le32(qts, MACIO_SCREAMER_SWAP), ==, 1);

    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/ppc/macio/keylargo-timer-precision",
                   test_keylargo_timer_precision);
    qtest_add_func("/ppc/uninorth/mac99-boot-cpu",
                   test_mac99_uninorth_boot_cpu);
    qtest_add_func("/ppc/uninorth/sawtooth-registers",
                   test_sawtooth_uninorth_registers);
    qtest_add_func("/ppc/macio/sawtooth-screamer-registers",
                   test_sawtooth_screamer_registers);
    return g_test_run();
}
