/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "hw/block/dvdrom.h"

static void test_dvd_structure(void)
{
    uint8_t buf[2053];
    static const uint8_t formats[] = { 0, 1, 4, 0xff };
    static const int lengths[] = { 2052, 8, 2052, 20 };
    size_t i, j;

    for (i = 0; i < ARRAY_SIZE(formats); i++) {
        memset(buf, 0xa5, sizeof(buf));
        g_assert_cmpint(dvdrom_read_structure(1000000, 0, formats[i],
                                             buf, sizeof(buf)), ==, lengths[i]);
        g_assert_cmpuint(lduw_be_p(buf), ==, lengths[i] - 2);
        g_assert_cmphex(buf[lengths[i]], ==, 0xa5);
        if (formats[i] == 0) {
            g_assert_cmphex(buf[4], ==, 1);
            g_assert_cmpuint(ldl_be_p(buf + 8), ==, 0);
            g_assert_cmpuint(ldl_be_p(buf + 12), ==, 999999);
            g_assert_cmpuint(ldl_be_p(buf + 16), ==, 999999);
            for (j = 20; j < lengths[i]; j++) {
                g_assert_cmphex(buf[j], ==, 0);
            }
        }
        memset(buf, 0xa5, sizeof(buf));
        g_assert_cmpint(dvdrom_read_structure(1000000, 0, formats[i],
                                             buf, lengths[i] - 1), ==, -ENOSPC);
        for (j = 0; j < sizeof(buf); j++) {
            g_assert_cmphex(buf[j], ==, 0xa5);
        }
    }

    g_assert_cmpint(dvdrom_read_structure(1000000, 1, 0, buf, sizeof(buf)),
                    ==, -EINVAL);
    g_assert_cmpint(dvdrom_read_structure(0, 0, 0, buf, sizeof(buf)),
                    ==, -ENOMEDIUM);
    g_assert_cmpint(dvdrom_read_structure(1000000, 0, 3, buf, sizeof(buf)),
                    ==, -EINVAL);
    g_assert_cmpint(dvdrom_read_structure(1000000, 0, 0x80, buf, sizeof(buf)),
                    ==, -EINVAL);
    g_assert_cmpint(dvdrom_read_structure(0, 0, 0xff, buf, sizeof(buf)),
                    ==, 20);
    g_assert_cmphex(buf[4], ==, 0);
    g_assert_cmphex(buf[8], ==, 1);
    g_assert_cmphex(buf[12], ==, 3);
    g_assert_cmphex(buf[16], ==, 4);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/dvdrom/structure", test_dvd_structure);
    return g_test_run();
}
