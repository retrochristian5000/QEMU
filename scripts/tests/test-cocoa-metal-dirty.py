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

    def test_arm64e_runtime_dispatch_is_typed(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertNotIn('objc_msgSend', text)
        self.assertNotIn('#import <objc/message.h>', text)
        self.assertIn('@protocol QEMUMetalLayerRuntime', text)
        self.assertIn('@protocol QEMUMetalBlitEncoderRuntime', text)
        self.assertIn('CocoaConsole *console', text)
        self.assertIn('(QEMUMetalCreateSystemDefaultDevice)dlsym', text)
        self.assertNotIn('ptrauth_strip', text)
        self.assertNotIn('ptrauth_sign_unauthenticated', text)

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


    def test_multihead_selection_keeps_one_window_per_graphic_console(self):
        text = COCOA_SOURCE.read_text(encoding='utf-8')
        start = text.index('- (void) selectConsoleLocked:(unsigned int)index')
        end = text.index('\n- (void) hideCursor', start)
        body = text[start:end]

        # View-menu and Ctrl+Alt+1..9 selection must focus existing graphic
        # windows before any listener is detached or rebound.
        focus = body.index('view->console->con == con')
        rebind = body.index('qemu_console_unregister_listener(&console->dcl)')
        self.assertLess(focus, rebind)
        self.assertIn('[window makeKeyAndOrderFront:self];', body[:rebind])
        self.assertIn('if (!console->is_primary)', body[:rebind])
        self.assertIn('view->console->is_primary', body[:rebind])
        self.assertIn('[view selectConsoleLocked:index];', body[:rebind])

        # An extra guest head must be represented by an independent listener
        # and view, not by stealing the primary window's console.
        self.assertIn('qemu_console_register_listener(guest, &extra->dcl,',
                      text)
        self.assertIn('qkbd_state_init(extra->dcl.con)', text)

    def test_extra_windows_stay_within_physical_monitor_bounds(self):
        text = COCOA_SOURCE.read_text(encoding='utf-8')
        start = text.index('- (void)createAdditionalConsoleWindows\n{')
        end = text.index('\n- (void)showConsoleWindow:', start)
        body = text[start:end]

        self.assertIn('NSArray *screens = [NSScreen screens];', body)
        self.assertIn('(1 + extraConsoles->len) % screenCount', body)
        self.assertIn('NSMinX(visible) + MIN(roomX, MAX(0,', body)
        self.assertIn('NSMinY(visible) + MIN(roomY, MAX(0,', body)

        # Screen rectangles can begin at negative desktop coordinates.
        # For a window fitting on the physical screen, both axes must stay
        # inside visibleFrame, including when the cascade exceeds room.
        for left, bottom, width, height, w, h, cascade in (
            (-1920, 0, 1920, 1080, 640, 480, 24),
            (0, -900, 1440, 900, 640, 480, 120),
            (0, 0, 800, 600, 640, 480, 250),
            (-1024, -768, 1024, 768, 800, 600, 300),
        ):
            room_x, room_y = max(0, width - w), max(0, height - h)
            x = left + min(room_x, max(0, room_x / 2 + cascade))
            y = bottom + min(room_y, max(0, room_y / 2 - cascade))
            self.assertGreaterEqual(x, left)
            self.assertLessEqual(x + w, left + width)
            self.assertGreaterEqual(y, bottom)
            self.assertLessEqual(y + h, bottom + height)


    def test_metal_default_device_balances_non_arc_ownership(self):
        text = SOURCE.read_text(encoding='utf-8')
        start = text.index('    device = metal_create_default_device();')
        end = text.index('    metalQueue = [metalDevice newCommandQueue];', start)
        setup = text[start:end]

        # The Metal Create function returns a +1 reference. Keep that
        # single ownership until -dealloc, rather than retaining twice.
        self.assertIn('metalDevice = device;', setup)
        self.assertNotIn('[device retain]', setup)
        self.assertIn('[metalDevice release];', text)

    def test_metal_layer_matches_srgb_and_validates_drawable(self):
        text = SOURCE.read_text(encoding='utf-8')
        self.assertIn('CGColorSpaceCreateWithName(kCGColorSpaceSRGB)', text)
        self.assertIn('[layer setColorspace:colorspace];', text)
        self.assertIn('[metalLayer setContentsScale:backing.width];', text)
        self.assertIn('CGSizeEqualToSize(', text)
        self.assertIn('[drawableTexture width] != (NSUInteger)width', text)
        self.assertIn('[drawableTexture height] != (NSUInteger)height', text)
        self.assertIn('[drawableTexture pixelFormat] !=', text)
        self.assertLess(text.index('[drawableTexture width] != (NSUInteger)width'),
                        text.index('[commandBuffer presentDrawable:drawable];'))

    def test_appkit_window_removal_and_retina_repaint(self):
        text = COCOA_SOURCE.read_text(encoding='utf-8')
        start = text.index('- (void) viewDidMoveToWindow\n{')
        end = text.index('\n- (void) selectConsoleLocked:', start)
        body = text[start:end]
        self.assertIn('[super viewDidMoveToWindow];', body)
        self.assertIn('if ([self window])', body)
        self.assertIn('[self setNeedsDisplay:YES];', body)
        self.assertIn('- (void) viewDidChangeBackingProperties', body)
        self.assertIn('[super viewDidChangeBackingProperties];', body)


if __name__ == '__main__':
    unittest.main()
