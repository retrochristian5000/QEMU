/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include <stdint.h>
#include "hw/display/vga-palette.h"

int main(void)
{
    unsigned attr, page, select, mask, pixel, value;

    /* Same six-bit EGA color code, different VGA DAC pages. */
    assert(vga_palette_index16(0x2a, 0, 0, 0xff) == 0x2a);
    assert(vga_palette_index16(0x2a, 0, 0xc, 0xff) == 0xea);
    assert(vga_palette_index16(0x2a, 0x80, 5, 0xff) == 0x5a);
    assert(vga_palette_index16(0x2a, 0x80, 5, 0x0f) == 0x0a);

    for (attr = 0; attr < 64; attr++) {
        for (page = 0; page < 16; page++) {
            for (select = 0; select < 2; select++) {
                unsigned expected = (page / 4) * 64 +
                    (select ? (page % 4) * 16 : attr & 0x30) +
                    (attr % 16);

                for (mask = 0; mask < 256; mask++) {
                    assert(vga_palette_index16(attr, select * 128,
                                               page, mask) ==
                           (expected & mask));
                }
            }
        }
    }
    for (pixel = 0; pixel < 256; pixel++) {
        for (mask = 0; mask < 256; mask++) {
            assert(vga_palette_index256(pixel, mask) == (pixel & mask));
        }
    }
    for (value = 0; value < 256; value++) {
        unsigned six = value % 64;
        unsigned expanded = six * 4 + (six % 2) * 3;

        assert(vga_dac_component(value, false) == expanded);
        assert(vga_dac_component(value, true) == value);
    }
    assert(vga_dac_component(0x80, true) == 0x80);
    assert(vga_dac_component(0x80, false) == 0);
    return 0;
}
