/*
 * Cirrus Logic CL-GD5430 VESA Local Bus framebuffer decoder
 *
 * QEMU's x86 machines do not model VLB timing. Use the ISA device
 * container only to connect the legacy VGA ports and the x86 physical
 * address space; this is not an ISA GD5430.
 *
 * SPDX-License-Identifier: MIT
 */

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "hw/core/loader.h"
#include "hw/core/qdev-properties.h"
#include "hw/isa/isa.h"
#include "cirrus_vga_internal.h"
#include "qom/object.h"
#include "ui/console.h"

#define TYPE_CIRRUS_GD5430_VLB "cirrus-gd5430-vlb"
OBJECT_DECLARE_SIMPLE_TYPE(CirrusGD5430VLBState, CIRRUS_GD5430_VLB)

struct CirrusGD5430VLBState {
    ISADevice parent_obj;
    CirrusVGAState cirrus_vga;
    uint32_t lfb_base;
};

static void cirrus_gd5430_vlb_realize(DeviceState *dev, Error **errp)
{
    CirrusGD5430VLBState *d = CIRRUS_GD5430_VLB(dev);
    ISADevice *isadev = ISA_DEVICE(dev);
    VGACommonState *vga = &d->cirrus_vga.vga;

    /*
     * Cirrus's February 1994 reference design offers 64 MiB or 2 GiB
     * jumper-selected linear apertures. The decoder is 4 MiB wide.
     */
    if (d->lfb_base != 0x04000000U && d->lfb_base != 0x80000000U) {
        error_setg(errp, "Invalid GD5430 VLB lfb-base 0x%x (use 0x04000000 or 0x80000000)",
                   d->lfb_base);
        return;
    }
    if (vga->vram_size_mb != 2) {
        error_setg(errp, "Invalid GD5430 VLB ram size '%u', expected 2",
                   vga->vram_size_mb);
        return;
    }
    if (!vga_common_init(vga, OBJECT(dev), errp)) {
        return;
    }

    cirrus_init_common(&d->cirrus_vga, OBJECT(dev), CIRRUS_ID_CLGD5430,
                       CIRRUS_BUSTYPE_VLBFAST,
                       isa_address_space(isadev), isa_address_space_io(isadev));

    /* Unlike PCI BARs, the board straps the physical aperture address.
     * It must remain disabled until SR07[7:4] enables the VLB decoder. */
    memory_region_set_enabled(&d->cirrus_vga.cirrus_linear_io, false);
    memory_region_add_subregion_overlap(isa_address_space(isadev),
                                        d->lfb_base,
                                        &d->cirrus_vga.cirrus_linear_io, 1);

    vga->con = qemu_graphic_console_create(dev, 0, vga->hw_ops, vga);
    rom_add_vga(VGABIOS_CIRRUS_FILENAME);
}

static const Property cirrus_gd5430_vlb_properties[] = {
    DEFINE_PROP_UINT32("vgamem_mb", CirrusGD5430VLBState,
                       cirrus_vga.vga.vram_size_mb, 2),
    DEFINE_PROP_UINT32("lfb-base", CirrusGD5430VLBState,
                       lfb_base, 0x04000000U),
    DEFINE_PROP_BOOL("blitter", CirrusGD5430VLBState,
                     cirrus_vga.enable_blitter, true),
    DEFINE_PROP_BOOL("global-vmstate", CirrusGD5430VLBState,
                     cirrus_vga.vga.global_vmstate, false),
};

static void cirrus_gd5430_vlb_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->vmsd = &vmstate_cirrus_vga;
    dc->realize = cirrus_gd5430_vlb_realize;
    device_class_set_props(dc, cirrus_gd5430_vlb_properties);
    set_bit(DEVICE_CATEGORY_DISPLAY, dc->categories);
    dc->desc = "Cirrus CL-GD5430 VLB VGA (address decoder, no VLB timing)";
}

static const TypeInfo cirrus_gd5430_vlb_info = {
    .name = TYPE_CIRRUS_GD5430_VLB,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(CirrusGD5430VLBState),
    .class_init = cirrus_gd5430_vlb_class_init,
};

static void cirrus_gd5430_vlb_register_types(void)
{
    type_register_static(&cirrus_gd5430_vlb_info);
}

type_init(cirrus_gd5430_vlb_register_types)
