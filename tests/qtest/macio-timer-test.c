/*
 * QTest testcase for the NewWorld PowerMac KeyLargo timer
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "libqtest.h"
#include "hw/pci/pci.h"
#include "qemu/bswap.h"

#define UNINORTH_CONFIG_ADDR 0xf2800000
#define UNINORTH_CONFIG_DATA 0xf2c00000
#define MACIO_BAR_BASE       0x80000000
#define MACIO_TIMER_LOW      (MACIO_BAR_BASE + 0x15038)
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

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/ppc/macio/keylargo-timer-precision",
                   test_keylargo_timer_precision);
    return g_test_run();
}
