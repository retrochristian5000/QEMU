#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return (ROOT / path).read_text()


def write(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def replace_once(path, old, new):
    text = read(path)
    if text.count(old) != 1:
        raise SystemExit(f"{path}: expected one match, found {text.count(old)}")
    write(path, text.replace(old, new, 1))


def insert_after_line(path, marker, new_line):
    lines = read(path).splitlines()
    matches = [i for i, line in enumerate(lines) if marker in line]
    if len(matches) != 1:
        raise SystemExit(f"{path}: marker {marker!r} matched {len(matches)} lines")
    lines.insert(matches[0] + 1, new_line)
    write(path, "\n".join(lines) + "\n")


def stage_tests():
    replace_once(
        "hw/display/Kconfig",
        "config VGA_ISA\n    bool\n    depends on ISA_BUS\n    select VGA\n\n",
        "config VGA_ISA\n    bool\n    depends on ISA_BUS\n    select VGA\n\n"
        "config CGA\n    bool\n    depends on ISA_BUS\n\n",
    )

    replace_once(
        "hw/i386/Kconfig",
        "config X86_16BIT_MACHINE\n    bool\n    depends on I386\n    select ISA_BUS\n    select SERIAL_ISA\n",
        "config X86_16BIT_MACHINE\n    bool\n    depends on I386\n    select ISA_BUS\n    select CGA\n    select SERIAL_ISA\n",
    )
    insert_after_line("hw/i386/Kconfig", "imply APPLESMC", "    imply CGA")

    insert_after_line(
        "tests/qtest/meson.build",
        "CONFIG_FDC_ISA') ? ['fdc-test']",
        "  (config_all_devices.has_key('CONFIG_CGA') ? ['cga-test'] : []) +                      \\",
    )

    write("tests/qtest/cga-test.c", r'''/*
 * QTest testcase for the IBM Color/Graphics Adapter.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "libqtest.h"

#define CGA_MEM_BASE       0x000b8000
#define CGA_MEM_MIRROR     0x000bc000
#define CGA_CRTC_INDEX     0x03d4
#define CGA_CRTC_DATA      0x03d5
#define CGA_STATUS         0x03da
#define CGA_LIGHTPEN_CLEAR 0x03db
#define CGA_LIGHTPEN_SET   0x03dc

static void test_cga_registers(void)
{
    QTestState *qts;
    uint8_t status;

    qts = qtest_init("-machine pc -nodefaults -display none -device isa-cga");

    /* A2/A1 are not decoded for the 6845 address/data pair. */
    qtest_outb(qts, 0x03d0, 12);
    qtest_outb(qts, 0x03d1, 0x12);
    qtest_outb(qts, CGA_CRTC_INDEX, 12);
    g_assert_cmphex(qtest_inb(qts, CGA_CRTC_DATA), ==, 0x12);

    status = qtest_inb(qts, CGA_STATUS);
    g_assert_cmphex(status & 0xf0, ==, 0x00);
    g_assert_cmphex(status & 0x04, ==, 0x04); /* no light-pen switch */

    qtest_outb(qts, CGA_LIGHTPEN_SET, 0);
    g_assert_cmphex(qtest_inb(qts, CGA_STATUS) & 0x02, ==, 0x02);
    qtest_outb(qts, CGA_LIGHTPEN_CLEAR, 0);
    g_assert_cmphex(qtest_inb(qts, CGA_STATUS) & 0x02, ==, 0x00);

    qtest_quit(qts);
}

static void test_cga_vram_mirror(void)
{
    static const uint8_t pattern[] = { 0x12, 0x34, 0x56, 0x78 };
    uint8_t mirror[sizeof(pattern)] = { 0 };
    QTestState *qts;

    qts = qtest_init("-machine pc -nodefaults -display none -device isa-cga");
    qtest_memwrite(qts, CGA_MEM_BASE, pattern, sizeof(pattern));
    qtest_memread(qts, CGA_MEM_MIRROR, mirror, sizeof(mirror));
    g_assert_cmpmem(pattern, sizeof(pattern), mirror, sizeof(mirror));
    qtest_quit(qts);
}

static void test_cga_vga_selector(void)
{
    QTestState *qts;

    /* A PCI PC must route -vga cga to the ISA adapter, not pci_vga_init(). */
    qts = qtest_init("-machine pc -nodefaults -display none -vga cga");
    qtest_outb(qts, CGA_CRTC_INDEX, 13);
    qtest_outb(qts, CGA_CRTC_DATA, 0x5a);
    g_assert_cmphex(qtest_inb(qts, CGA_CRTC_DATA), ==, 0x5a);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/display/cga/registers", test_cga_registers);
    qtest_add_func("/display/cga/vram-mirror", test_cga_vram_mirror);
    qtest_add_func("/display/cga/vga-selector", test_cga_vga_selector);
    return g_test_run();
}
''')

    write("docs/superpowers/specs/2026-08-27-ibm-cga-design.md", r'''# IBM CGA Device Design

## Scope

Add a standalone IBM Color/Graphics Adapter instead of treating CGA as a VGA mode. The device is an ISA display adapter with no IRQ and no DMA.

## Guest-visible ABI

- QOM type: `isa-cga`.
- Legacy selector: `-vga cga`.
- 16 KiB display RAM at `0xB8000`, mirrored at `0xBC000`.
- Motorola 6845-compatible index/data decode at `0x3D0`-`0x3D7`; A2/A1 are not decoded, so even ports select the index latch and odd ports select data.
- Mode control at `0x3D8`, color select at `0x3D9`, status at `0x3DA`, light-pen clear at `0x3DB`, and light-pen preset at `0x3DC`.
- Migration section name: `isa-cga`; RAM migration name: `isa-cga.vram`. These names are ABI-stable once shipped.

## Display behavior

Render the digital RGBI output at a 640x200 host surface. Implement 40x25 and 80x25 alphanumeric modes, 320x200 four-color graphics, and 640x200 two-color graphics. The character generator is not guest-readable; the first implementation compresses QEMU's existing 8x16 VGA font to an 8x8 cell so no new firmware/font blob is required.

The first implementation does not emulate composite artifact colors, CGA snow/contention, or a host pointer as a physical light pen. The light-pen latch/register ABI is present and testable.

## Timing

Status register bit 0 reports a safe regen-buffer access interval during horizontal/vertical blanking. Bit 3 reports vertical retrace. Baseline timing uses the CGA 912x262 field shape at 60 Hz; later work may derive timing from every programmed 6845 parameter without changing the I/O ABI.

## Integration

`CONFIG_CGA` depends on `ISA_BUS`. PC machines imply it; the dedicated original-x86 target selects it. `pc_vga_init()` routes `VGA_CGA` to the ISA bus even on PCI PC machines. The original 8086/8088 machine instantiates it when `-vga cga` is selected.

## Tests

QTest must prove the 6845 alias decode, readable CRTC state used for diagnostics, status/light-pen behavior, the B8000/BC000 mirror, and `-vga cga` routing on a PCI PC machine.
''')

    write("docs/superpowers/plans/2026-08-27-ibm-cga.md", r'''# IBM CGA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a guest-visible IBM CGA ISA display adapter and expose it through both `-device isa-cga` and `-vga cga`.

**Architecture:** Use a dedicated ISA device with its own 16 KiB RAM, 6845/CGA I/O registers, timing status, and RGBI renderer. Do not reuse `VGACommonState`, VBE, a VGA option ROM, IRQ, or DMA.

**Tech Stack:** QEMU QOM/qdev, ISA MemoryRegion I/O, QEMU display console, migration VMState, qtest/Meson.

**Spec:** `docs/superpowers/specs/2026-08-27-ibm-cga-design.md`

## Global Constraints

- Preserve the IBM CGA I/O and memory ABI described in the spec.
- Keep composite artifact simulation and snow/contention out of this first slice.
- Keep migration identifiers `isa-cga` and `isa-cga.vram` stable.
- Use tests before production code.

---

### Task 1: Establish the failing hardware test

**Files:** `hw/display/Kconfig`, `hw/i386/Kconfig`, `tests/qtest/cga-test.c`, `tests/qtest/meson.build`

**Interfaces:** The test launches `-device isa-cga`, accesses ports `0x3D0`-`0x3DC`, and reads/writes `0xB8000`/`0xBC000`.

- [ ] Add `CONFIG_CGA` and enable it for PC/original-x86 builds.
- [ ] Add `cga-test` to the i386 qtest list.
- [ ] Build `qemu-system-i386` and `tests/qtest/cga-test`.
- [ ] Run `meson test -C build-cga --print-errorlogs cga-test`; expected RED is failure because `isa-cga` does not exist.

### Task 2: Implement the adapter

**Files:** `hw/display/cga.c`, `hw/display/meson.build`

**Interfaces:** Produce QOM type `isa-cga`, migration section `isa-cga`, RAM section `isa-cga.vram`, I/O base `0x3D0`, and display RAM at `0xB8000` with the `0xBC000` mirror.

- [ ] Implement 6845 register aliases, mode/color/status/light-pen registers, and migration state.
- [ ] Implement RGBI text, 320x200, and 640x200 rendering.
- [ ] Register the source under `CONFIG_CGA`.

### Task 3: Integrate command-line selection

**Files:** `include/system/system.h`, `system/vl.c`, `hw/isa/isa-bus.c`, `hw/i386/pc.c`, `hw/i386/x86-16bit.c`

**Interfaces:** Add enum value `VGA_CGA`; `-vga cga` resolves to `isa-cga` on ISA-capable x86 machines.

- [ ] Add `VGA_CGA` and the `cga` selector metadata.
- [ ] Add `isa-cga` to default-display suppression.
- [ ] Route CGA through `isa_vga_init()` on PCI PCs and original-x86 machines.

### Task 4: Verify and commit

- [ ] Run `git diff --check`.
- [ ] Build `qemu-system-i386`, `qemu-system-x86`, and `tests/qtest/cga-test`.
- [ ] Run `meson test -C build-cga --print-errorlogs cga-test`; expected GREEN is PASS.
- [ ] Verify `qemu-system-i386 -vga help` lists `cga`.
- [ ] Commit as `display: add IBM CGA ISA adapter`.
''')


def production():
    insert_after_line(
        "hw/display/meson.build",
        "CONFIG_VGA_ISA', if_true: files('vga-isa.c')",
        "system_ss.add(when: 'CONFIG_CGA', if_true: files('cga.c'))",
    )

    replace_once(
        "include/system/system.h",
        "    VGA_NONE, VGA_STD, VGA_CIRRUS, VGA_VMWARE, VGA_XENFB, VGA_QXL,\n",
        "    VGA_NONE, VGA_STD, VGA_CGA, VGA_CIRRUS, VGA_VMWARE, VGA_XENFB, VGA_QXL,\n",
    )

    insert_after_line(
        "system/vl.c",
        '{ .driver = "isa-vga",              .flag = &default_vga       },',
        '    { .driver = "isa-cga",              .flag = &default_vga       },',
    )
    replace_once(
        "system/vl.c",
        "    [VGA_STD] = {\n        .opt_name = \"std\",\n        .name = \"standard VGA\",\n        .class_names = { \"VGA\", \"isa-vga\" },\n    },\n",
        "    [VGA_STD] = {\n        .opt_name = \"std\",\n        .name = \"standard VGA\",\n        .class_names = { \"VGA\", \"isa-vga\" },\n    },\n"
        "    [VGA_CGA] = {\n        .opt_name = \"cga\",\n        .name = \"IBM Color/Graphics Adapter\",\n        .class_names = { \"isa-cga\" },\n    },\n",
    )

    replace_once(
        "hw/isa/isa-bus.c",
        "    switch (vga_interface_type) {\n    case VGA_CIRRUS:\n",
        "    switch (vga_interface_type) {\n    case VGA_CGA:\n        return isa_create_simple(bus, \"isa-cga\");\n    case VGA_CIRRUS:\n",
    )

    replace_once(
        "hw/i386/pc.c",
        "    if (pci_bus) {\n        PCIDevice *pcidev = pci_vga_init(pci_bus);\n        dev = pcidev ? &pcidev->qdev : NULL;\n    } else if (isa_bus) {\n",
        "    if (pci_bus && vga_interface_type != VGA_CGA) {\n        PCIDevice *pcidev = pci_vga_init(pci_bus);\n        dev = pcidev ? &pcidev->qdev : NULL;\n    } else if (isa_bus) {\n",
    )

    insert_after_line("hw/i386/x86-16bit.c", '#include "system/qtest.h"', '#include "system/system.h"')
    insert_after_line(
        "hw/i386/x86-16bit.c",
        "serial_hds_isa_init(isa_bus, 0, 1);",
        "    if (vga_interface_type == VGA_CGA) {\n        isa_vga_init(isa_bus);\n    }",
    )

    write("hw/display/cga.c", r'''/*
 * IBM Color/Graphics Adapter (CGA)
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qemu/units.h"
#include "hw/isa/isa.h"
#include "migration/vmstate.h"
#include "system/memory.h"
#include "ui/console.h"
#include "ui/pixel_ops.h"
#include "ui/vgafont.h"
#include "qom/object.h"

#define TYPE_ISA_CGA "isa-cga"
OBJECT_DECLARE_SIMPLE_TYPE(CGAState, ISA_CGA)

#define CGA_VRAM_SIZE       (16 * KiB)
#define CGA_MEM_BASE        0x000b8000
#define CGA_MEM_MIRROR      0x000bc000
#define CGA_IO_BASE         0x03d0
#define CGA_IO_SIZE         0x10
#define CGA_WIDTH           640
#define CGA_HEIGHT          200
#define CGA_TOTAL_DOTS      912
#define CGA_TOTAL_LINES     262
#define CGA_VRETRACE_START  224
#define CGA_VRETRACE_END    240
#define CGA_FRAME_NS        (NANOSECONDS_PER_SECOND / 60)

#define CGA_MODE_80COL      0x01
#define CGA_MODE_GRAPHICS   0x02
#define CGA_MODE_VIDEO      0x08
#define CGA_MODE_HIRES      0x10
#define CGA_MODE_BLINK      0x20

struct CGAState {
    ISADevice parent_obj;

    MemoryRegion vram;
    MemoryRegion vram_mirror;
    MemoryRegion io;
    QemuConsole *con;

    uint8_t crtc_index;
    uint8_t crtc[18];
    uint8_t mode;
    uint8_t color;
    bool light_pen_latched;
};

static const uint8_t cga_crtc_mask[18] = {
    0xff, 0xff, 0xff, 0xff, 0x7f, 0x1f, 0x7f, 0x7f,
    0x03, 0x1f, 0x7f, 0x1f, 0x3f, 0xff, 0x3f, 0xff,
    0xff, 0xff,
};

static const uint8_t cga_rgb[16][3] = {
    { 0x00, 0x00, 0x00 }, { 0x00, 0x00, 0xaa },
    { 0x00, 0xaa, 0x00 }, { 0x00, 0xaa, 0xaa },
    { 0xaa, 0x00, 0x00 }, { 0xaa, 0x00, 0xaa },
    { 0xaa, 0x55, 0x00 }, { 0xaa, 0xaa, 0xaa },
    { 0x55, 0x55, 0x55 }, { 0x55, 0x55, 0xff },
    { 0x55, 0xff, 0x55 }, { 0x55, 0xff, 0xff },
    { 0xff, 0x55, 0x55 }, { 0xff, 0x55, 0xff },
    { 0xff, 0xff, 0x55 }, { 0xff, 0xff, 0xff },
};

static uint32_t cga_host_color(DisplaySurface *surface, uint8_t index)
{
    const uint8_t *rgb = cga_rgb[index & 0x0f];

    switch (surface_bits_per_pixel(surface)) {
    case 8:
        return rgb_to_pixel8(rgb[0], rgb[1], rgb[2]);
    case 15:
        return rgb_to_pixel15(rgb[0], rgb[1], rgb[2]);
    case 16:
        return rgb_to_pixel16(rgb[0], rgb[1], rgb[2]);
    case 24:
        return rgb_to_pixel24(rgb[0], rgb[1], rgb[2]);
    case 32:
        return rgb_to_pixel32(rgb[0], rgb[1], rgb[2]);
    default:
        return 0;
    }
}

static void cga_put_pixel(DisplaySurface *surface, int x, int y, uint32_t pixel)
{
    int bpp = (surface_bits_per_pixel(surface) + 7) >> 3;
    uint8_t *p = surface_data(surface) + surface_stride(surface) * y + bpp * x;

    switch (bpp) {
    case 1:
        p[0] = pixel;
        break;
    case 2:
        *(uint16_t *)p = pixel;
        break;
    case 3:
        p[0] = pixel;
        p[1] = pixel >> 8;
        p[2] = pixel >> 16;
        break;
    case 4:
        *(uint32_t *)p = pixel;
        break;
    default:
        break;
    }
}

static void cga_blank(DisplaySurface *surface)
{
    uint8_t *row = surface_data(surface);
    int y;

    for (y = 0; y < CGA_HEIGHT; y++) {
        memset(row, 0, surface_stride(surface));
        row += surface_stride(surface);
    }
}

static uint8_t cga_320_palette(const CGAState *s, unsigned int pel)
{
    static const uint8_t palette[2][3] = {
        { 2, 4, 6 },
        { 3, 5, 7 },
    };
    uint8_t value;

    if (pel == 0) {
        return s->color & 0x0f;
    }

    value = palette[(s->color >> 5) & 1][pel - 1];
    if (s->color & 0x10) {
        value += 8;
    }
    return value;
}

static void cga_draw_graphics(CGAState *s, DisplaySurface *surface)
{
    uint8_t *vram = memory_region_get_ram_ptr(&s->vram);
    bool hires = s->mode & CGA_MODE_HIRES;
    int y, byte;

    for (y = 0; y < CGA_HEIGHT; y++) {
        unsigned int row = ((y & 1) ? 0x2000 : 0) + (y >> 1) * 80;

        for (byte = 0; byte < 80; byte++) {
            uint8_t data = vram[(row + byte) & (CGA_VRAM_SIZE - 1)];

            if (hires) {
                uint32_t off = cga_host_color(surface, 0);
                uint32_t on = cga_host_color(surface, s->color & 0x0f);
                int bit;

                for (bit = 0; bit < 8; bit++) {
                    cga_put_pixel(surface, byte * 8 + bit, y,
                                  (data & (0x80 >> bit)) ? on : off);
                }
            } else {
                int pel;

                for (pel = 0; pel < 4; pel++) {
                    uint8_t index = (data >> (6 - pel * 2)) & 3;
                    uint32_t pixel = cga_host_color(surface,
                                                    cga_320_palette(s, index));
                    int x = (byte * 4 + pel) * 2;
                    cga_put_pixel(surface, x, y, pixel);
                    cga_put_pixel(surface, x + 1, y, pixel);
                }
            }
        }
    }
}

static uint8_t cga_font_row(uint8_t ch, int row)
{
    unsigned int base = ch * FONT_HEIGHT + row * 2;

    /* Reuse QEMU's built-in font without introducing a new ROM blob. */
    return vgafont16[base] | vgafont16[base + 1];
}

static void cga_draw_text(CGAState *s, DisplaySurface *surface)
{
    uint8_t *vram = memory_region_get_ram_ptr(&s->vram);
    unsigned int columns = (s->mode & CGA_MODE_80COL) ? 80 : 40;
    unsigned int xscale = (columns == 40) ? 2 : 1;
    unsigned int start = ((s->crtc[12] & 0x3f) << 8) | s->crtc[13];
    bool blink_phase = (qemu_clock_get_ms(QEMU_CLOCK_VIRTUAL) / 500) & 1;
    int row, col, scan, bit;

    for (row = 0; row < 25; row++) {
        for (col = 0; col < columns; col++) {
            unsigned int cell = (start + row * columns + col) & 0x1fff;
            uint8_t ch = vram[(cell * 2) & (CGA_VRAM_SIZE - 1)];
            uint8_t attr = vram[(cell * 2 + 1) & (CGA_VRAM_SIZE - 1)];
            uint8_t fg = attr & 0x0f;
            uint8_t bg;

            if (s->mode & CGA_MODE_BLINK) {
                bg = (attr >> 4) & 0x07;
                if ((attr & 0x80) && !blink_phase) {
                    fg = bg;
                }
            } else {
                bg = (attr >> 4) & 0x0f;
            }

            for (scan = 0; scan < 8; scan++) {
                uint8_t glyph = cga_font_row(ch, scan);
                uint32_t fg_pixel = cga_host_color(surface, fg);
                uint32_t bg_pixel = cga_host_color(surface, bg);

                for (bit = 0; bit < 8; bit++) {
                    uint32_t pixel = (glyph & (0x80 >> bit)) ?
                                     fg_pixel : bg_pixel;
                    int x = (col * 8 + bit) * xscale;
                    int y = row * 8 + scan;
                    int scale;

                    for (scale = 0; scale < xscale; scale++) {
                        cga_put_pixel(surface, x + scale, y, pixel);
                    }
                }
            }
        }
    }
}

static bool cga_update_display(void *opaque)
{
    CGAState *s = opaque;
    DisplaySurface *surface = qemu_console_surface(s->con);

    if (!(s->mode & CGA_MODE_VIDEO)) {
        cga_blank(surface);
    } else if (s->mode & CGA_MODE_GRAPHICS) {
        cga_draw_graphics(s, surface);
    } else {
        cga_draw_text(s, surface);
    }

    qemu_console_update_full(s->con);
    return true;
}

static void cga_invalidate_display(void *opaque)
{
    CGAState *s = opaque;

    qemu_console_update_full(s->con);
}

static const GraphicHwOps cga_hw_ops = {
    .invalidate = cga_invalidate_display,
    .gfx_update = cga_update_display,
};

static uint8_t cga_status(CGAState *s)
{
    uint64_t frame_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) % CGA_FRAME_NS;
    uint64_t dot = frame_ns * (CGA_TOTAL_DOTS * CGA_TOTAL_LINES) / CGA_FRAME_NS;
    unsigned int line = dot / CGA_TOTAL_DOTS;
    unsigned int x = dot % CGA_TOTAL_DOTS;
    uint8_t status = 0x04; /* no light-pen switch pressed */

    if (line >= CGA_HEIGHT || x >= CGA_WIDTH) {
        status |= 0x01;
    }
    if (s->light_pen_latched) {
        status |= 0x02;
    }
    if (line >= CGA_VRETRACE_START && line < CGA_VRETRACE_END) {
        status |= 0x08;
    }
    return status;
}

static uint64_t cga_io_read(void *opaque, hwaddr addr, unsigned int size)
{
    CGAState *s = opaque;

    if (addr < 8 && (addr & 1)) {
        if (s->crtc_index < ARRAY_SIZE(s->crtc)) {
            return s->crtc[s->crtc_index];
        }
        return 0xff;
    }

    if (addr == 0x0a) {
        return cga_status(s);
    }

    return 0xff;
}

static void cga_light_pen_preset(CGAState *s)
{
    uint16_t pos = ((s->crtc[12] & 0x3f) << 8) | s->crtc[13];

    s->light_pen_latched = true;
    s->crtc[16] = pos >> 8;
    s->crtc[17] = pos;
}

static void cga_io_write(void *opaque, hwaddr addr, uint64_t value,
                         unsigned int size)
{
    CGAState *s = opaque;
    uint8_t val = value;

    if (addr < 8) {
        if (!(addr & 1)) {
            s->crtc_index = val & 0x1f;
        } else if (s->crtc_index < 16) {
            s->crtc[s->crtc_index] = val & cga_crtc_mask[s->crtc_index];
        }
        return;
    }

    switch (addr) {
    case 0x08:
        s->mode = val & 0x3f;
        break;
    case 0x09:
        s->color = val & 0x3f;
        break;
    case 0x0b:
        s->light_pen_latched = false;
        break;
    case 0x0c:
        cga_light_pen_preset(s);
        break;
    default:
        break;
    }
}

static const MemoryRegionOps cga_io_ops = {
    .read = cga_io_read,
    .write = cga_io_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid.min_access_size = 1,
    .valid.max_access_size = 1,
    .impl.min_access_size = 1,
    .impl.max_access_size = 1,
};

static int cga_post_load(void *opaque, int version_id)
{
    CGAState *s = opaque;

    qemu_console_resize(s->con, CGA_WIDTH, CGA_HEIGHT);
    return 0;
}

static const VMStateDescription vmstate_cga = {
    .name = "isa-cga",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = cga_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(crtc_index, CGAState),
        VMSTATE_UINT8_ARRAY(crtc, CGAState, 18),
        VMSTATE_UINT8(mode, CGAState),
        VMSTATE_UINT8(color, CGAState),
        VMSTATE_BOOL(light_pen_latched, CGAState),
        VMSTATE_END_OF_LIST()
    },
};

static void cga_reset(DeviceState *dev)
{
    CGAState *s = ISA_CGA(dev);

    s->crtc_index = 0;
    memset(s->crtc, 0, sizeof(s->crtc));
    s->mode = 0;
    s->color = 0;
    s->light_pen_latched = false;
    qemu_console_resize(s->con, CGA_WIDTH, CGA_HEIGHT);
}

static void cga_realize(DeviceState *dev, Error **errp)
{
    ISADevice *isadev = ISA_DEVICE(dev);
    CGAState *s = ISA_CGA(dev);
    MemoryRegion *as = isa_address_space(isadev);

    if (!memory_region_init_ram(&s->vram, OBJECT(dev), "isa-cga.vram",
                                CGA_VRAM_SIZE, errp)) {
        return;
    }
    memory_region_init_alias(&s->vram_mirror, OBJECT(dev), "isa-cga.vram-mirror",
                             &s->vram, 0, CGA_VRAM_SIZE);
    memory_region_add_subregion_overlap(as, CGA_MEM_BASE, &s->vram, 1);
    memory_region_add_subregion_overlap(as, CGA_MEM_MIRROR,
                                        &s->vram_mirror, 1);

    memory_region_init_io(&s->io, OBJECT(dev), &cga_io_ops, s,
                          "isa-cga.io", CGA_IO_SIZE);
    isa_register_ioport(isadev, &s->io, CGA_IO_BASE);

    s->con = qemu_graphic_console_create(dev, 0, &cga_hw_ops, s);
    qemu_console_resize(s->con, CGA_WIDTH, CGA_HEIGHT);
}

static void cga_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->desc = "IBM Color/Graphics Adapter";
    dc->realize = cga_realize;
    dc->vmsd = &vmstate_cga;
    device_class_set_legacy_reset(dc, cga_reset);
    set_bit(DEVICE_CATEGORY_DISPLAY, dc->categories);
}

static const TypeInfo cga_info = {
    .name = TYPE_ISA_CGA,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(CGAState),
    .class_init = cga_class_init,
};

static void cga_register_types(void)
{
    type_register_static(&cga_info);
}

type_init(cga_register_types)
''')


if len(sys.argv) != 2 or sys.argv[1] not in {"tests", "production"}:
    raise SystemExit("usage: implement_ibm_cga.py tests|production")

if sys.argv[1] == "tests":
    stage_tests()
else:
    production()
