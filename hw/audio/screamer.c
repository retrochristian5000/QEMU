/*
 * QEMU PowerMac Awacs Screamer device support
 *
 * Copyright (c) 2016 Mark Cave-Ayland
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
#include "qemu/audio.h"
#include "qemu/error-report.h"
#include "qemu/log.h"
#include "qemu/module.h"
#include "hw/audio/screamer.h"
#include "hw/core/qdev-properties.h"
#include "migration/vmstate.h"
#include "system/dma.h"

enum {
    SCREAMER_SND_CTRL = 0,
    SCREAMER_CODEC_CTRL,
    SCREAMER_CODEC_STAT,
    SCREAMER_CLIP_COUNT,
    SCREAMER_BYTE_SWAP,
    SCREAMER_FRAME_COUNT,
};

#define SCREAMER_CODEC_NEWECMD       0x01000000
#define SCREAMER_CODEC_VALID         0x00400000
/* Guest-visible compatibility values; not a physical supplier claim. */
#define SCREAMER_CODEC_MFG_COMPAT    0x00000100
#define SCREAMER_CODEC_REV_COMPAT    0x00003000

#define SCREAMER_CODEC_RECALIBRATE   0x004
#define SCREAMER_CODEC_CMUTE         0x080
#define SCREAMER_CODEC_AMUTE         0x200

#define SCREAMER_DAV_MMIO_SIZE       0x1000
#define SCREAMER_SAMPLE_BYTES        4

static const uint32_t screamer_rates[8] = {
    44100, 29400, 22050, 17640, 14700, 11025, 8820, 7350,
};

static void screamer_clear_queue(ScreamerState *s)
{
    s->tx_rpos = 0;
    s->tx_wpos = 0;
    s->tx_count = 0;
}

static void screamer_update_volume(ScreamerState *s)
{
    uint16_t control = s->codec_ctrl_regs[1];
    uint16_t out_a = s->codec_ctrl_regs[2];
    uint16_t out_c = s->codec_ctrl_regs[4];
    bool a_muted = control & SCREAMER_CODEC_AMUTE;
    bool c_muted = control & SCREAMER_CODEC_CMUTE;
    uint8_t a_left = a_muted ? 0 : (uint8_t)((0xf - (out_a & 0xf)) * 17);
    uint8_t a_right = a_muted ? 0 :
        (uint8_t)((0xf - ((out_a >> 6) & 0xf)) * 17);
    uint8_t c_left = c_muted ? 0 : (uint8_t)((0xf - (out_c & 0xf)) * 17);
    uint8_t c_right = c_muted ? 0 :
        (uint8_t)((0xf - ((out_c >> 6) & 0xf)) * 17);
    uint8_t left = MAX(a_left, c_left);
    uint8_t right = MAX(a_right, c_right);

    if (s->voice) {
        audio_be_set_volume_out_lr(s->audio_be, s->voice,
                                   left == 0 && right == 0, left, right);
    }
}

static void screamer_output_cb(void *opaque, int free_b);

static bool screamer_update_settings(ScreamerState *s, Error **errp)
{
    struct audsettings as = {
        .freq = (int)s->rate,
        .nchannels = 2,
        .fmt = AUDIO_FORMAT_S16,
        .big_endian = !(s->regs[SCREAMER_BYTE_SWAP] & 1),
    };

    s->voice = audio_be_open_out(s->audio_be, s->voice, "screamer.out",
                                 s, screamer_output_cb, &as);
    if (!s->voice) {
        if (errp) {
            error_setg(errp, "could not open Screamer output voice");
        } else {
            error_report("screamer: could not reopen output voice");
        }
        return false;
    }

    audio_be_set_active_out(s->audio_be, s->voice, true);
    screamer_update_volume(s);
    return true;
}

static void screamer_tx_refill(ScreamerState *s, DBDMA_io *io)
{
    while (io->len > 0 && s->tx_count < SCREAMER_BUFFER_SIZE) {
        uint32_t room = SCREAMER_BUFFER_SIZE - s->tx_count;
        uint32_t contiguous = SCREAMER_BUFFER_SIZE - s->tx_wpos;
        uint32_t len = MIN((uint32_t)io->len, MIN(room, contiguous));

        dma_memory_read(&address_space_memory, io->addr,
                        &s->tx_buffer[s->tx_wpos], len,
                        MEMTXATTRS_UNSPECIFIED);
        io->addr += len;
        io->len -= (int32_t)len;
        s->tx_wpos = (s->tx_wpos + len) % SCREAMER_BUFFER_SIZE;
        s->tx_count += len;
    }

    if (io->len == 0) {
        io->dma_end(io);
    }
}

static void screamer_output_cb(void *opaque, int free_b)
{
    ScreamerState *s = opaque;

    while (free_b > 0) {
        size_t len;
        size_t written;

        if (s->tx_count == 0 && s->dbdma) {
            DBDMA_io *io = &s->dbdma->channels[s->tx_channel].io;

            if (io->processing) {
                screamer_tx_refill(s, io);
            }
        }

        if (s->tx_count == 0) {
            break;
        }

        len = MIN((size_t)free_b,
                  (size_t)MIN(s->tx_count,
                              SCREAMER_BUFFER_SIZE - s->tx_rpos));
        written = audio_be_write(s->audio_be, s->voice,
                                 &s->tx_buffer[s->tx_rpos], len);
        if (written == 0) {
            break;
        }

        s->tx_rpos = (s->tx_rpos + (uint32_t)written) %
                     SCREAMER_BUFFER_SIZE;
        s->tx_count -= (uint32_t)written;
        free_b -= (int)written;
        s->regs[SCREAMER_FRAME_COUNT] +=
            (uint32_t)(written / SCREAMER_SAMPLE_BYTES);

        if (s->dbdma) {
            DBDMA_io *io = &s->dbdma->channels[s->tx_channel].io;

            if (io->processing) {
                screamer_tx_refill(s, io);
            }
        }

        if (written < len) {
            break;
        }
    }
}

static void screamer_tx_dma(DBDMA_io *io)
{
    ScreamerState *s = io->opaque;

    screamer_tx_refill(s, io);
}

static void screamer_tx_flush(DBDMA_io *io)
{
    ScreamerState *s = io->opaque;

    screamer_clear_queue(s);
    io->processing = false;
}

static void screamer_rx_dma(DBDMA_io *io)
{
    static const uint8_t silence[4096];
    uint32_t remaining = (uint32_t)io->len;
    hwaddr addr = io->addr;

    while (remaining > 0) {
        size_t len = MIN((size_t)remaining, sizeof(silence));

        dma_memory_write(&address_space_memory, addr, silence, len,
                         MEMTXATTRS_UNSPECIFIED);
        addr += len;
        remaining -= (uint32_t)len;
    }

    io->addr = addr;
    io->len = 0;
    io->dma_end(io);
}

static void screamer_rx_flush(DBDMA_io *io)
{
    io->processing = false;
}

void macio_screamer_register_dma(ScreamerState *s, DBDMAState *dbdma,
                                 int tx_channel, int rx_channel)
{
    s->dbdma = dbdma;
    s->tx_channel = tx_channel;
    s->rx_channel = rx_channel;

    DBDMA_register_channel(dbdma, tx_channel, s->dma_tx_irq,
                           screamer_tx_dma, screamer_tx_flush, s);
    DBDMA_register_channel(dbdma, rx_channel, s->dma_rx_irq,
                           screamer_rx_dma, screamer_rx_flush, s);
}

static void screamer_control_write(ScreamerState *s, uint32_t value)
{
    uint32_t rate = screamer_rates[(value >> 8) & 7];

    s->regs[SCREAMER_SND_CTRL] = value;
    if (rate != s->rate) {
        s->rate = rate;
        screamer_clear_queue(s);
        screamer_update_settings(s, NULL);
    }
}

static void screamer_codec_write(ScreamerState *s, uint32_t value)
{
    unsigned int reg = (value >> 12) & 7;
    uint16_t data = (uint16_t)(value & 0xfff);

    if (reg == 1) {
        data &= (uint16_t)~SCREAMER_CODEC_RECALIBRATE;
    }

    s->regs[SCREAMER_CODEC_CTRL] = value;
    s->codec_ctrl_regs[reg] = data;

    if (reg == 1 || reg == 2 || reg == 4) {
        screamer_update_volume(s);
    }
}

static uint64_t screamer_read(void *opaque, hwaddr addr, unsigned int size)
{
    ScreamerState *s = opaque;
    unsigned int reg = addr >> 4;
    uint32_t value;

    switch (reg) {
    case SCREAMER_SND_CTRL:
        return s->regs[reg];
    case SCREAMER_CODEC_CTRL:
        return s->regs[reg] & ~SCREAMER_CODEC_NEWECMD;
    case SCREAMER_CODEC_STAT:
        if (s->codec_ctrl_regs[7] & 1) {
            unsigned int codec_reg = (s->codec_ctrl_regs[7] & 0xe) >> 1;

            s->codec_ctrl_regs[7] &= (uint16_t)~1;
            return (uint32_t)s->codec_ctrl_regs[codec_reg] << 4;
        }

        value = s->regs[reg] & ~0xff00u;
        return value | SCREAMER_CODEC_MFG_COMPAT |
               SCREAMER_CODEC_REV_COMPAT | SCREAMER_CODEC_VALID;
    case SCREAMER_CLIP_COUNT:
    case SCREAMER_BYTE_SWAP:
    case SCREAMER_FRAME_COUNT:
        return s->regs[reg];
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "screamer: invalid register read at 0x%"
                      HWADDR_PRIx " size %u\n", addr, size);
        return 0;
    }
}

static void screamer_write(void *opaque, hwaddr addr, uint64_t value,
                           unsigned int size)
{
    ScreamerState *s = opaque;
    unsigned int reg = addr >> 4;
    uint32_t value32 = (uint32_t)value;
    uint32_t old;

    switch (reg) {
    case SCREAMER_SND_CTRL:
        screamer_control_write(s, value32);
        break;
    case SCREAMER_CODEC_CTRL:
        screamer_codec_write(s, value32);
        break;
    case SCREAMER_CODEC_STAT:
    case SCREAMER_CLIP_COUNT:
        s->regs[reg] = value32;
        break;
    case SCREAMER_BYTE_SWAP:
        old = s->regs[reg];
        s->regs[reg] = value32;
        if ((old ^ value32) & 1) {
            screamer_clear_queue(s);
            screamer_update_settings(s, NULL);
        }
        break;
    default:
        qemu_log_mask(LOG_GUEST_ERROR,
                      "screamer: invalid register write at 0x%"
                      HWADDR_PRIx " size %u value 0x%" PRIx64 "\n",
                      addr, size, value);
        break;
    }
}

static const MemoryRegionOps screamer_ops = {
    .read = screamer_read,
    .write = screamer_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = { .min_access_size = 4, .max_access_size = 4 },
    .impl = { .min_access_size = 4, .max_access_size = 4 },
};

static const VMStateDescription vmstate_screamer = {
    .name = "screamer",
    .unmigratable = 1,
};

static void screamer_reset_hold(Object *obj, ResetType type)
{
    ScreamerState *s = SCREAMER(obj);

    memset(s->regs, 0, sizeof(s->regs));
    memset(s->codec_ctrl_regs, 0, sizeof(s->codec_ctrl_regs));
    s->rate = screamer_rates[0];
    screamer_clear_queue(s);
    if (s->voice) {
        screamer_update_settings(s, NULL);
    }
}

static void screamer_realize(DeviceState *dev, Error **errp)
{
    ScreamerState *s = SCREAMER(dev);

    if (!audio_be_check(&s->audio_be, errp)) return;
    s->rate = screamer_rates[0];
    if (!screamer_update_settings(s, errp)) return;
}

static void screamer_unrealize(DeviceState *dev)
{
    ScreamerState *s = SCREAMER(dev);
    if (s->voice) {
        audio_be_close_out(s->audio_be, s->voice);
        s->voice = NULL;
    }
}

static void screamer_init(Object *obj)
{
    ScreamerState *s = SCREAMER(obj);
    SysBusDevice *sbd = SYS_BUS_DEVICE(obj);
    memory_region_init_io(&s->mem, obj, &screamer_ops, s,
                          "screamer-dav", SCREAMER_DAV_MMIO_SIZE);
    sysbus_init_mmio(sbd, &s->mem);
    sysbus_init_irq(sbd, &s->irq);
    sysbus_init_irq(sbd, &s->dma_tx_irq);
    sysbus_init_irq(sbd, &s->dma_rx_irq);
}

static const Property screamer_properties[] = {
    DEFINE_AUDIO_PROPERTIES(ScreamerState, audio_be),
};

static void screamer_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);
    ResettableClass *rc = RESETTABLE_CLASS(oc);
    dc->realize = screamer_realize;
    dc->unrealize = screamer_unrealize;
    dc->desc = "Apple Screamer audio codec";
    dc->vmsd = &vmstate_screamer;
    device_class_set_props(dc, screamer_properties);
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
    rc->phases.hold = screamer_reset_hold;
}

static const TypeInfo screamer_info = {
    .name = TYPE_SCREAMER,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(ScreamerState),
    .instance_init = screamer_init,
    .class_init = screamer_class_init,
};

static void screamer_register_types(void)
{
    type_register_static(&screamer_info);
}

type_init(screamer_register_types)
