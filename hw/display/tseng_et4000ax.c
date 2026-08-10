/*
 * Tseng Labs ET4000AX ISA VGA controller
 *
 * This first implementation concentrates on the ET4000 programming interface
 * which software uses to distinguish the chip from a plain VGA: the KEY
 * sequence, protected extended registers, and independent 64 KiB read/write
 * segment pointers.  Extended high-resolution timing/rendering is layered on
 * the VGA core and can be completed separately.
 *
 * Reference: Tseng Labs, ET4000 Graphics Controller Data Book, 1989/1990,
 * including the ET4000AX Revision E addendum.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/units.h"
#include "qemu/module.h"
#include "hw/core/loader.h"
#include "hw/display/tseng_et4000ax.h"
#include "hw/isa/isa.h"
#include "migration/vmstate.h"
#include "qom/object.h"
#include "ui/console.h"
#include "vga_int.h"

OBJECT_DECLARE_SIMPLE_TYPE(ET4000AXState, ISA_ET4000AX)

struct ET4000AXState {
    ISADevice parent_obj;

    VGACommonState vga;
    PortioList portio;
    MemoryRegion legacy_memory;

    uint8_t segment_select;
    uint8_t hercules_compat;
    uint8_t mode_control;
    bool key_unlocked;
};

/* Tseng register addresses. */
#define ET4000_HERC_COMPAT       0x3bf
#define ET4000_SEGMENT_SELECT    0x3cd
#define ET4000_MODE_MONO         0x3b8
#define ET4000_MODE_COLOR        0x3d8

/* Extended CRTC registers used by the first implementation. */
#define ET4000_CRTC_RCONF        0x32
#define ET4000_CRTC_EXT_START    0x33
#define ET4000_CRTC_COMPAT       0x34
#define ET4000_CRTC_OVERFLOW_HI  0x35
#define ET4000_CRTC_VSCONF1      0x36
#define ET4000_CRTC_VSCONF2      0x37

static bool et4000ax_crtc_data_port(VGACommonState *s, uint32_t addr)
{
    return (addr == 0x3b5 && !(s->msr & VGA_MIS_COLOR)) ||
           (addr == 0x3d5 &&  (s->msr & VGA_MIS_COLOR));
}

static bool et4000ax_crtc_index_port(VGACommonState *s, uint32_t addr)
{
    return (addr == 0x3b4 && !(s->msr & VGA_MIS_COLOR)) ||
           (addr == 0x3d4 &&  (s->msr & VGA_MIS_COLOR));
}

static uint32_t et4000ax_io_read(void *opaque, uint32_t addr)
{
    ET4000AXState *d = opaque;
    VGACommonState *s = &d->vga;

    switch (addr) {
    case ET4000_SEGMENT_SELECT:
        /* The segment register is inaccessible until KEY has been set. */
        return d->key_unlocked ? d->segment_select : 0xff;
    case ET4000_MODE_MONO:
    case ET4000_MODE_COLOR:
        /* Hercules Compatibility bit 1 is reflected as mode-control bit 6. */
        return (d->mode_control & ~0x40) |
               ((d->hercules_compat & 0x02) << 5);
    case ET4000_HERC_COMPAT:
        /* Documented as write-only. */
        return 0xff;
    default:
        return vga_ioport_read(s, addr);
    }
}

static void et4000ax_io_write(void *opaque, uint32_t addr, uint32_t val)
{
    ET4000AXState *d = opaque;
    VGACommonState *s = &d->vga;
    uint8_t index;

    val &= 0xff;

    switch (addr) {
    case ET4000_HERC_COMPAT:
        d->hercules_compat = val;
        return;

    case ET4000_MODE_MONO:
    case ET4000_MODE_COLOR:
        d->mode_control = val;
        /*
         * Tseng's documented KEY sequence is:
         *   out 3bf,03h
         *   out 3#8,0a0h
         * KEY remains enabled until power-on or synchronous reset.
         */
        if (d->hercules_compat == 0x03 && val == 0xa0) {
            d->key_unlocked = true;
        }
        return;

    case ET4000_SEGMENT_SELECT:
        if (d->key_unlocked) {
            d->segment_select = val;
        }
        return;

    case 0x3c4: /* Timing Sequencer index */
        s->sr_index = val & 0x07;
        return;

    case 0x3c5: /* Timing Sequencer data */
        index = s->sr_index & 0x07;
        if (index == 0) {
            /* A synchronous reset clears KEY and requires it to be set again. */
            if (!(val & 0x02)) {
                d->key_unlocked = false;
                d->segment_select = 0;
            }
            vga_ioport_write(s, addr, val);
            return;
        }
        if (index == 6 || index == 7) {
            if (!d->key_unlocked) {
                return;
            }
            if (index == 6) {
                /* TS State Control: only state bits 1:2 are defined. */
                s->sr[6] = val & 0x06;
            } else {
                /*
                 * Revision E requires bits 2 and 4 set.  Bit 7 selects
                 * VGA compatibility and is otherwise software controlled.
                 */
                s->sr[7] = val | 0x14;
            }
            return;
        }
        vga_ioport_write(s, addr, val);
        return;

    default:
        break;
    }

    if (et4000ax_crtc_index_port(s, addr)) {
        /* ET4000 CRTC index is six bits wide. */
        vga_ioport_write(s, addr, val & 0x3f);
        return;
    }

    if (et4000ax_crtc_data_port(s, addr)) {
        index = s->cr_index & 0x3f;

        /*
         * Tseng: CRTC indices above 18h require KEY, except 33h and 35h.
         * Index 35h has its own VGA CR11 bit-7 protection.
         */
        if (index > 0x18 && index != ET4000_CRTC_EXT_START &&
            index != ET4000_CRTC_OVERFLOW_HI && !d->key_unlocked) {
            return;
        }

        if (index == ET4000_CRTC_OVERFLOW_HI &&
            (s->cr[VGA_CRTC_V_SYNC_END] & VGA_CR11_LOCK_CR0_CR7)) {
            /* With CR11 locked, only Overflow High bits 4 and 7 are writable. */
            val = (s->cr[index] & ~0x90) | (val & 0x90);
        }
        vga_ioport_write(s, addr, val);
        return;
    }

    vga_ioport_write(s, addr, val);
}

static const MemoryRegionPortio et4000ax_portio_list[] = {
    { 0x04,  2, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3b4-5 */
    { 0x08,  1, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3b8 */
    { 0x0a,  1, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3ba */
    { 0x0f,  1, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3bf */
    { 0x10, 13, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3c0-3cc */
    { 0x1d,  1, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3cd */
    { 0x1e,  2, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3ce-3cf */
    { 0x24,  2, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3d4-5 */
    { 0x28,  1, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3d8 */
    { 0x2a,  1, 1, .read = et4000ax_io_read, .write = et4000ax_io_write }, /* 3da */
    PORTIO_END_OF_LIST(),
};

static uint64_t et4000ax_mem_read(void *opaque, hwaddr addr, unsigned size)
{
    ET4000AXState *d = opaque;
    VGACommonState *s = &d->vga;
    int32_t saved_bank = s->bank_offset;
    uint64_t value;

    /* Bits 7:4 select one of sixteen 64 KiB read segments. */
    s->bank_offset = ((d->segment_select >> 4) & 0x0f) << 16;
    value = vga_mem_readb(s, addr);
    s->bank_offset = saved_bank;
    return value;
}

static void et4000ax_mem_write(void *opaque, hwaddr addr,
                               uint64_t value, unsigned size)
{
    ET4000AXState *d = opaque;
    VGACommonState *s = &d->vga;
    int32_t saved_bank = s->bank_offset;

    /* Bits 3:0 select one of sixteen 64 KiB write segments. */
    s->bank_offset = (d->segment_select & 0x0f) << 16;
    vga_mem_writeb(s, addr, value);
    s->bank_offset = saved_bank;
}

static const MemoryRegionOps et4000ax_mem_ops = {
    .read = et4000ax_mem_read,
    .write = et4000ax_mem_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
};

static void et4000ax_get_params(VGACommonState *s, VGADisplayParams *params)
{
    params->line_offset = s->cr[VGA_CRTC_OFFSET] << 3;
    params->start_addr = s->cr[VGA_CRTC_START_LO] |
                         (s->cr[VGA_CRTC_START_HI] << 8) |
                         ((s->cr[ET4000_CRTC_EXT_START] & 0x03) << 16);
    params->line_compare = s->cr[VGA_CRTC_LINE_COMPARE] |
                           ((s->cr[VGA_CRTC_OVERFLOW] & 0x10) << 4) |
                           ((s->cr[VGA_CRTC_MAX_SCAN] & 0x40) << 3) |
                           ((s->cr[ET4000_CRTC_OVERFLOW_HI] & 0x10) << 6);
    params->hpel = s->ar[VGA_ATC_PEL];
    params->hpel_split = s->ar[VGA_ATC_MODE] & 0x20;
}

static void et4000ax_reset(DeviceState *dev)
{
    ET4000AXState *d = ISA_ET4000AX(dev);

    vga_common_reset(&d->vga);
    d->segment_select = 0;
    d->hercules_compat = 0;
    d->mode_control = 0;
    d->key_unlocked = false;

    /* Documented ET4000AX Revision E / DRAM power-on characteristics. */
    d->vga.sr[7] = 0xbc;      /* VGA mode, 32 KiB ROM map, Rev-E fixed bits. */
    d->vga.cr[ET4000_CRTC_VSCONF1] = 0x40; /* 16-bit memory host interface. */
    d->vga.cr[ET4000_CRTC_VSCONF2] = 0x00; /* DRAM, not VRAM. */
}

static void et4000ax_realize(DeviceState *dev, Error **errp)
{
    ISADevice *isadev = ISA_DEVICE(dev);
    ET4000AXState *d = ISA_ET4000AX(dev);
    VGACommonState *s = &d->vga;

    /* ET4000AX boards commonly exposed up to 1 MiB; model that configuration. */
    s->vram_size_mb = 1;
    if (!vga_common_init(s, OBJECT(dev), errp)) {
        return;
    }

    s->legacy_address_space = isa_address_space(isadev);
    s->get_params = et4000ax_get_params;

    isa_register_portio_list(isadev, &d->portio, 0x3b0,
                             et4000ax_portio_list, d, "et4000ax");

    memory_region_init_io(&d->legacy_memory, OBJECT(dev), &et4000ax_mem_ops,
                          d, "et4000ax-lowmem", 0x20000);
    memory_region_add_subregion_overlap(isa_address_space(isadev), 0x000a0000,
                                        &d->legacy_memory, 1);
    memory_region_set_coalescing(&d->legacy_memory);

    s->con = qemu_graphic_console_create(dev, 0, s->hw_ops, s);

    /* A real Dell/Tseng ROM can replace this generic VGA BIOS later. */
    rom_add_vga(VGABIOS_FILENAME);

    et4000ax_reset(dev);
}

static const VMStateDescription vmstate_et4000ax = {
    .name = "tseng-et4000ax",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_STRUCT(vga, ET4000AXState, 0, vmstate_vga_common,
                       VGACommonState),
        VMSTATE_UINT8(segment_select, ET4000AXState),
        VMSTATE_UINT8(hercules_compat, ET4000AXState),
        VMSTATE_UINT8(mode_control, ET4000AXState),
        VMSTATE_BOOL(key_unlocked, ET4000AXState),
        VMSTATE_END_OF_LIST()
    },
};

static void et4000ax_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = et4000ax_realize;
    device_class_set_legacy_reset(dc, et4000ax_reset);
    dc->vmsd = &vmstate_et4000ax;
    set_bit(DEVICE_CATEGORY_DISPLAY, dc->categories);
    dc->desc = "Tseng Labs ET4000AX ISA VGA controller";
}

static const TypeInfo et4000ax_info = {
    .name = TYPE_ISA_ET4000AX,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(ET4000AXState),
    .class_init = et4000ax_class_init,
};

static void et4000ax_register_types(void)
{
    type_register_static(&et4000ax_info);
}

type_init(et4000ax_register_types)
