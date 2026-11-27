/*
 * QEMU PC speaker emulation
 *
 * Copyright (c) 2006 Joachim Henke
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
#include "hw/isa/isa.h"
#include "hw/audio/model.h"
#include "qemu/audio.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "qemu/error-report.h"
#include "hw/timer/i8254.h"
#include "migration/vmstate.h"
#include "hw/audio/pcspk.h"
#include "qapi/error.h"
#include "qom/object.h"
#include "trace.h"
#include "pcspk-signal.h"

#define PCSPK_BUF_LEN 1792
#define PCSPK_SAMPLE_RATE 32000
#define PCSPK_MAX_FREQ (PCSPK_SAMPLE_RATE >> 1)
#define PCSPK_MIN_COUNT DIV_ROUND_UP(PIT_FREQ, PCSPK_MAX_FREQ)

OBJECT_DECLARE_SIMPLE_TYPE(PCSpkState, PC_SPEAKER)

struct PCSpkState {
    ISADevice parent_obj;

    MemoryRegion ioport;
    uint32_t iobase;
    uint8_t sample_buf[PCSPK_BUF_LEN];
    AudioBackend *audio_be;
    SWVoiceOut *voice;
    PITCommonState *pit;
    unsigned int pit_count;
    uint32_t phase;
    uint8_t data_on;
    uint8_t dummy_refresh_clock;
};

static const char *s_spk = "pcspk";

static void pcspk_callback(void *opaque, int free)
{
    PCSpkState *s = opaque;
    PITChannelInfo ch;
    uint32_t count, period;

    pit_get_channel_info(s->pit, 2, &ch);
    count = ch.mode == 3 && ch.gate && s->data_on &&
            ch.initial_count >= PCSPK_MIN_COUNT &&
            ch.initial_count <= 0x10000 ? ch.initial_count : 0;
    if (s->pit_count != count) {
        s->pit_count = count;
        s->phase = 0;
    }
    period = count * PCSPK_SAMPLE_RATE;

    while (free > 0) {
        unsigned int n = MIN((unsigned int)free, sizeof(s->sample_buf));
        unsigned int written;

        if (period) {
            uint32_t phase = s->phase;

            for (unsigned int i = 0; i < n; i++) {
                s->sample_buf[i] =
                    pcspk_square_sample(phase, count, PCSPK_SAMPLE_RATE);
                phase += PIT_FREQ;
                if (phase >= period) {
                    phase -= period;
                }
            }
        } else {
            memset(s->sample_buf, 128, n);
        }
        written = audio_be_write(s->audio_be, s->voice, s->sample_buf, n);
        if (!written) {
            break;
        }
        if (period) {
            s->phase = pcspk_advance_phase(s->phase, period, PIT_FREQ,
                                           written);
        }
        free -= written;
    }
}

static int pcspk_audio_init(PCSpkState *s)
{
    struct audsettings as = {PCSPK_SAMPLE_RATE, 1, AUDIO_FORMAT_U8, 0};

    if (s->voice) {
        /* already initialized */
        return 0;
    }

    s->voice = audio_be_open_out(s->audio_be, s->voice, s_spk, s, pcspk_callback, &as);
    if (!s->voice) {
        error_report("pcspk: Could not open voice");
        return -1;
    }

    return 0;
}

static uint64_t pcspk_io_read(void *opaque, hwaddr addr,
                              unsigned size)
{
    PCSpkState *s = opaque;
    PITChannelInfo ch;
    uint8_t val;

    pit_get_channel_info(s->pit, 2, &ch);

    val = ch.gate | (s->data_on << 1) |
       pcspk_refresh_bit(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)) |
       (ch.out << 5);

    trace_pcspk_io_read(s->iobase, val);

    return val;
}

static void pcspk_io_write(void *opaque, hwaddr addr, uint64_t val,
                           unsigned size)
{
    PCSpkState *s = opaque;
    const int gate = val & 1;
    PITChannelInfo ch;

    pit_get_channel_info(s->pit, 2, &ch);
    trace_pcspk_io_write(s->iobase, val);

    s->data_on = (val >> 1) & 1;
    pit_set_gate(s->pit, 2, gate);
    if (gate && !ch.gate) {
        s->phase = 0;
    }
    if (s->voice) {
        audio_be_set_active_out(s->audio_be, s->voice, gate & s->data_on);
    }
}

static const MemoryRegionOps pcspk_io_ops = {
    .read = pcspk_io_read,
    .write = pcspk_io_write,
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
};

static void pcspk_initfn(Object *obj)
{
    PCSpkState *s = PC_SPEAKER(obj);

    memory_region_init_io(&s->ioport, OBJECT(s), &pcspk_io_ops, s, "pcspk", 1);
}

static void pcspk_realizefn(DeviceState *dev, Error **errp)
{
    ISADevice *isadev = ISA_DEVICE(dev);
    PCSpkState *s = PC_SPEAKER(dev);

    if (!s->pit) {
        error_setg(errp, "pcspk: No \"pit\" set or available");
        return;
    }

    isa_register_ioport(isadev, &s->ioport, s->iobase);

    if (s->audio_be && audio_be_check(&s->audio_be, errp)) {
        pcspk_audio_init(s);
        return;
    }
}

static void pcspk_reset(DeviceState *dev)
{
    PCSpkState *s = PC_SPEAKER(dev);

    s->data_on = 0;
    s->dummy_refresh_clock = 0;
    s->pit_count = 0;
    s->phase = 0;
    if (s->voice) {
        audio_be_set_active_out(s->audio_be, s->voice, false);
    }
}

static int pcspk_post_load(void *opaque, int version_id)
{
    PCSpkState *s = opaque;
    PITChannelInfo ch;

    s->data_on &= 1;
    s->pit_count = 0;
    s->phase = 0;
    if (s->voice) {
        pit_get_channel_info(s->pit, 2, &ch);
        audio_be_set_active_out(s->audio_be, s->voice,
                                ch.gate && s->data_on);
    }
    return 0;
}

static const VMStateDescription vmstate_spk = {
    .name = "pcspk",
    .version_id = 1,
    .minimum_version_id = 1,
    .post_load = pcspk_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(data_on, PCSpkState),
        VMSTATE_UINT8(dummy_refresh_clock, PCSpkState),
        VMSTATE_END_OF_LIST()
    }
};

static const Property pcspk_properties[] = {
    DEFINE_AUDIO_PROPERTIES(PCSpkState, audio_be),
    DEFINE_PROP_UINT32("iobase", PCSpkState, iobase,  0x61),
    DEFINE_PROP_LINK("pit", PCSpkState, pit, TYPE_PIT_COMMON, PITCommonState *),
};

static void pcspk_class_initfn(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = pcspk_realizefn;
    dc->desc = "PC speaker (PIT-driven motherboard audio)";
    set_bit(DEVICE_CATEGORY_SOUND, dc->categories);
    dc->vmsd = &vmstate_spk;
    device_class_set_legacy_reset(dc, pcspk_reset);
    device_class_set_props(dc, pcspk_properties);
    /* Reason: pit object link */
    dc->user_creatable = false;
}

static const TypeInfo pcspk_info = {
    .name           = TYPE_PC_SPEAKER,
    .parent         = TYPE_ISA_DEVICE,
    .instance_size  = sizeof(PCSpkState),
    .instance_init  = pcspk_initfn,
    .class_init     = pcspk_class_initfn,
};

static void pcspk_register(void)
{
    type_register_static(&pcspk_info);
}
type_init(pcspk_register)
