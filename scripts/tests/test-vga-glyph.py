#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class VGAGlyphTests(unittest.TestCase):
    def test_glyph_ninth_dot_and_pixel_expansion(self):
        # Exercise the production helpers without linking the full emulator.
        helpers = (ROOT / 'hw/display/vga-helpers.h').read_text()
        start = helpers.index('static inline bool vga_glyph_duplicate_ninth(')
        end = helpers.index('/*\n * 4 color mode', start)
        program = '''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "hw/display/vga_regs.h"

static uint8_t expand4to8[16];
''' + helpers[start:end] + r'''
int main(void)
{
    const uint32_t fg = 0x00ffffff, bg = 0x00010203;
    uint8_t font[8] = { 0x81, 0xaa, 0xbb, 0xcc, 0x42 };
    uint32_t pixels[2][20];
    for (unsigned ch = 0; ch < 256; ch++) {
        for (unsigned mode = 0; mode < 256; mode++) {
            bool expected = (mode & 4) && ch >= 0xc0 && ch <= 0xdf;
            assert(vga_glyph_duplicate_ninth(ch, mode) == expected);
        }
    }
    for (unsigned n = 0; n < 16; n++) {
        for (unsigned bit = 0; bit < 4; bit++) {
            if (n & (1u << bit)) {
                expand4to8[n] |= 3u << (bit * 2);
            }
        }
    }
    memset(pixels, 0, sizeof(pixels));
    vga_draw_glyph8((uint8_t *)pixels, sizeof(pixels[0]), font, 2, fg, bg);
    for (unsigned row = 0; row < 2; row++) {
        for (unsigned x = 0; x < 8; x++) {
            assert(pixels[row][x] ==
                   ((font[row * 4] & (0x80u >> x)) ? fg : bg));
        }
        assert(pixels[row][8] == 0);
    }
    for (unsigned dup = 0; dup < 2; dup++) {
        memset(pixels, 0, sizeof(pixels));
        vga_draw_glyph9((uint8_t *)pixels, sizeof(pixels[0]), font, 2,
                        fg, bg, dup);
        assert(pixels[0][8] == (dup ? fg : bg));
        assert(pixels[1][8] == bg);
        assert(pixels[0][9] == 0 && pixels[1][9] == 0);
    }
    memset(pixels, 0, sizeof(pixels));
    vga_draw_glyph16((uint8_t *)pixels, sizeof(pixels[0]), font, 2, fg, bg);
    for (unsigned row = 0; row < 2; row++) {
        for (unsigned x = 0; x < 16; x++) {
            assert(pixels[row][x] ==
                   ((font[row * 4] & (0x80u >> (x / 2))) ? fg : bg));
        }
        assert(pixels[row][16] == 0);
    }
    return 0;
}
'''
        cc = shutil.which('cc') or shutil.which('clang')
        self.assertIsNotNone(cc)
        with tempfile.TemporaryDirectory(prefix='vga-glyph-') as temp:
            source = pathlib.Path(temp) / 'test.c'
            binary = pathlib.Path(temp) / 'test'
            source.write_text(program)
            subprocess.run([cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT), str(source), '-o', str(binary)],
                           check=True)
            subprocess.run([str(binary)], check=True)

    def test_register_changes_invalidate_text_pixels(self):
        for name in ('vga.c', 'cirrus_vga.c'):
            source = (ROOT / 'hw/display' / name).read_text()
            start = source.index('case VGA_ATC_MODE:')
            end = source.index('break;', start)
            body = source[start:end]
            self.assertIn('VGA_ATC_MODE_LINE_GRAPHICS | VGA_ATC_MODE_BLINK', body)
            self.assertIn('s->full_update_gfx = 1;', body)
        source = (ROOT / 'hw/display/vga.c').read_text()
        start = source.index('static void vga_draw_text(')
        body = source[start:]
        self.assertLess(body.index('> CH_ATTR_SIZE'),
                        body.index('s->plane_updated = 0;'))
        self.assertIn('dup9 = vga_glyph_duplicate_ninth(ch,', body)


if __name__ == '__main__':
    unittest.main()
