/*
 * V.42bis transparent-mode escape tests.
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include "chardev/modem-v42bis.h"

static void test_escape_vectors(void)
{
    static const uint8_t plain[] = { 0, 0, 51, 102, 153, 204, 255, 50 };
    static const uint8_t expected[] = {
        0, 1, 0, 51, 1, 102, 1, 153, 1, 204, 1, 255, 1, 50, 1,
    };
    uint8_t wire[2], escape = 0;
    size_t offset = 0;

    for (size_t i = 0; i < sizeof(plain); i++) {
        unsigned len = modem_v42bis_escape_encode(&escape, plain[i], wire);

        g_assert_cmpuint(offset + len, <=, sizeof(expected));
        g_assert_cmpmem(wire, len, expected + offset, len);
        offset += len;
    }
    g_assert_cmpuint(offset, ==, sizeof(expected));
    g_assert_cmpuint(escape, ==, 101);
}

static void test_escape_roundtrip(void)
{
    /* Exercise every pair of escape value and literal octet. */
    for (unsigned i = 0; i < 256; i++) {
        for (unsigned j = 0; j < 256; j++) {
            ModemV42bisTransparentRx rx = { .escape = i };
            uint8_t escape = i, wire[2], data = 0;
            unsigned len = modem_v42bis_escape_encode(&escape, j, wire);

            g_assert_cmpuint(len, ==, i == j ? 2 : 1);
            g_assert_cmpuint(escape, ==, i == j ? (i + 51) % 256 : i);

            if (len == 2) {
                g_assert_cmpint(modem_v42bis_transparent_decode(
                                    &rx, wire[0], &data),
                                ==, MODEM_V42BIS_MORE);
            }
            g_assert_cmpint(modem_v42bis_transparent_decode(
                                &rx, wire[len - 1], &data),
                            ==, MODEM_V42BIS_DATA);
            g_assert_cmpuint(data, ==, j);
            g_assert_cmpuint(rx.escape, ==, escape);
        }
    }
}

static void test_escape_control(void)
{
    ModemV42bisTransparentRx rx;
    uint8_t escape = 51, wire[2], data = 0xaa;

    modem_v42bis_transparent_init(&rx);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 0, &data),
                    ==, MODEM_V42BIS_MORE);
    g_assert_cmpuint(data, ==, 0xaa);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 1, &data),
                    ==, MODEM_V42BIS_DATA);
    g_assert_cmpuint(data, ==, 0);
    modem_v42bis_escape_reset(&escape, wire);
    g_assert_cmpuint(wire[0], ==, 51);
    g_assert_cmpuint(wire[1], ==, 2);
    g_assert_cmpuint(escape, ==, 0);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, wire[0], &data),
                    ==, MODEM_V42BIS_MORE);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, wire[1], &data),
                    ==, MODEM_V42BIS_RESET);
    g_assert_cmpuint(rx.escape, ==, 0);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 0, &data),
                    ==, MODEM_V42BIS_MORE);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 0, &data),
                    ==, MODEM_V42BIS_ECM);
    g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 'A', &data),
                    ==, MODEM_V42BIS_INVALID);

    for (unsigned i = 3; i <= 255; i++) {
        modem_v42bis_transparent_init(&rx);
        data = 0xaa;
        g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 0, &data),
                        ==, MODEM_V42BIS_MORE);
        g_assert_cmpint(modem_v42bis_transparent_decode(&rx, i, &data),
                        ==, MODEM_V42BIS_INVALID);
        g_assert_cmpuint(data, ==, 0xaa);
        g_assert_cmpint(modem_v42bis_transparent_decode(&rx, 'A', &data),
                        ==, MODEM_V42BIS_INVALID);
    }
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/modem/v42bis/escape-vectors", test_escape_vectors);
    g_test_add_func("/modem/v42bis/escape-roundtrip", test_escape_roundtrip);
    g_test_add_func("/modem/v42bis/escape-control", test_escape_control);
    return g_test_run();
}
