/*
 * VIA south bridges sound support
 *
 * Copyright (c) 2022-2023 BALATON Zoltan
 *
 * This work is licensed under the GNU GPL license version 2 or later.
 */

/*
 * TODO: This is only a basic implementation of one audio playback channel
 *       more functionality should be added here.
 */

#include "qemu/osdep.h"
#include "qemu/log.h"
#include "hw/audio/ac97-codec.h"
#include "hw/isa/vt82c686.h"
#include "ac97.h"
#include "trace.h"

#define CLEN_IS_EOL(x)  ((x)->clen & BIT(31))
#define CLEN_IS_FLAG(x) ((x)->clen & BIT(30))
#define CLEN_IS_STOP(x) ((x)->clen & BIT(29))
#define CLEN_LEN(x)     ((x)->clen & 0xffffff)

#define STAT_ACTIVE BIT(7)
#define STAT_PAUSED BIT(6)
#define STAT_TRIG   BIT(3)
#define STAT_STOP   BIT(2)
#define STAT_EOL    BIT(1)
#define STAT_FLAG   BIT(0)

#define CNTL_START  BIT(7)
#define CNTL_TERM   BIT(6)
#define CNTL_PAUSE  BIT(3)

#define CODEC_VOL(vol, mask)  ((255 * ((vol) & mask)) / mask)

static void open_voice_out(ViaAC97State *s);

static AC97Codec via_ac97_codec(ViaAC97State *s)
{
    AC97Codec codec;

    ac97_codec_init_u16(&codec, s->codec_regs,
                        &ac97_codec_profile_stac9766, 0);
    return codec;
}

static uint16_t codec_read(ViaAC97State *s, unsigned addr)
{
    AC97Codec codec = via_ac97_codec(s);

    return ac97_codec_read(&codec, addr);
}

static void codec_volume_set_out(ViaAC97State *s)
{
    int lvol, rvol, mute;
    uint16_t master = codec_read(s, AC97_Master_Volume_Mute);
    uint16_t pcm = codec_read(s, AC97_PCM_Out_Volume_Mute);

    lvol = 255 - CODEC_VOL(master >> 8, 0x1f);
    lvol *= 255 - CODEC_VOL(pcm >> 8, 0x1f);
    lvol /= 255;
    rvol = 255 - CODEC_VOL(master, 0x1f);
    rvol *= 255 - CODEC_VOL(pcm, 0x1f);
    rvol /= 255;
    mute = master >> MUTE_SHIFT;
    mute |= pcm >> MUTE_SHIFT;
    audio_be_set_volume_out_lr(s->audio_be, s->vo, mute, lvol, rvol);
}

static void codec_apply_events(ViaAC97State *s, uint32_t events)
{
    if (events & AC97_CODEC_EVENT_VOLUME_OUT) {
        codec_volume_set_out(s);
    }
    if (events & (AC97_CODEC_EVENT_FRONT_DAC_RATE |
                  AC97_CODEC_EVENT_LR_ADC_RATE)) {
        open_voice_out(s);
    }
}

static void fetch_sgd(ViaAC97SGDChannel *c, PCIDevice *d)
{
    uint32_t b[2];

    if (c->curr < c->base) {
        c->curr = c->base;
    }
    if (unlikely(pci_dma_read(d, c->curr, b, sizeof(b)) != MEMTX_OK)) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "via-ac97: DMA error reading SGD table\n");
        return;
    }
    c->addr = le32_to_cpu(b[0]);
    c->clen = le32_to_cpu(b[1]);
    trace_via_ac97_sgd_fetch(c->curr, c->addr, CLEN_IS_STOP(c) ? 'S' : '-',
                             CLEN_IS_EOL(c) ? 'E' : '-',
                             CLEN_IS_FLAG(c) ? 'F' : '-', CLEN_LEN(c));
}

static void out_cb(void *opaque, int avail)
{
    ViaAC97State *s = opaque;
    ViaAC97SGDChannel *c = &s->aur;
    int temp, to_copy, copied;
    bool stop = false;
    QEMU_UNINITIALIZED uint8_t tmpbuf[4096];

    if (c->stat & STAT_PAUSED) {
        return;
    }
    c->stat |= STAT_ACTIVE;
    while (avail && !stop) {
        if (!c->clen) {
            fetch_sgd(c, &s->dev);
        }
        temp = MIN(CLEN_LEN(c), avail);
        while (temp) {
            to_copy = MIN(temp, sizeof(tmpbuf));
            pci_dma_read(&s->dev, c->addr, tmpbuf, to_copy);
            copied = audio_be_write(s->audio_be, s->vo, tmpbuf, to_copy);
            if (!copied) {
                stop = true;
                break;
            }
            temp -= copied;
            avail -= copied;
            c->addr += copied;
            c->clen -= copied;
        }
        if (CLEN_LEN(c) == 0) {
            c->curr += 8;
            if (CLEN_IS_EOL(c)) {
                c->stat |= STAT_EOL;
                if (c->type & CNTL_START) {
                    c->curr = c->base;
                    c->stat |= STAT_PAUSED;
                } else {
                    c->stat &= ~STAT_ACTIVE;
                    audio_be_set_active_out(s->audio_be, s->vo, 0);
                }
                if (c->type & STAT_EOL) {
                    via_isa_set_irq(&s->dev, 0, 1);
                }
            }
            if (CLEN_IS_FLAG(c)) {
                c->stat |= STAT_FLAG;
                c->stat |= STAT_PAUSED;
                if (c->type & STAT_FLAG) {
                    via_isa_set_irq(&s->dev, 0, 1);
                }
            }
            if (CLEN_IS_STOP(c)) {
                c->stat |= STAT_STOP;
                c->stat |= STAT_PAUSED;
            }
            c->clen = 0;
            stop = true;
        }
    }
}

static void open_voice_out(ViaAC97State *s)
{
    struct audsettings as = {
        .freq = codec_read(s, AC97_PCM_Front_DAC_Rate),
        .nchannels = s->aur.type & BIT(4) ? 2 : 1,
        .fmt = s->aur.type & BIT(5) ? AUDIO_FORMAT_S16 : AUDIO_FORMAT_S8,
        .big_endian = false,
    };
    s->vo = audio_be_open_out(s->audio_be, s->vo, "via-ac97.out", s, out_cb, &as);
}

static uint64_t sgd_read(void *opaque, hwaddr addr, unsigned size)
{
    ViaAC97State *s = opaque;
    uint64_t val = 0;

    switch (addr) {
    case 0:
        val = s->aur.stat;
        if (s->aur.type & CNTL_START) {
            val |= STAT_TRIG;
        }
        break;
    case 1:
        val = s->aur.stat & STAT_PAUSED ? BIT(3) : 0;
        break;
    case 2:
        val = s->aur.type;
        break;
    case 4:
        val = s->aur.curr;
        break;
    case 0xc:
        val = CLEN_LEN(&s->aur);
        break;
    case 0x10:
        /* silence unimplemented log message that happens at every IRQ */
        break;
    case 0x80:
        val = s->ac97_cmd;
        break;
    case 0x84:
        val = s->aur.stat & STAT_FLAG;
        if (s->aur.stat & STAT_EOL) {
            val |= BIT(4);
        }
        if (s->aur.stat & STAT_STOP) {
            val |= BIT(8);
        }
        if (s->aur.stat & STAT_ACTIVE) {
            val |= BIT(12);
        }
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "via-ac97: Unimplemented register read 0x%"
                      HWADDR_PRIx"\n", addr);
    }
    trace_via_ac97_sgd_read(addr, size, val);
    return val;
}

static void sgd_write(void *opaque, hwaddr addr, uint64_t val, unsigned size)
{
    ViaAC97State *s = opaque;

    trace_via_ac97_sgd_write(addr, size, val);
    switch (addr) {
    case 0:
        if (val & STAT_STOP) {
            s->aur.stat &= ~STAT_PAUSED;
        }
        if (val & STAT_EOL) {
            s->aur.stat &= ~(STAT_EOL | STAT_PAUSED);
            if (s->aur.type & STAT_EOL) {
                via_isa_set_irq(&s->dev, 0, 0);
            }
        }
        if (val & STAT_FLAG) {
            s->aur.stat &= ~(STAT_FLAG | STAT_PAUSED);
            if (s->aur.type & STAT_FLAG) {
                via_isa_set_irq(&s->dev, 0, 0);
            }
        }
        break;
    case 1:
        if (val & CNTL_START) {
            audio_be_set_active_out(s->audio_be, s->vo, 1);
            s->aur.stat = STAT_ACTIVE;
        }
        if (val & CNTL_TERM) {
            audio_be_set_active_out(s->audio_be, s->vo, 0);
            s->aur.stat &= ~(STAT_ACTIVE | STAT_PAUSED);
            s->aur.clen = 0;
        }
        if (val & CNTL_PAUSE) {
            audio_be_set_active_out(s->audio_be, s->vo, 0);
            s->aur.stat &= ~STAT_ACTIVE;
            s->aur.stat |= STAT_PAUSED;
        } else if (!(val & CNTL_PAUSE) && (s->aur.stat & STAT_PAUSED)) {
            audio_be_set_active_out(s->audio_be, s->vo, 1);
            s->aur.stat |= STAT_ACTIVE;
            s->aur.stat &= ~STAT_PAUSED;
        }
        break;
    case 2:
    {
        uint32_t oldval = s->aur.type;
        s->aur.type = val;
        if ((oldval & 0x30) != (val & 0x30)) {
            open_voice_out(s);
        }
        break;
    }
    case 4:
        s->aur.base = val & ~1ULL;
        s->aur.curr = s->aur.base;
        break;
    case 0x80:
        if (val >> 30) {
            /* we only have primary codec */
            break;
        }
        if (val & BIT(23)) { /* read reg */
            s->ac97_cmd = val & 0xc0ff0000ULL;
            s->ac97_cmd |= codec_read(s, (val >> 16) & 0x7f);
            s->ac97_cmd |= BIT(25); /* data valid */
        } else {
            AC97Codec codec = via_ac97_codec(s);
            uint32_t events;
            unsigned reg = (val >> 16) & 0x7f;

            trace_via_ac97_codec_write(reg, val);
            s->ac97_cmd = val & 0xc0ffffffULL;
            events = ac97_codec_write(&codec, reg, val);
            codec_apply_events(s, events);
        }
        break;
    case 0xc:
    case 0x84:
        /* Read only */
        break;
    default:
        qemu_log_mask(LOG_UNIMP, "via-ac97: Unimplemented register write 0x%"
                      HWADDR_PRIx"\n", addr);
    }
}

static const MemoryRegionOps sgd_ops = {
    .read = sgd_read,
    .write = sgd_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static uint64_t fm_read(void *opaque, hwaddr addr, unsigned size)
{
    qemu_log_mask(LOG_UNIMP, "%s: 0x%"HWADDR_PRIx" %d\n", __func__, addr, size);
    return 0;
}

static void fm_write(void *opaque, hwaddr addr, uint64_t val, unsigned size)
{
    qemu_log_mask(LOG_UNIMP, "%s: 0x%"HWADDR_PRIx" %d <= 0x%"PRIX64"\n",
                  __func__, addr, size, val);
}

static const MemoryRegionOps fm_ops = {
    .read = fm_read,
    .write = fm_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static uint64_t midi_read(void *opaque, hwaddr addr, unsigned size)
{
    qemu_log_mask(LOG_UNIMP, "%s: 0x%"HWADDR_PRIx" %d\n", __func__, addr, size);
    return 0;
}

static void midi_write(void *opaque, hwaddr addr, uint64_t val, unsigned size)
{
    qemu_log_mask(LOG_UNIMP, "%s: 0x%"HWADDR_PRIx" %d <= 0x%"PRIX64"\n",
                  __func__, addr, size, val);
}

static const MemoryRegionOps midi_ops = {
    .read = midi_read,
    .write = midi_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void via_ac97_reset(DeviceState *dev)
{
    ViaAC97State *s = VIA_AC97(dev);
    AC97Codec codec = via_ac97_codec(s);

    ac97_codec_reset(&codec);
}

static void via_ac97_realize(PCIDevice *pci_dev, Error **errp)
{
    ViaAC97State *s = VIA_AC97(pci_dev);
    Object *o = OBJECT(s);

    if (!audio_be_check(&s->audio_be, errp)) {
        return;
    }

    /*
     * Command register Bus Master bit is documented to be fixed at 0 but it's
     * needed for PCI DMA to work in QEMU. The pegasos2 firmware writes 0 here
     * and the AmigaOS driver writes 1 only enabling IO bit which works on
     * real hardware. So set it here and fix it to 1 to allow DMA.
     */
    pci_set_word(pci_dev->config + PCI_COMMAND, PCI_COMMAND_MASTER);
    pci_set_word(pci_dev->wmask + PCI_COMMAND, PCI_COMMAND_IO);
    pci_set_word(pci_dev->config + PCI_STATUS,
                 PCI_STATUS_CAP_LIST | PCI_STATUS_DEVSEL_MEDIUM);
    pci_set_long(pci_dev->config + PCI_INTERRUPT_PIN, 0x03);
    pci_set_byte(pci_dev->config + 0x40, 1); /* codec ready */

    memory_region_init_io(&s->sgd, o, &sgd_ops, s, "via-ac97.sgd", 256);
    pci_register_bar(pci_dev, 0, PCI_BASE_ADDRESS_SPACE_IO, &s->sgd);
    memory_region_init_io(&s->fm, o, &fm_ops, s, "via-ac97.fm", 4);
    pci_register_bar(pci_dev, 1, PCI_BASE_ADDRESS_SPACE_IO, &s->fm);
    memory_region_init_io(&s->midi, o, &midi_ops, s, "via-ac97.midi", 4);
    pci_register_bar(pci_dev, 2, PCI_BASE_ADDRESS_SPACE_IO, &s->midi);
}

static void via_ac97_exit(PCIDevice *dev)
{
    ViaAC97State *s = VIA_AC97(dev);

    audio_be_close_out(s->audio_be, s->vo);
}

static const Property via_ac97_properties[] = {
    DEFINE_AUDIO_PROPERTIES(ViaAC97State, audio_be),
};

static void via_ac97_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    k->realize = via_ac97_realize;
    k->exit = via_ac97_exit;
    k->vendor_id = PCI_VENDOR_ID_VIA;
    k->device_id = PCI_DEVICE_ID_VIA_AC97;
    k->revision = 0x50;
    k->class_id = PCI_CLASS_MULTIMEDIA_AUDIO;
    device_class_set_props(dc, via_ac97_properties);
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
    dc->desc = "VIA AC97";
    device_class_set_legacy_reset(dc, via_ac97_reset);
    /* Reason: Part of a south bridge chip */
    dc->user_creatable = false;
}

static const TypeInfo via_ac97_info = {
    .name          = TYPE_VIA_AC97,
    .parent        = TYPE_PCI_DEVICE,
    .instance_size = sizeof(ViaAC97State),
    .class_init    = via_ac97_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

static void via_mc97_realize(PCIDevice *pci_dev, Error **errp)
{
    pci_set_word(pci_dev->config + PCI_COMMAND,
                 PCI_COMMAND_INVALIDATE | PCI_COMMAND_VGA_PALETTE);
    pci_set_word(pci_dev->config + PCI_STATUS, PCI_STATUS_DEVSEL_MEDIUM);
    pci_set_long(pci_dev->config + PCI_INTERRUPT_PIN, 0x03);
}

static void via_mc97_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    PCIDeviceClass *k = PCI_DEVICE_CLASS(klass);

    k->realize = via_mc97_realize;
    k->vendor_id = PCI_VENDOR_ID_VIA;
    k->device_id = PCI_DEVICE_ID_VIA_MC97;
    k->class_id = PCI_CLASS_COMMUNICATION_OTHER;
    k->revision = 0x30;
    set_bit(DEVICE_CATEGORY_NETWORK, dc->categories);
    dc->desc = "VIA MC97";
    /* Reason: Part of a south bridge chip */
    dc->user_creatable = false;
}

static const TypeInfo via_mc97_info = {
    .name          = TYPE_VIA_MC97,
    .parent        = TYPE_PCI_DEVICE,
    .instance_size = sizeof(PCIDevice),
    .class_init    = via_mc97_class_init,
    .interfaces = (const InterfaceInfo[]) {
        { INTERFACE_CONVENTIONAL_PCI_DEVICE },
        { },
    },
};

static void via_ac97_register_types(void)
{
    type_register_static(&via_ac97_info);
    type_register_static(&via_mc97_info);
}

type_init(via_ac97_register_types)
