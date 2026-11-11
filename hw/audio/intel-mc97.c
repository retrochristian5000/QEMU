/*
 * Intel 82801AA (ICH) MC'97 modem controller
 *
 * The ICH modem function is a separate PCI function from the AC'97 audio
 * controller.  It exposes an AC'97/MC'97 codec window plus two bus-master
 * channels (modem input and modem output).  Telephone-line sample transport
 * is intentionally left for a later layer; this model first makes the PCI,
 * AC-link, reset, semaphore, status, and DMA-register programming interfaces
 * visible to guest drivers.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/audio/ac97-codec.h"
#include "hw/core/qdev-properties.h"
#include "hw/pci/pci_device.h"
#include "migration/vmstate.h"
#include "qapi/error.h"
#include "qemu/module.h"
#include "qom/object.h"

#define TYPE_INTEL_MC97 "intel-mc97"
OBJECT_DECLARE_SIMPLE_TYPE(IntelMC97State, INTEL_MC97)

#define MC97_NAM_SIZE          0x100
#define MC97_NABM_SIZE         0x80
#define MC97_CODEC_STRIDE      0x80
#define MC97_MAX_CODECS        2

#define MC97_SR_FIFOE          BIT(4)
#define MC97_SR_BCIS           BIT(3)
#define MC97_SR_LVBCI          BIT(2)
#define MC97_SR_CELV           BIT(1)
#define MC97_SR_DCH            BIT(0)
#define MC97_SR_WCLEAR_MASK    (MC97_SR_FIFOE | MC97_SR_BCIS | \
                                MC97_SR_LVBCI)
#define MC97_SR_RO_MASK        (MC97_SR_CELV | MC97_SR_DCH)

#define MC97_CR_IOCE           BIT(4)
#define MC97_CR_FEIE           BIT(3)
#define MC97_CR_LVBIE          BIT(2)
#define MC97_CR_RR             BIT(1)
#define MC97_CR_RPBM           BIT(0)
#define MC97_CR_VALID_MASK     0x1f
#define MC97_CR_IRQ_MASK       (MC97_CR_IOCE | MC97_CR_FEIE | \
                                MC97_CR_LVBIE)

#define MC97_GC_GIE            BIT(0)
#define MC97_GC_COLD_RESET     BIT(1)
#define MC97_GC_WARM_RESET     BIT(2)
#define MC97_GC_ACLINK_OFF     BIT(3)
#define MC97_GC_PRIE           BIT(4)
#define MC97_GC_SRIE           BIT(5)
#define MC97_GC_TRIE           BIT(6)
#define MC97_GC_VALID_MASK     0x7f

#define MC97_GS_RCS            BIT(15)
#define MC97_GS_SRI            BIT(11)
#define MC97_GS_PRI            BIT(10)
#define MC97_GS_SCR            BIT(9)
#define MC97_GS_PCR            BIT(8)
#define MC97_GS_MOINT          BIT(2)
#define MC97_GS_MIINT          BIT(1)
#define MC97_GS_GSCI           BIT(0)
#define MC97_GS_WCLEAR_MASK    (MC97_GS_RCS | MC97_GS_SRI | \
                                MC97_GS_PRI | MC97_GS_MOINT | \
                                MC97_GS_MIINT | MC97_GS_GSCI)

#define MC97_GLOB_CNT          0x3c
#define MC97_GLOB_STA          0x40
#define MC97_ACC_SEMA          0x44

#define MC97_CODEC_VENDOR_QEMU 0x51454d01u /* "QEM" + generic modem rev 1 */

typedef struct IntelMC97BMRegs {
    uint32_t bdbar;
    uint8_t civ;
    uint8_t lvi;
    uint16_t sr;
    uint16_t picb;
    uint8_t piv;
    uint8_t cr;
} IntelMC97BMRegs;

struct IntelMC97State {
    PCIDevice dev;

    MemoryRegion nam;
    MemoryRegion nabm;

    IntelMC97BMRegs bm[2];
    uint32_t glob_cnt;
    uint32_t glob_sta;
    uint8_t cas;

    uint8_t codec_data[MC97_NAM_SIZE];
    uint8_t codec_slot;
    uint32_t codec_vendor_id;
};

static const uint32_t mc97_irq_status[2] = {
    MC97_GS_MIINT,
    MC97_GS_MOINT,
};

static AC97Codec intel_mc97_codec(IntelMC97State *s)
{
    AC97Codec codec;

    ac97_codec_init_le_bytes(&codec,
                             &s->codec_data[s->codec_slot * MC97_CODEC_STRIDE],
                             MC97_CODEC_STRIDE,
                             &ac97_codec_profile_mc97_modem,
                             s->codec_vendor_id);
    return codec;
}

static uint32_t intel_mc97_ready_bit(const IntelMC97State *s)
{
    if (s->glob_cnt & MC97_GC_ACLINK_OFF) {
        return 0;
    }

    return s->codec_slot ? MC97_GS_SCR : MC97_GS_PCR;
}

static uint32_t intel_mc97_global_status(const IntelMC97State *s)
{
    return s->glob_sta | intel_mc97_ready_bit(s);
}

static bool intel_mc97_bm_irq(const IntelMC97BMRegs *r)
{
    return ((r->sr & MC97_SR_FIFOE) && (r->cr & MC97_CR_FEIE)) ||
           ((r->sr & MC97_SR_BCIS) && (r->cr & MC97_CR_IOCE)) ||
           ((r->sr & MC97_SR_LVBCI) && (r->cr & MC97_CR_LVBIE));
}

static void intel_mc97_update_irq(IntelMC97State *s)
{
    bool level = false;
    unsigned i;

    for (i = 0; i < ARRAY_SIZE(s->bm); i++) {
        if (intel_mc97_bm_irq(&s->bm[i])) {
            s->glob_sta |= mc97_irq_status[i];
            level = true;
        } else {
            s->glob_sta &= ~mc97_irq_status[i];
        }
    }

    if (level) {
        pci_irq_assert(&s->dev);
    } else {
        pci_irq_deassert(&s->dev);
    }
}

static void intel_mc97_reset_bm(IntelMC97State *s, unsigned index)
{
    IntelMC97BMRegs *r = &s->bm[index];

    r->bdbar = 0;
    r->civ = 0;
    r->lvi = 0;
    r->sr = MC97_SR_DCH;
    r->picb = 0;
    r->piv = 0;
    r->cr &= MC97_CR_IRQ_MASK;
    s->glob_sta &= ~mc97_irq_status[index];
}

static void intel_mc97_reset_link(IntelMC97State *s)
{
    AC97Codec codec = intel_mc97_codec(s);

    intel_mc97_reset_bm(s, 0);
    intel_mc97_reset_bm(s, 1);
    ac97_codec_reset(&codec);
    s->cas = 0;
    s->glob_sta &= ~(MC97_GS_RCS | MC97_GS_SRI | MC97_GS_PRI |
                     MC97_GS_MOINT | MC97_GS_MIINT | MC97_GS_GSCI);
    intel_mc97_update_irq(s);
}

static void intel_mc97_reset(DeviceState *dev)
{
    IntelMC97State *s = INTEL_MC97(dev);

    s->glob_cnt = MC97_GC_COLD_RESET;
    s->glob_sta = 0;
    intel_mc97_reset_link(s);
}

static bool intel_mc97_decode_codec(IntelMC97State *s, hwaddr addr,
                                    AC97Codec *codec, unsigned *reg)
{
    unsigned slot = addr / MC97_CODEC_STRIDE;

    if (slot >= MC97_MAX_CODECS || slot != s->codec_slot) {
        return false;
    }

    *codec = intel_mc97_codec(s);
    *reg = addr % MC97_CODEC_STRIDE;
    return true;
}

static uint64_t intel_mc97_nam_read(void *opaque, hwaddr addr, unsigned size)
{
    IntelMC97State *s = opaque;
    AC97Codec codec;
    unsigned reg;

    s->cas = 0;
    if (size != 2 || !intel_mc97_decode_codec(s, addr, &codec, &reg)) {
        s->glob_sta |= MC97_GS_RCS;
        return size == 1 ? 0xff : size == 2 ? 0xffff : 0xffffffffu;
    }

    return ac97_codec_read(&codec, reg);
}

static void intel_mc97_nam_write(void *opaque, hwaddr addr, uint64_t value,
                                 unsigned size)
{
    IntelMC97State *s = opaque;
    AC97Codec codec;
    unsigned reg;

    s->cas = 0;
    if (size != 2 || !intel_mc97_decode_codec(s, addr, &codec, &reg)) {
        return;
    }

    ac97_codec_write(&codec, reg, value);
}

static const MemoryRegionOps intel_mc97_nam_ops = {
    .read = intel_mc97_nam_read,
    .write = intel_mc97_nam_write,
    .impl = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static uint64_t intel_mc97_bm_read(IntelMC97State *s, unsigned index,
                                   unsigned reg, unsigned size)
{
    IntelMC97BMRegs *r = &s->bm[index];

    switch (reg) {
    case 0x00:
        return size == 4 ? r->bdbar : ~0u;
    case 0x04:
        if (size == 1) {
            return r->civ;
        }
        if (size == 4) {
            return r->civ | (r->lvi << 8) | (r->sr << 16);
        }
        break;
    case 0x05:
        if (size == 1) {
            return r->lvi;
        }
        break;
    case 0x06:
        if (size == 1 || size == 2) {
            return r->sr & (size == 1 ? 0xff : 0xffff);
        }
        break;
    case 0x08:
        if (size == 2) {
            return r->picb;
        }
        break;
    case 0x0a:
        if (size == 1) {
            return r->piv;
        }
        break;
    case 0x0b:
        if (size == 1) {
            return r->cr;
        }
        break;
    default:
        break;
    }

    return size == 1 ? 0xff : size == 2 ? 0xffff : 0xffffffffu;
}

static void intel_mc97_bm_write(IntelMC97State *s, unsigned index,
                                unsigned reg, uint64_t value, unsigned size)
{
    IntelMC97BMRegs *r = &s->bm[index];

    switch (reg) {
    case 0x00:
        if (size == 4) {
            r->bdbar = value & ~3u;
        }
        break;
    case 0x05:
        if (size == 1) {
            r->lvi = value & 0x1f;
        }
        break;
    case 0x06:
        if (size == 1 || size == 2) {
            uint16_t writable = value & ~MC97_SR_RO_MASK;

            r->sr |= writable & ~MC97_SR_WCLEAR_MASK;
            r->sr &= ~(writable & MC97_SR_WCLEAR_MASK);
            intel_mc97_update_irq(s);
        }
        break;
    case 0x0b:
        if (size == 1) {
            uint8_t val = value & MC97_CR_VALID_MASK;

            if (val & MC97_CR_RR) {
                intel_mc97_reset_bm(s, index);
            } else {
                r->cr = val;
                if (val & MC97_CR_RPBM) {
                    r->sr &= ~MC97_SR_DCH;
                    r->civ = r->piv;
                    r->piv = (r->piv + 1) & 0x1f;
                } else {
                    r->sr |= MC97_SR_DCH;
                }
            }
            intel_mc97_update_irq(s);
        }
        break;
    default:
        break;
    }
}

static uint64_t intel_mc97_nabm_read(void *opaque, hwaddr addr, unsigned size)
{
    IntelMC97State *s = opaque;

    if (addr < 0x20) {
        unsigned index = addr >> 4;

        return intel_mc97_bm_read(s, index, addr & 0x0f, size);
    }

    switch (addr) {
    case MC97_GLOB_CNT:
        return size == 4 ? s->glob_cnt : 0xffffffffu;
    case MC97_GLOB_STA:
        return size == 4 ? intel_mc97_global_status(s) : 0xffffffffu;
    case MC97_ACC_SEMA:
        if (size == 1) {
            uint8_t value = s->cas;

            s->cas = 1;
            return value;
        }
        break;
    default:
        break;
    }

    return size == 1 ? 0xff : size == 2 ? 0xffff : 0xffffffffu;
}

static void intel_mc97_nabm_write(void *opaque, hwaddr addr, uint64_t value,
                                  unsigned size)
{
    IntelMC97State *s = opaque;

    if (addr < 0x20) {
        unsigned index = addr >> 4;

        intel_mc97_bm_write(s, index, addr & 0x0f, value, size);
        return;
    }

    switch (addr) {
    case MC97_GLOB_CNT:
        if (size == 4) {
            uint32_t val = value & MC97_GC_VALID_MASK;

            if (val & (MC97_GC_COLD_RESET | MC97_GC_WARM_RESET)) {
                intel_mc97_reset_link(s);
            }
            /* Warm reset is a self-clearing command bit. */
            val &= ~MC97_GC_WARM_RESET;
            s->glob_cnt = val;
        }
        break;
    case MC97_GLOB_STA:
        if (size == 4) {
            s->glob_sta &= ~(value & MC97_GS_WCLEAR_MASK);
            intel_mc97_update_irq(s);
        }
        break;
    default:
        break;
    }
}

static const MemoryRegionOps intel_mc97_nabm_ops = {
    .read = intel_mc97_nabm_read,
    .write = intel_mc97_nabm_write,
    .impl = {
        .min_access_size = 1,
        .max_access_size = 4,
    },
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static const VMStateDescription vmstate_intel_mc97_bm = {
    .name = "intel-mc97/bm",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32(bdbar, IntelMC97BMRegs),
        VMSTATE_UINT8(civ, IntelMC97BMRegs),
        VMSTATE_UINT8(lvi, IntelMC97BMRegs),
        VMSTATE_UINT16(sr, IntelMC97BMRegs),
        VMSTATE_UINT16(picb, IntelMC97BMRegs),
        VMSTATE_UINT8(piv, IntelMC97BMRegs),
        VMSTATE_UINT8(cr, IntelMC97BMRegs),
        VMSTATE_END_OF_LIST()
    },
};

static int intel_mc97_post_load(void *opaque, int version_id)
{
    IntelMC97State *s = opaque;

    intel_mc97_update_irq(s);
    return 0;
}

static const VMStateDescription vmstate_intel_mc97 = {
    .name = "intel-mc97",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = intel_mc97_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_PCI_DEVICE(dev, IntelMC97State),
        VMSTATE_STRUCT_ARRAY(bm, IntelMC97State, 2, 1,
                             vmstate_intel_mc97_bm, IntelMC97BMRegs),
        VMSTATE_UINT32(glob_cnt, IntelMC97State),
        VMSTATE_UINT32(glob_sta, IntelMC97State),
        VMSTATE_UINT8(cas, IntelMC97State),
        VMSTATE_BUFFER(codec_data, IntelMC97State),
        VMSTATE_UINT8(codec_slot, IntelMC97State),
        VMSTATE_UINT32(codec_vendor_id, IntelMC97State),
        VMSTATE_END_OF_LIST()
    },
};

static void intel_mc97_realize(PCIDevice *pci_dev, Error **errp)
{
    IntelMC97State *s = INTEL_MC97(pci_dev);

    if (s->codec_slot >= MC97_MAX_CODECS) {
        error_setg(errp, "intel-mc97 codec-slot must be 0 or 1");
        return;
    }
    if (s->codec_vendor_id == 0 || s->codec_vendor_id == UINT32_MAX) {
        error_setg(errp, "intel-mc97 codec-vendor-id must be a valid AC'97 ID");
        return;
    }

    pci_set_word(pci_dev->config + PCI_STATUS, PCI_STATUS_DEVSEL_MEDIUM);
    pci_set_byte(pci_dev->config + PCI_INTERRUPT_PIN, 1);

    memory_region_init_io(&s->nam, OBJECT(s), &intel_mc97_nam_ops, s,
                          "intel-mc97-nam", MC97_NAM_SIZE);
    memory_region_init_io(&s->nabm, OBJECT(s), &intel_mc97_nabm_ops, s,
                          "intel-mc97-nabm", MC97_NABM_SIZE);
    pci_register_bar(pci_dev, 0, PCI_BASE_ADDRESS_SPACE_IO, &s->nam);
    pci_register_bar(pci_dev, 1, PCI_BASE_ADDRESS_SPACE_IO, &s->nabm);

    intel_mc97_reset(DEVICE(s));
}

static const Property intel_mc97_properties[] = {
    DEFINE_PROP_UINT8("codec-slot", IntelMC97State, codec_slot, 0),
    DEFINE_PROP_UINT32("codec-vendor-id", IntelMC97State, codec_vendor_id,
                       MC97_CODEC_VENDOR_QEMU),
};

static void intel_mc97_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    k->realize = intel_mc97_realize;
    k->vendor_id = PCI_VENDOR_ID_INTEL;
    k->device_id = PCI_DEVICE_ID_INTEL_82801AA_6;
    k->revision = 0x01;
    k->class_id = PCI_CLASS_COMMUNICATION_MODEM;
    dc->desc = "Intel 82801AA MC97 Modem";
    dc->vmsd = &vmstate_intel_mc97;
    device_class_set_props(dc, intel_mc97_properties);
    device_class_set_legacy_reset(dc, intel_mc97_reset);
    set_bit(DEVICE_CATEGORY_NETWORK, dc->categories);
}

static const TypeInfo intel_mc97_info = {
    .name = TYPE_INTEL_MC97,
    .parent = TYPE_PCI_DEVICE,
    .instance_size = sizeof(IntelMC97State),
    .class_init = intel_mc97_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

static void intel_mc97_register_types(void)
{
    type_register_static(&intel_mc97_info);
}

type_init(intel_mc97_register_types)
