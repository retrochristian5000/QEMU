/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Standalone test: also runnable without a QEMU build or GLib. */
#undef NDEBUG
#include <assert.h>
#include <stdint.h>
#include "hw/display/vga-scanout.h"

int main(void)
{
    unsigned row, mode, max_scan;
    uint32_t addr = 0;

    /* CGA-compatible word addressing: 80 guest bytes per scanline.
     * The VGA plane layout maps each pair of guest bytes to four bytes.
     */
    for (row = 0; row < 200; row++) {
        uint32_t expected = (row / 2) * 160 + (row & 1) * 0x4000;

        assert(vga_scanline_address(addr, 2, row) == expected);
        if (vga_scanline_advance(2, row)) {
            addr += 160;
        }
    }
    /* Word and byte address modes select different internal address bits. */
    assert(vga_scanline_address(0x1234, 2, 1) == 0x5234);
    assert(vga_scanline_address(0x1234, 0x42, 1) == 0x9234);
    assert(vga_scanline_address(0xc123, 0, 0) == 0x0123);
    assert(vga_scanline_address(0x0123, 0, 3) == 0xc123);

    /* Native VGA never substitutes either row bit. */
    for (row = 0; row < 2048; row++) {
        assert(vga_scanline_address(0xc123, 3, row) == 0xc123);
        assert(vga_scanline_address(0xc123, 0x43, row) == 0xc123);
        assert(vga_scanline_advance(3, row));
    }
    for (mode = 0; mode < 256; mode++) {
        for (max_scan = 0; max_scan < 256; max_scan++) {
            unsigned expected = (mode & 1) ?
                ((max_scan & 31) + 1) * (1 + (max_scan >> 7)) - 1 :
                max_scan >> 7;

            assert(vga_scanline_repeat(mode, max_scan) == expected);
        }
    }
    return 0;
}
