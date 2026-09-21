#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
vga = (ROOT / "hw/display/vga.c").read_text(encoding="utf-8")
macfb = (ROOT / "hw/display/macfb.c").read_text(encoding="utf-8")
sm501 = (ROOT / "hw/display/sm501.c").read_text(encoding="utf-8")
apple_gfx = (ROOT / "hw/display/apple-gfx.m").read_text(encoding="utf-8")
apple_gfx_mmio = (ROOT / "hw/display/apple-gfx-mmio.m").read_text(encoding="utf-8")
cocoa_metal = (ROOT / "ui/cocoa-metal.m").read_text(encoding="utf-8")

# Scanline renderers run once for each dirty line. Keep their stable mode
# selection as data and dispatch to direct functions so arm64e does not pay a
# pointer-authenticated indirect call for every rendered scanline.
for token in ("vga_draw_line_func", "vga_draw_line_table"):
    assert token not in vga, f"VGA scanline pointer dispatch regressed: {token}"
for token in (
    "static inline void *vga_draw_line_dispatch(",
    "return vga_draw_line32_le(",
    "p = vga_draw_line_dispatch(v, s, d, addr, width, hpel);",
):
    assert token in vga, f"missing VGA direct scanline dispatch: {token}"

for token in ("macfb_draw_line_func", "macfb_draw_line_table"):
    assert token not in macfb, f"MacFB scanline pointer dispatch regressed: {token}"
for token in (
    "typedef enum MacFBDrawLine",
    "static inline void macfb_draw_line(",
    "macfb_draw_line(draw_line, s, data_display, page, s->width);",
):
    assert token in macfb, f"missing MacFB direct scanline dispatch: {token}"

for token in ("typedef void draw_line_func", "typedef void draw_hwc_line_func"):
    assert token not in sm501, f"SM501 scanline pointer dispatch regressed: {token}"
for token in (
    "static inline void draw_line_32(",
    "draw_line_32(src_bpp, d, s->local_mem + offset, width, palette);",
    "draw_hwc_line_32(d, hwc_src, width, hwc_palette, c_x,",
):
    assert token in sm501, f"missing SM501 direct scanline dispatch: {token}"

# Cocoa/Metal must leave code-pointer signing to Clang, dyld and the Objective-C
# runtime. Erasing a code pointer through an integer/void* or manually changing
# its PAC schema here would make the display path both fragile and slower.
for token in ("ptrauth_strip", "ptrauth_sign_unauthenticated", "objc_msgSend"):
    assert token not in cocoa_metal, f"manual/erased Cocoa code-pointer ABI: {token}"
assert "(QEMUMetalCreateSystemDefaultDevice)dlsym" in cocoa_metal
assert "(QEMUCocoaInitIMP)method_getImplementation(initMethod)" in cocoa_metal
assert "(QEMUCocoaDrawIMP)method_getImplementation(drawMethod)" in cocoa_metal

# GCD callbacks stay as correctly typed named functions. libdispatch/Clang can
# then apply the platform callback pointer-authentication schema themselves.
for token in (
    "dispatch_async_f(queue, &job, apple_gfx_do_read);",
    "dispatch_async_f(queue, &job, apple_gfx_do_write);",
):
    assert token in apple_gfx, f"missing typed AppleGFX GCD callback: {token}"
for token in (
    "dispatch_async_f(queue, &job, iosfc_do_read);",
    "dispatch_async_f(queue, &job, iosfc_do_write);",
):
    assert token in apple_gfx_mmio, f"missing typed IOSFC GCD callback: {token}"

for text in (apple_gfx, apple_gfx_mmio):
    assert "ptrauth_strip" not in text
    assert "ptrauth_sign_unauthenticated" not in text

# AppleGFX on arm64e/Apple Silicon should render into unified storage that is
# simultaneously the QEMU DisplaySurface.  Keep getBytes() as a fallback for
# hosts where Metal cannot create the linear shared texture.
for token in (
    "#if defined(__arm64__) && defined(__PTRAUTH__)",
    "minimumLinearTextureAlignmentForPixelFormat:",
    "newBufferWithLength:buffer_length",
    "newTextureWithDescriptor:texture_descriptor",
    "qemu_create_displaysurface_from(width, height,",
    "pixman_image_set_destroy_function(surface->image,",
    "s->using_shared_surface_texture = shared_surface;",
    "if (!s->using_shared_surface_texture)",
):
    assert token in apple_gfx, f"missing AppleGFX shared-surface contract: {token}"

assert apple_gfx.count("copy_mtl_texture_to_surface_mem(") == 2, (
    "AppleGFX full-frame readback should exist only as one helper and one "
    "fallback call"
)

print("ARM64e display hot-path and callback ABI audit passed")
