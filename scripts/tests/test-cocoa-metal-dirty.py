#!/usr/bin/env python3
import pathlib
import shutil
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HEADER = ROOT / 'ui' / 'cocoa-metal-dirty.h'
SOURCE = ROOT / 'ui' / 'cocoa-metal.m'
COCOA_SOURCE = ROOT / 'ui' / 'cocoa.m'


class CocoaMetalDirtyRectTests(unittest.TestCase):
    def test_dirty_rect_conversion_and_clipping(self):
        self.assertTrue(HEADER.is_file(), 'dirty-rectangle helper is missing')
        cc = shutil.which('cc') or shutil.which('clang') or shutil.which('gcc')
        self.assertIsNotNone(cc, 'a C compiler is required for this test')
        program = r'''
#include <assert.h>
#include "ui/cocoa-metal-dirty.h"

int main(void)
{
    QEMUCocoaMetalDirtyRect r;

    assert(qemu_cocoa_metal_dirty_rect(640, 480, 10, 20, 110, 70, &r));
    assert(r.x == 10 && r.y == 410 && r.width == 100 && r.height == 50);

    assert(qemu_cocoa_metal_dirty_rect(640, 480, -5, -10, 50, 20, &r));
    assert(r.x == 0 && r.y == 460 && r.width == 50 && r.height == 20);

    assert(qemu_cocoa_metal_dirty_rect(640, 480, 0, 460, 640, 480, &r));
    assert(r.x == 0 && r.y == 0 && r.width == 640 && r.height == 20);

    assert(!qemu_cocoa_metal_dirty_rect(640, 480, 700, 10, 720, 20, &r));
    assert(!qemu_cocoa_metal_dirty_rect(640, 480, 20, 20, 20, 30, &r));
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='cocoa-metal-dirty-') as td:
            td = pathlib.Path(td)
            source = td / 'test.c'
            binary = td / 'test'
            source.write_text(program, encoding='utf-8')
            subprocess.run(
                [cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                 '-I', str(ROOT), str(source), '-o', str(binary)],
                check=True,
            )
            subprocess.run([str(binary)], check=True)

    def test_metal_renderer_uses_dirty_rectangles(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertIn('#include "ui/cocoa-metal-dirty.h"', text)
        self.assertIn('getRectsBeingDrawn', text)
        self.assertIn('textureImage != image', text)
        self.assertIn('qemu_cocoa_metal_dirty_rect', text)

    def test_refresh_rate_reapplied_after_application_launch(self):
        # updateUIInfo() is suppressed before AppKit finishes launching. If the
        # launch callback does not retry it, the listener keeps QEMU's 30 ms
        # default refresh interval, imposing an unintended ~33.3 fps ceiling.
        text = COCOA_SOURCE.read_text(encoding='utf-8')
        start = text.index('- (void)applicationDidFinishLaunching:')
        end = text.index('\n}\n', start)
        body = text[start:end]

        allow = body.index('allow_events = true;')
        refresh = body.index('[console.view updateUIInfo];')
        self.assertLess(allow, refresh)


if __name__ == '__main__':
    unittest.main()
