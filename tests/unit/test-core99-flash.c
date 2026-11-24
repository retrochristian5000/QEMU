/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "hw/nvram/core99_flash.h"

static void amd_unlock(Core99Flash *s, uint8_t *data, uint32_t bank,
                       uint8_t command)
{
    core99_flash_write(s, data, bank + 0x555, 0xaa);
    core99_flash_write(s, data, bank + 0x2aa, 0x55);
    core99_flash_write(s, data, bank + 0x555, command);
}

static void test_sharp_micron(void)
{
    Core99Flash s;
    uint8_t data[CORE99_FLASH_SIZE];
    uint32_t bank = CORE99_FLASH_BANK_SIZE;

    memset(data, 0xff, sizeof(data));
    core99_flash_reset(&s, CORE99_FLASH_SHARP_MICRON);
    g_assert_cmphex(core99_flash_write(&s, data, bank, 0x40), ==,
                    CORE99_FLASH_UNCHANGED);
    g_assert_cmphex(data[bank], ==, 0xff);
    g_assert_cmphex(core99_flash_write(&s, data, bank, 0x55), ==,
                    CORE99_FLASH_PROGRAMMED);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0x80);
    core99_flash_write(&s, data, bank, 0xff);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0x55);

    core99_flash_write(&s, data, bank, 0x40);
    core99_flash_write(&s, data, bank, 0xff);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0x90);
    g_assert_cmphex(data[bank], ==, 0x55);
    core99_flash_write(&s, data, bank, 0x50);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0x80);

    data[0] = 0x00;
    core99_flash_write(&s, data, bank, 0x20);
    core99_flash_write(&s, data, 0, 0xd0);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0xb0);
    g_assert_cmphex(data[0], ==, 0x00);
    g_assert_cmphex(data[bank], ==, 0x55);

    core99_flash_write(&s, data, bank, 0x50);
    core99_flash_write(&s, data, bank, 0x20);
    g_assert_cmphex(core99_flash_write(&s, data, bank, 0xd0), ==,
                    CORE99_FLASH_ERASED);
    core99_flash_write(&s, data, bank, 0x70);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0x80);
    core99_flash_write(&s, data, bank, 0xff);
    for (uint32_t i = bank; i < sizeof(data); i++) {
        g_assert_cmphex(data[i], ==, 0xff);
    }
    g_assert_cmphex(data[0], ==, 0x00);
}

static void test_amd(void)
{
    Core99Flash s;
    uint8_t data[CORE99_FLASH_SIZE];
    uint32_t bank = CORE99_FLASH_BANK_SIZE;
    uint8_t status;

    memset(data, 0xff, sizeof(data));
    core99_flash_reset(&s, CORE99_FLASH_AMD);

    core99_flash_write(&s, data, bank + 0x555, 0xaa);
    core99_flash_write(&s, data, bank + 0x2ab, 0x55);
    core99_flash_write(&s, data, bank + 0x555, 0xa0);
    core99_flash_write(&s, data, bank, 0x00);
    g_assert_cmphex(data[bank], ==, 0xff);

    amd_unlock(&s, data, bank, 0xa0);
    g_assert_cmphex(core99_flash_write(&s, data, bank, 0xf0), ==,
                    CORE99_FLASH_PROGRAMMED);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0xf0);

    amd_unlock(&s, data, bank, 0xa0);
    core99_flash_write(&s, data, bank, 0xff);
    status = core99_flash_read(&s, data, bank);
    g_assert_cmphex(status & 0xa0, ==, 0x20);
    g_assert_cmphex(status ^ core99_flash_read(&s, data, bank), ==, 0x40);
    core99_flash_write(&s, data, bank, 0xf0);
    g_assert_cmphex(core99_flash_read(&s, data, bank), ==, 0xf0);

    data[0] = 0;
    amd_unlock(&s, data, bank, 0x80);
    amd_unlock(&s, data, bank, 0x10);
    g_assert_cmphex(data[bank], ==, 0xf0);
    g_assert_cmphex(data[0], ==, 0);

    amd_unlock(&s, data, bank, 0x80);
    core99_flash_write(&s, data, bank + 0x555, 0xaa);
    core99_flash_write(&s, data, bank + 0x2aa, 0x55);
    g_assert_cmphex(core99_flash_write(&s, data, bank, 0x30), ==,
                    CORE99_FLASH_ERASED);
    for (uint32_t i = bank; i < sizeof(data); i++) {
        g_assert_cmphex(data[i], ==, 0xff);
    }
    g_assert_cmphex(data[0], ==, 0);
    g_assert_cmphex(data[bank + 0x555], ==, 0xff);
}

static void test_reset_and_bounds(void)
{
    Core99Flash s;
    uint8_t data[CORE99_FLASH_SIZE];

    memset(data, 0x55, sizeof(data));
    core99_flash_reset(&s, CORE99_FLASH_SHARP_MICRON);
    core99_flash_write(&s, data, 0, 0x40);
    core99_flash_reset(&s, CORE99_FLASH_SHARP_MICRON);
    g_assert_cmphex(core99_flash_read(&s, data, 0), ==, 0x55);
    g_assert_cmphex(core99_flash_write(&s, data, sizeof(data), 0x40), ==,
                    CORE99_FLASH_UNCHANGED);
    g_assert_cmphex(core99_flash_read(&s, data, UINT32_MAX), ==, 0xff);
    g_assert_cmphex(data[0], ==, 0x55);
    core99_flash_reset(&s, CORE99_FLASH_AMD);
    amd_unlock(&s, data, 0, 0xa0);
    core99_flash_reset(&s, CORE99_FLASH_AMD);
    core99_flash_write(&s, data, 0, 0x00);
    g_assert_cmphex(data[0], ==, 0x55);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/core99-flash/sharp-micron", test_sharp_micron);
    g_test_add_func("/core99-flash/amd", test_amd);
    g_test_add_func("/core99-flash/reset-bounds", test_reset_and_bounds);
    return g_test_run();
}
