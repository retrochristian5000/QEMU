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

#include "qemu/osdep.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "hw/core/loader.h"
#include "hw/core/qdev-properties.h"
#include "hw/isa/isa.h"
#include "cirrus_vga_internal.h"
#include "qom/object.h"
#include "ui/console.h"

#define TYPE_ISA_CIRRUS_VGA "isa-cirrus-vga"
#define TYPE_ISA_CIRRUS_GD5426 "isa-cirrus-gd5426"
#define TYPE_ISA_CIRRUS_GD5422 "isa-cirrus-gd5422"
OBJECT_DECLARE_SIMPLE_TYPE(ISACirrusVGAState, ISA_CIRRUS_VGA)
OBJECT_DECLARE_SIMPLE_TYPE(ISACirrusGD5422State, ISA_CIRRUS_GD5422)

struct ISACirrusVGAState {
    ISADevice parent_obj;

    CirrusVGAState cirrus_vga;
};

/* Sibling type permits independent 1 MiB defaults without shadowing
 * the inherited GD5428/GD5426 qdev properties. */
struct ISACirrusGD5422State {
    ISADevice parent_obj;

    CirrusVGAState cirrus_vga;
};

static void isa_cirrus_vga_realize(DeviceState *dev, Error **errp,
                                   CirrusVGAState *cirrus, int device_id,
                                   unsigned int vram_mb)
{
    ISADevice *isadev = ISA_DEVICE(dev);
    VGACommonState *s = &cirrus->vga;

    if (s->vram_size_mb != vram_mb) {
        error_setg(errp, "Invalid Cirrus ISA VRAM size '%u', expected %u",
                   s->vram_size_mb, vram_mb);
        return;
    }
    if (!vga_common_init(s, OBJECT(dev), errp)) {
        return;
    }
    cirrus_init_common(cirrus, OBJECT(dev), device_id,
                       CIRRUS_BUSTYPE_ISA,
                       isa_address_space(isadev),
                       isa_address_space_io(isadev));
    s->con = qemu_graphic_console_create(dev, 0, s->hw_ops, s);
    rom_add_vga(VGABIOS_CIRRUS_FILENAME);
    /* XXX ISA-LFB support */
    /* FIXME not qdev yet */
}

static void isa_cirrus_vga_realizefn(DeviceState *dev, Error **errp)
{
    ISACirrusVGAState *d = ISA_CIRRUS_VGA(dev);

    isa_cirrus_vga_realize(dev, errp, &d->cirrus_vga,
                           CIRRUS_ID_CLGD5428, 2);
}

static void isa_cirrus_gd5426_realizefn(DeviceState *dev, Error **errp)
{
    ISACirrusVGAState *d = ISA_CIRRUS_VGA(dev);

    isa_cirrus_vga_realize(dev, errp, &d->cirrus_vga,
                           CIRRUS_ID_CLGD5426, 2);
}

static void isa_cirrus_gd5422_realizefn(DeviceState *dev, Error **errp)
{
    ISACirrusGD5422State *d = ISA_CIRRUS_GD5422(dev);

    d->cirrus_vga.enable_blitter = false;
    isa_cirrus_vga_realize(dev, errp, &d->cirrus_vga,
                           CIRRUS_ID_CLGD5422, 1);
}

static const Property isa_cirrus_gd5422_properties[] = {
    DEFINE_PROP_UINT32("vgamem_mb", struct ISACirrusGD5422State,
                       cirrus_vga.vga.vram_size_mb, 1),
    DEFINE_PROP_BOOL("global-vmstate", struct ISACirrusGD5422State,
                     cirrus_vga.vga.global_vmstate, false),
};

static const Property isa_cirrus_vga_properties[] = {
    DEFINE_PROP_UINT32("vgamem_mb", struct ISACirrusVGAState,
                       cirrus_vga.vga.vram_size_mb, 2),
    DEFINE_PROP_BOOL("blitter", struct ISACirrusVGAState,
                     cirrus_vga.enable_blitter, true),
    DEFINE_PROP_BOOL("global-vmstate", struct ISACirrusVGAState,
                     cirrus_vga.vga.global_vmstate, false),
};

static void isa_cirrus_vga_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->vmsd  = &vmstate_cirrus_vga;
    dc->realize = isa_cirrus_vga_realizefn;
    device_class_set_props(dc, isa_cirrus_vga_properties);
    set_bit(DEVICE_CATEGORY_DISPLAY, dc->categories);
}

static const TypeInfo isa_cirrus_vga_info = {
    .name          = TYPE_ISA_CIRRUS_VGA,
    .parent        = TYPE_ISA_DEVICE,
    .instance_size = sizeof(ISACirrusVGAState),
    .class_init = isa_cirrus_vga_class_init,
};

/* Inherit the ISA wiring, VRAM properties and migration state. */
static void isa_cirrus_gd5426_class_init(ObjectClass *klass,
                                          const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = isa_cirrus_gd5426_realizefn;
    dc->desc = "Cirrus Logic CL-GD5426 ISA VGA";
}

static const TypeInfo isa_cirrus_gd5426_info = {
    .name = TYPE_ISA_CIRRUS_GD5426,
    .parent = TYPE_ISA_CIRRUS_VGA,
    .class_init = isa_cirrus_gd5426_class_init,
};

static void isa_cirrus_gd5422_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->vmsd = &vmstate_cirrus_vga;
    dc->realize = isa_cirrus_gd5422_realizefn;
    device_class_set_props(dc, isa_cirrus_gd5422_properties);
    set_bit(DEVICE_CATEGORY_DISPLAY, dc->categories);
    dc->desc = "Cirrus Logic CL-GD5422 ISA VGA (1 MiB, no BitBLT)";
}

static const TypeInfo isa_cirrus_gd5422_info = {
    .name = TYPE_ISA_CIRRUS_GD5422,
    .parent = TYPE_ISA_DEVICE,
    .instance_size = sizeof(ISACirrusGD5422State),
    .class_init = isa_cirrus_gd5422_class_init,
};

static void cirrus_vga_isa_register_types(void)
{
    type_register_static(&isa_cirrus_vga_info);
    type_register_static(&isa_cirrus_gd5426_info);
    type_register_static(&isa_cirrus_gd5422_info);
}

type_init(cirrus_vga_isa_register_types)
