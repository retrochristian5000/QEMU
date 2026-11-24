/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "hw/nvram/core99_bank.h"

static void test_inspect(void)
{
    uint8_t bank[CORE99_FLASH_BANK_SIZE] = { 0 };
    Core99BankInfo info;

    g_assert_cmpint(core99_bank_inspect(bank).status, ==,
                    CORE99_BANK_BAD_SIGNATURE);
    bank[0] = 0x5a;
    bank[3] = 2;
    g_assert_cmpint(core99_bank_inspect(bank).status, ==, CORE99_BANK_BAD_HEADER);
    bank[1] = 0x5c;
    g_assert_cmpint(core99_bank_inspect(bank).status, ==, CORE99_BANK_BAD_ADLER);
    /* Independent Adler-32 vector: 8172 zero bytes. */
    bank[0x10] = 0x1f;
    bank[0x11] = 0xec;
    bank[0x13] = 1;
    info = core99_bank_inspect(bank);
    g_assert_cmpint(info.status, ==, CORE99_BANK_VALID);
    g_assert_cmpuint(info.generation, ==, 0);
    bank[sizeof(bank) - 1] ^= 1;
    g_assert_cmpint(core99_bank_inspect(bank).status, ==, CORE99_BANK_BAD_ADLER);

    /* Dense data distinguishes standard and historical Linux checksums. */
    memset(bank + 0x14, 0xff, sizeof(bank) - 0x14);
    bank[0x10] = 0x0c;
    bank[0x11] = 0x8d;
    bank[0x12] = 0xcd;
    bank[0x13] = 0xe6;
    info = core99_bank_inspect(bank);
    g_assert_cmpint(info.status, ==, CORE99_BANK_VALID);
    g_assert_cmpuint(info.generation, ==, UINT32_MAX);
    bank[0x10] = 0x0b;
    bank[0x11] = 0xac;
    g_assert_cmpint(core99_bank_inspect(bank).status, ==, CORE99_BANK_LEGACY_ADLER);
}

static void test_select(void)
{
    Core99BankInfo banks[2] = { 0 };

    g_assert_cmpint(core99_bank_select(banks), ==, -1);
    banks[1].status = CORE99_BANK_VALID;
    g_assert_cmpint(core99_bank_select(banks), ==, 1);
    banks[0].status = CORE99_BANK_VALID;
    g_assert_cmpint(core99_bank_select(banks), ==, 0);
    banks[1].generation = 0x12345678;
    g_assert_cmpint(core99_bank_select(banks), ==, 1);
    banks[0].generation = UINT32_MAX;
    g_assert_cmpint(core99_bank_select(banks), ==, 0);
    banks[0].status = CORE99_BANK_BAD_ADLER;
    banks[1].status = CORE99_BANK_LEGACY_ADLER;
    g_assert_cmpint(core99_bank_select(banks), ==, 1);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/core99-bank/inspect", test_inspect);
    g_test_add_func("/core99-bank/select", test_select);
    return g_test_run();
}
