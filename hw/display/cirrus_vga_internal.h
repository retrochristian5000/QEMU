/*
 * QEMU Cirrus CLGD 54xx VGA Emulator, ISA bus support
 *
 * Copyright (c) 2004 Fabrice Bellard
 * Copyright (c) 2004 Makoto Suzuki (suzu)
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#ifndef CIRRUS_VGA_INTERNAL_H
#define CIRRUS_VGA_INTERNAL_H

#include "vga_int.h"
#include "hw/i2c/bitbang_i2c.h"

/* IDs */
#define CIRRUS_ID_CLGD5422  (0x23 << 2)
#define CIRRUS_ID_CLGD5426  (0x24 << 2)
#define CIRRUS_ID_CLGD5424  (0x25 << 2)
#define CIRRUS_ID_CLGD5428  (0x26 << 2)
#define CIRRUS_ID_CLGD5430  (0x28 << 2)
#define CIRRUS_ID_CLGD5434  (0x2A << 2)
#define CIRRUS_ID_CLGD5436  (0x2B << 2)
#define CIRRUS_ID_CLGD5446  (0x2E << 2)

/* SR17[5:3]: bus interface straps (read-only to guest software). */
#define CIRRUS_BUSTYPE_VLBFAST 0x10
#define CIRRUS_BUSTYPE_PCI     0x20
#define CIRRUS_BUSTYPE_VLBSLOW 0x30
#define CIRRUS_BUSTYPE_ISA     0x38

extern const VMStateDescription vmstate_cirrus_vga;

struct CirrusVGAState;
typedef void (*cirrus_bitblt_rop_t)(struct CirrusVGAState *s,
                                    uint32_t dstaddr, uint32_t srcaddr,
                                    int dstpitch, int srcpitch,
                                    int bltwidth, int bltheight);

/* Derived CRTC timing; reconstructed from registers after reset/load. */
typedef struct CirrusDisplayTiming {
    uint32_t character_hz;
    unsigned htotal, vtotal;
    unsigned hblank_start, hblank_end;
    unsigned vblank_start, vblank_end;
    unsigned vsync_start, vsync_end;
} CirrusDisplayTiming;

/* Explicit silicon profiles; keep the historical QEMU layout separate. */
typedef enum CirrusGD5446Revision {
    CIRRUS_GD5446_LEGACY = 0,
    CIRRUS_GD5446_REV_A,
    CIRRUS_GD5446_REV_B,
} CirrusGD5446Revision;

typedef struct CirrusVGAState {
    VGACommonState vga;
    CirrusDisplayTiming display_timing;
    bitbang_i2c_interface ddc;
    uint8_t ddc_saved_state; /* Migration encoding of bitbang state. */

    MemoryRegion cirrus_vga_io;
    MemoryRegion cirrus_linear_io;
    MemoryRegion cirrus_linear_bitblt_io;
    MemoryRegion cirrus_mmio_io;
    MemoryRegion pci_bar;
    bool linear_vram;  /* vga.vram mapped over cirrus_linear_io */
    MemoryRegion low_mem_container; /* container for 0xa0000-0xc0000 */
    MemoryRegion low_mem;           /* always mapped, overridden by: */
    MemoryRegion cirrus_bank[2];    /*   aliases at 0xa0000-0xb0000  */
    uint32_t cirrus_addr_mask;
    uint32_t linear_mmio_mask;
    uint8_t cirrus_shadow_gr0;
    uint8_t cirrus_shadow_gr1;
    uint8_t cirrus_hidden_dac_lockindex;
    uint8_t cirrus_hidden_dac_data;
    uint32_t cirrus_bank_base[2];
    uint32_t cirrus_bank_limit[2];
    uint8_t cirrus_hidden_palette[48];
    bool enable_blitter;
    int cirrus_blt_pixelwidth;
    int cirrus_blt_width;
    int cirrus_blt_height;
    int cirrus_blt_dstpitch;
    int cirrus_blt_srcpitch;
    unsigned cirrus_blt_host_skip; /* Latched source DWORD byte offset. */
    uint32_t cirrus_blt_fgcol;
    uint32_t cirrus_blt_bgcol;
    uint32_t cirrus_blt_dstaddr;
    uint32_t cirrus_blt_srcaddr;
    uint8_t cirrus_blt_mode;
    uint8_t cirrus_blt_modeext;
    cirrus_bitblt_rop_t cirrus_rop;
#define CIRRUS_BLTBUFSIZE (2048 * 4) /* one line width */
    uint8_t cirrus_bltbuf[CIRRUS_BLTBUFSIZE];
    uint8_t *cirrus_srcptr;
    uint8_t *cirrus_srcptr_end;
    uint32_t cirrus_srccounter;
    /* hwcursor display state */
    int last_hw_cursor_size;
    int last_hw_cursor_x;
    int last_hw_cursor_y;
    int last_hw_cursor_y_start;
    int last_hw_cursor_y_end;
    int real_vram_size; /* XXX: suppress that */
    int device_id;
    int bustype;
    CirrusGD5446Revision gd5446_revision; /* derived from device type */
} CirrusVGAState;

/*
 * GD5446 TRM 8.2 and 8.37: HDR mode 0x4a with SR7[3:0] = 7
 * routes two successive indexed pixels per CRTC pixel clock.
 */
static inline bool cirrus_gd5446_double_clock_palette(const CirrusVGAState *s)
{
    return s->device_id == CIRRUS_ID_CLGD5446 &&
           (s->vga.sr[7] & 0x0f) == 0x07 &&
           (s->cirrus_hidden_dac_data & 0xcf) == 0x4a;
}

void cirrus_init_common(CirrusVGAState *s, Object *owner,
                        int device_id, int bustype,
                        MemoryRegion *system_memory, MemoryRegion *system_io);

void cirrus_gd5446_update_retrace_info(VGACommonState *vga);
uint8_t cirrus_gd5446_retrace(VGACommonState *vga);

#endif
