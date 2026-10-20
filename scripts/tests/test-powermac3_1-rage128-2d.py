#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Source contract for PowerMac3,1 Rage128 24-bpp and safe VRAM rectangles.

This guards code and boundary arithmetic; it is not a rendered-guest GPU test.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
source = (root / "hw/display/ati_2d.c").read_text(encoding="utf-8")
machine = (root / "hw/ppc/powermac3_1.c").read_text(encoding="utf-8")
regs = (root / "hw/display/ati_regs.h").read_text(encoding="utf-8")
assert 'pci_new(PCI_DEVFN(16, 0), "ati-rage128p")' in machine
assert 'qdev_prop_set_uint32(DEVICE(dev), "vgamem_mb", 16)' in machine
assert "#define DST_24BPP" in regs

rect = source.split("static bool ati_2d_rect_in_vram(", 1)[1].split(
    "static void ati_set_dirty(", 1)[0]
for token in ("rect->x < 0", "rect->y < 0", "rect->width <= 0",
              "rect->height <= 0", "stride <= 0",
              "offset >= ctx->vga->vram_size", "(uint64_t)offset +",
              "rect->height - 1", "rect->x + rect->width",
              "end <= ctx->vga->vram_size"):
    assert token in rect, token

setup = source.split("static void setup_2d_blt_ctx(", 1)[1].split(
    "static uint32_t make_filler(", 1)[0]
assert "ctx->src_offset = s->regs.src_offset;" in setup
assert "s->regs.dst_offset < s->vga.vram_size ?" in setup
assert "s->regs.src_offset < s->vga.vram_size ?" in setup

blit = source.split("static bool ati_2d_do_blt(", 1)[1].split(
    "void ati_2d_blt(ATIVGAState *s)", 1)[0]
for token in ("ati_2d_rect_in_vram(ctx, &vis_dst, ctx->dst_offset,",
              "ati_2d_rect_in_vram(ctx, &vis_src, ctx->src_offset,",
              "if (ctx->bpp == 24)",
              "pixel[0] = big_endian ? filler >> 16 : filler;",
              "pixel[2] = big_endian ? filler : filler >> 16;",
              "memcpy(&ctx->dst_bits[i], pixel, sizeof(pixel));",
              "pixman_fill(", "pixman_blt(",
              "stn_he_p(&ctx->dst_bits[i], bypp, filler);"):
    assert token in blit, token
assert "Fill blt unsupported in 24 bits" not in blit
assert "vram_end - bypp" not in blit

dirty = source.split("static void ati_set_dirty(", 1)[1].split(
    "static void setup_2d_blt_ctx(", 1)[0]
assert "qemu_rect_intersect(&ctx->dst, &ctx->scissor, &clipped);" in dirty
assert "ati_2d_rect_in_vram(ctx, &clipped" in dirty

def valid(offset, x, y, width, height, stride, bpp, vram):
    if x < 0 or y < 0 or width <= 0 or height <= 0 or stride <= 0:
        return False
    if offset >= vram:
        return False
    return (offset + (y + height - 1) * stride +
            (x + width) * (bpp // 8)) <= vram

assert valid(0, 0, 1, 1, 1, 3, 24, 6)
assert not valid(0, 0, 1, 2, 1, 3, 24, 6)
assert not valid(0, -1, 0, 1, 1, 3, 24, 6)
assert not valid(6, 0, 0, 1, 1, 3, 24, 6)
for pixel in (0x112233, 0, 0xffffff):
    le = bytes((pixel & 255, (pixel >> 8) & 255, (pixel >> 16) & 255))
    be = bytes(((pixel >> 16) & 255, (pixel >> 8) & 255, pixel & 255))
    assert le == pixel.to_bytes(3, "little")
    assert be == pixel.to_bytes(3, "big")

print("PowerMac3,1 Rage128 packed fill / VRAM bounds contract: ok")
