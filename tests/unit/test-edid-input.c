/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "hw/display/edid.h"

static void check_edid(const uint8_t *edid, size_t size)
{
    size_t offset, i;

    g_assert_cmpuint(size % 128, ==, 0);
    g_assert_cmpuint(size, ==, (edid[126] + 1) * 128);

    for (offset = 0; offset < size; offset += 128) {
        unsigned sum = 0;

        for (i = 0; i < 128; i++) {
            sum += edid[offset + i];
        }
        g_assert_cmpuint(sum & 0xff, ==, 0);
    }
}

static void test_edid_input(void)
{
    static const struct {
        QemuEdidInput input;
        uint8_t video_input;
        uint8_t features;
    } cases[] = {
        { QEMU_EDID_INPUT_DISPLAYPORT, 0xa5, 0x06 },
        { QEMU_EDID_INPUT_VGA, 0x08, 0x0e },
        { QEMU_EDID_INPUT_HDMI_A, 0xa2, 0x06 },
    };
    static const size_t sizes[] = { 128, 256, 384 };
    size_t i, j, k;

    for (i = 0; i < ARRAY_SIZE(sizes); i++) {
        uint8_t legacy[384] = { 0 };
        qemu_edid_info info = { 0 };
        size_t used;

        qemu_edid_generate(legacy, sizes[i], &info);
        used = qemu_edid_size(legacy);
        g_assert_cmpuint(used, <=, sizes[i]);
        check_edid(legacy, used);

        for (j = 0; j < ARRAY_SIZE(cases); j++) {
            uint8_t edid[384] = { 0 };
            qemu_edid_info profile = { 0 };

            qemu_edid_generate_for_input(edid, sizes[i], &profile,
                                         cases[j].input);
            g_assert_cmpuint(qemu_edid_size(edid), ==, used);
            g_assert_cmphex(edid[20], ==, cases[j].video_input);
            g_assert_cmphex(edid[24], ==, cases[j].features);
            check_edid(edid, used);

            /* Only input parameters, features and base checksum may differ. */
            for (k = 0; k < sizeof(edid); k++) {
                if (k != 20 && k != 24 && k != 127) {
                    g_assert_cmphex(edid[k], ==, legacy[k]);
                }
            }

            if (cases[j].input == QEMU_EDID_INPUT_DISPLAYPORT) {
                g_assert_cmpmem(edid, sizeof(edid), legacy, sizeof(legacy));
            }
        }
    }
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/edid/input-profiles", test_edid_input);
    return g_test_run();
}
