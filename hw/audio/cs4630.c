/*
 * Cirrus Logic Crystal SoundFusion CS4630
 *
 * This is an initial, reusable CS4630 core.  It models the PCI identity,
 * BAR layout, host-control registers, AC'97 link bring-up, and the large
 * SoundFusion DSP memory window.  DSP instruction execution and PCM engines
 * are intentionally left for later layers so board personalities such as the
 * Turtle Beach Santa Cruz can reuse the same controller core.
 *
 * Register layout follows the public CS46xx driver definitions used by Linux
 * and FreeBSD.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "qemu/module.h"
#include "hw/audio/ac97-codec.h"
#include "hw/audio/cs4630.h"
#include "hw/core/qdev-properties.h"
#include "hw/pci/pci_device.h"
#include "migration/vmstate.h"

#define CS4630_PCI_VENDOR_ID        0x1013
#define CS4630_PCI_DEVICE_ID        0x6003
#define CS4630_PCI_REVISION         0x01

#define CS4630_BA0_SIZE             0x00001000
#define CS4630_BA1_SIZE             0x00100000
#define CS4630_BA0_DWORDS           (CS4630_BA0_SIZE / sizeof(uint32_t))

/* BA0 direct registers used by the initial model. */
#define BA0_HISR                    0x000
#define BA0_HSR0                    0x004
#define BA0_HICR                    0x008
#define BA0_DMSR                    0x100
#define BA0_HSAR                    0x110
#define BA0_HDAR                    0x114
#define BA0_HDMR                    0x118
#define BA0_HDCR                    0x11c
#define BA0_PCICFG00                0x300
#define BA0_PCICFG3C                0x33c
#define BA0_CLKCR1                  0x400
#define BA0_CLKCR2                  0x404
#define BA0_PLLM                    0x408
#define BA0_PLLCC                   0x40c
#define BA0_FRR                     0x410
#define BA0_CFL1                    0x414
#define BA0_CFL2                    0x418
#define BA0_SERMC1                  0x420
#define BA0_SERMC2                  0x424
#define BA0_ACCTL                   0x460
#define BA0_ACSTS                   0x464
#define BA0_ACOSV                   0x468
#define BA0_ACCAD                   0x46c
#define BA0_ACCDA                   0x470
#define BA0_ACISV                   0x474
#define BA0_ACSAD                   0x478
#define BA0_ACSDA                   0x47c
#define BA0_JSPT                    0x480
#define BA0_JSCTL                   0x484
#define BA0_JSC1                    0x488
#define BA0_JSC2                    0x48c
#define BA0_MIDCR                   0x490
#define BA0_MIDSR                   0x494
#define BA0_MIDWP                   0x498
#define BA0_MIDRP                   0x49c
#define BA0_JSIO                    0x4a0
#define BA0_CFGI                    0x4b0
#define BA0_SSVID                   0x4b4
#define BA0_GPIOR                   0x4b8
#define BA0_SERACC                  0x4d8
#define BA0_ACCTL2                  0x4e0
#define BA0_ACSTS2                  0x4e4
#define BA0_ACOSV2                  0x4e8
#define BA0_ACCAD2                  0x4ec
#define BA0_ACCDA2                  0x4f0
#define BA0_ACISV2                  0x4f4
#define BA0_ACSAD2                  0x4f8
#define BA0_ACSDA2                  0x4fc

/* BA1 Sound Processor memory/register window. */
#define BA1_SPCR                    0x30000

/* Host interrupt status/control bits. */
#define HISR_INTENA                 0x80000000u
#define HISR_SOURCE_MASK            0x7fffffffu
#define HICR_IEV                    0x00000001u
#define HICR_CHGM                   0x00000002u

/* AC'97 control/status bits. */
#define ACCTL_RSTN                  0x00000001u
#define ACCTL_ESYN                  0x00000002u
#define ACCTL_VFRM                  0x00000004u
#define ACCTL_DCV                   0x00000008u
#define ACCTL_CRW                   0x00000010u
#define ACSTS_CRDY                  0x00000001u
#define ACSTS_VSTS                  0x00000002u
#define ACISV_ISV3                  0x00000001u
#define ACISV_ISV4                  0x00000002u

/* MIDI status reset state: receive buffer empty. */
#define MIDSR_RBE                   0x00000002u

/* Sound Processor control bits. */
#define SPCR_RUN                    0x00000001u
#define SPCR_RSTSP                  0x00000040u

struct CS4630State {
    PCIDevice parent_obj;

    MemoryRegion ba0_mmio;
    MemoryRegion ba1_mmio;

    uint32_t ba0[CS4630_BA0_DWORDS];
    uint8_t *ba1;
    uint32_t ba1_size;

    uint16_t ac97[AC97_CODEC_REGS];
    uint32_t ac97_codec_id;

    bool irq_enabled;
};

static inline uint32_t *cs4630_ba0_reg(CS4630State *s, hwaddr addr)
{
    return &s->ba0[addr >> 2];
}

static void cs4630_update_irq(CS4630State *s)
{
    uint32_t hisr = s->ba0[BA0_HISR >> 2];
    bool level = s->irq_enabled && (hisr & HISR_SOURCE_MASK);

    pci_set_irq(&s->parent_obj, level);
}

static void cs4630_set_irq_enabled(CS4630State *s, bool enabled)
{
    uint32_t *hisr = cs4630_ba0_reg(s, BA0_HISR);

    s->irq_enabled = enabled;
    if (enabled) {
        *hisr |= HISR_INTENA;
    } else {
        *hisr &= ~HISR_INTENA;
    }
    cs4630_update_irq(s);
}

static void cs4630_ac97_link_update(CS4630State *s, bool secondary,
                                    uint32_t value)
{
    hwaddr sts_addr = secondary ? BA0_ACSTS2 : BA0_ACSTS;
    hwaddr isv_addr = secondary ? BA0_ACISV2 : BA0_ACISV;
    hwaddr cad_addr = secondary ? BA0_ACCAD2 : BA0_ACCAD;
    hwaddr cda_addr = secondary ? BA0_ACCDA2 : BA0_ACCDA;
    hwaddr sad_addr = secondary ? BA0_ACSAD2 : BA0_ACSAD;
    hwaddr sda_addr = secondary ? BA0_ACSDA2 : BA0_ACSDA;
    uint32_t *sts = cs4630_ba0_reg(s, sts_addr);
    uint32_t *isv = cs4630_ba0_reg(s, isv_addr);
    uint32_t *ctl = cs4630_ba0_reg(s, secondary ? BA0_ACCTL2 : BA0_ACCTL);

    if (!(value & ACCTL_RSTN)) {
        *sts = 0;
        *isv = 0;
        *ctl = value;
        return;
    }

    if (value & ACCTL_ESYN) {
        *sts |= ACSTS_CRDY;
    }

    if ((value & (ACCTL_ESYN | ACCTL_VFRM)) ==
        (ACCTL_ESYN | ACCTL_VFRM)) {
        *isv |= ACISV_ISV3 | ACISV_ISV4;
    }

    if (value & ACCTL_DCV) {
        unsigned reg = *cs4630_ba0_reg(s, cad_addr) & 0x7f;

        if (value & ACCTL_CRW) {
            *cs4630_ba0_reg(s, sad_addr) = reg;
            *cs4630_ba0_reg(s, sda_addr) = ac97_codec_read(s->ac97, reg);
            *sts |= ACSTS_VSTS;
        } else {
            ac97_codec_write_raw(s->ac97, reg,
                                 *cs4630_ba0_reg(s, cda_addr) & 0xffff);
        }

        /* Commands complete synchronously in this first implementation. */
        value &= ~ACCTL_DCV;
    }

    *ctl = value;
}

static uint64_t cs4630_ba0_read(void *opaque, hwaddr addr, unsigned size)
{
    CS4630State *s = opaque;

    if ((addr & 3) || addr >= CS4630_BA0_SIZE) {
        return 0;
    }

    /* The CS46xx exposes a shadow of conventional PCI config space in BA0. */
    if (addr >= BA0_PCICFG00 && addr <= BA0_PCICFG3C) {
        unsigned cfg = addr - BA0_PCICFG00;
        return pci_get_long(s->parent_obj.config + cfg);
    }

    if (addr == BA0_SSVID) {
        return pci_get_long(s->parent_obj.config + PCI_SUBSYSTEM_VENDOR_ID);
    }

    return *cs4630_ba0_reg(s, addr);
}

static void cs4630_ba0_write(void *opaque, hwaddr addr, uint64_t value,
                             unsigned size)
{
    CS4630State *s = opaque;
    uint32_t v = value;

    if ((addr & 3) || addr >= CS4630_BA0_SIZE) {
        return;
    }

    switch (addr) {
    case BA0_HISR:
    case BA0_HSR0:
    case BA0_ACSTS:
    case BA0_ACISV:
    case BA0_ACSAD:
    case BA0_ACSDA:
    case BA0_ACSTS2:
    case BA0_ACISV2:
    case BA0_ACSAD2:
    case BA0_ACSDA2:
    case BA0_SSVID:
        /* Read-only status/shadow registers. */
        return;

    case BA0_HICR:
        *cs4630_ba0_reg(s, addr) = v & (HICR_IEV | HICR_CHGM);
        if (v & HICR_CHGM) {
            cs4630_set_irq_enabled(s, v & HICR_IEV);
        }
        return;

    case BA0_ACCTL:
        cs4630_ac97_link_update(s, false, v);
        return;

    case BA0_ACCTL2:
        cs4630_ac97_link_update(s, true, v);
        return;

    case BA0_MIDWP:
        /* No MIDI sink yet; preserve the last transmitted byte. */
        *cs4630_ba0_reg(s, addr) = v & 0xff;
        return;

    default:
        *cs4630_ba0_reg(s, addr) = v;
        return;
    }
}

static const MemoryRegionOps cs4630_ba0_ops = {
    .read = cs4630_ba0_read,
    .write = cs4630_ba0_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
    .impl = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static uint64_t cs4630_ba1_read(void *opaque, hwaddr addr, unsigned size)
{
    CS4630State *s = opaque;

    if ((addr & 3) || addr + 4 > s->ba1_size) {
        return 0;
    }

    return ldl_le_p(s->ba1 + addr);
}

static void cs4630_ba1_write(void *opaque, hwaddr addr, uint64_t value,
                             unsigned size)
{
    CS4630State *s = opaque;
    uint32_t v = value;

    if ((addr & 3) || addr + 4 > s->ba1_size) {
        return;
    }

    if (addr == BA1_SPCR && (v & SPCR_RSTSP)) {
        v &= ~SPCR_RUN;
    }

    stl_le_p(s->ba1 + addr, v);
}

static const MemoryRegionOps cs4630_ba1_ops = {
    .read = cs4630_ba1_read,
    .write = cs4630_ba1_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
    .impl = {
        .min_access_size = 4,
        .max_access_size = 4,
    },
};

static void cs4630_reset(DeviceState *dev)
{
    CS4630State *s = CS4630(dev);

    memset(s->ba0, 0, sizeof(s->ba0));
    memset(s->ba1, 0, s->ba1_size);
    ac97_codec_reset(s->ac97, &ac97_codec_profile_minimal,
                     s->ac97_codec_id);

    s->irq_enabled = false;
    s->ba0[BA0_MIDSR >> 2] = MIDSR_RBE;
    pci_set_irq(&s->parent_obj, 0);
}

static void cs4630_realize(PCIDevice *pdev, Error **errp)
{
    CS4630State *s = CS4630(pdev);
    uint8_t *pci_conf = pdev->config;

    pci_conf[PCI_REVISION_ID] = CS4630_PCI_REVISION;
    pci_conf[PCI_INTERRUPT_PIN] = 1;

    s->ba1_size = CS4630_BA1_SIZE;
    s->ba1 = g_malloc0(s->ba1_size);

    memory_region_init_io(&s->ba0_mmio, OBJECT(s), &cs4630_ba0_ops, s,
                          "cs4630-ba0", CS4630_BA0_SIZE);
    memory_region_init_io(&s->ba1_mmio, OBJECT(s), &cs4630_ba1_ops, s,
                          "cs4630-ba1", CS4630_BA1_SIZE);

    pci_register_bar(pdev, 0, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->ba0_mmio);
    pci_register_bar(pdev, 1, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->ba1_mmio);

    cs4630_reset(DEVICE(pdev));
}

static void cs4630_exit(PCIDevice *pdev)
{
    CS4630State *s = CS4630(pdev);

    g_clear_pointer(&s->ba1, g_free);
}

static int cs4630_post_load(void *opaque, int version_id)
{
    CS4630State *s = opaque;

    cs4630_update_irq(s);
    return 0;
}

static const VMStateDescription vmstate_cs4630 = {
    .name = "cs4630",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = cs4630_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_PCI_DEVICE(parent_obj, CS4630State),
        VMSTATE_UINT32_ARRAY(ba0, CS4630State, CS4630_BA0_DWORDS),
        VMSTATE_UINT32(ba1_size, CS4630State),
        VMSTATE_VBUFFER_UINT32(ba1, CS4630State, 1, NULL, ba1_size),
        VMSTATE_UINT16_ARRAY(ac97, CS4630State, AC97_CODEC_REGS),
        VMSTATE_BOOL(irq_enabled, CS4630State),
        VMSTATE_END_OF_LIST()
    }
};

static const Property cs4630_properties[] = {
    DEFINE_PROP_UINT32("ac97-codec-id", CS4630State, ac97_codec_id, 0x43525910),
};

static void cs4630_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    k->realize = cs4630_realize;
    k->exit = cs4630_exit;
    k->vendor_id = CS4630_PCI_VENDOR_ID;
    k->device_id = CS4630_PCI_DEVICE_ID;
    k->revision = CS4630_PCI_REVISION;
    k->class_id = PCI_CLASS_MULTIMEDIA_AUDIO;
    k->subsystem_vendor_id = CS4630_PCI_VENDOR_ID;
    k->subsystem_id = CS4630_PCI_DEVICE_ID;

    dc->desc = "Cirrus Logic Crystal SoundFusion CS4630";
    dc->vmsd = &vmstate_cs4630;
    device_class_set_legacy_reset(dc, cs4630_reset);
    device_class_set_props(dc, cs4630_properties);
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
}

static const TypeInfo cs4630_info = {
    .name = TYPE_CS4630,
    .parent = TYPE_PCI_DEVICE,
    .instance_size = sizeof(CS4630State),
    .class_init = cs4630_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

static void cs4630_register_types(void)
{
    type_register_static(&cs4630_info);
}

type_init(cs4630_register_types)
