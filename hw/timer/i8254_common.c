/*
 * QEMU 8253/8254 - common bits of emulated and KVM kernel model
 *
 * Copyright (c) 2003-2004 Fabrice Bellard
 * Copyright (c) 2012      Jan Kiszka, Siemens AG
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
#include "qemu/module.h"
#include "qemu/timer.h"
#include "hw/timer/i8254.h"
#include "hw/timer/i8254_internal.h"
#include "migration/vmstate.h"

/* val must be 0 or 1 */
void pit_set_gate(PITCommonState *pit, int channel, int val)
{
    PITChannelState *s = &pit->channels[channel];
    PITCommonClass *c = PIT_COMMON_GET_CLASS(pit);

    c->set_channel_gate(pit, s, val);
}

/*
 * Count reads, output state and IRQ deadlines share the same load epoch.
 * Clamp an epoch in the future (possible during clock synchronization)
 * instead of converting a negative interval into unsigned elapsed ticks.
 */
static uint64_t pit_elapsed_ticks(PITChannelState *s, int64_t current_time)
{
    uint64_t elapsed = current_time < s->count_load_time ? 0 :
        (uint64_t)current_time - (uint64_t)s->count_load_time;

    return muldiv64(elapsed, PIT_FREQ, NANOSECONDS_PER_SECOND);
}

/* A programmed zero represents a full 16-bit binary count. */
static unsigned pit_reload_count(const PITChannelState *s)
{
    return s->count > 0 && s->count <= 0x10000 ? (unsigned)s->count : 0x10000U;
}

typedef struct PITTiming {
    int out;
    /* Zero means no further output transition. */
    unsigned ticks_to_edge;
} PITTiming;

/*
 * Calculate phase once for both OUT and the next edge. The timer remains
 * anchored to the count-load epoch, never to the host callback time.
 */
static PITTiming pit_timing_elapsed(PITChannelState *s, uint64_t ticks)
{
    unsigned count = pit_reload_count(s);
    unsigned phase, high_ticks;
    PITTiming timing = { .out = 1 };

    switch (pit_effective_mode(s)) {
    default:
    case 0:
    case 1:
        timing.out = ticks >= count;
        if (!timing.out) {
            timing.ticks_to_edge = count - ticks;
        }
        break;
    case 2:
        if (!s->gate || count == 1) {
            break;
        }
        phase = ticks % count;
        timing.out = phase != count - 1;
        timing.ticks_to_edge = timing.out ? count - 1 - phase : 1;
        break;
    case 3:
        if (!s->gate || count == 1) {
            /* No low half-cycle: do not schedule an unchanged OUT. */
            break;
        }
        phase = ticks % count;
        high_ticks = (count + 1) / 2;
        timing.out = phase < high_ticks;
        timing.ticks_to_edge = (timing.out ? high_ticks : count) - phase;
        break;
    case 4:
    case 5:
        timing.out = ticks != count;
        if (ticks < count) {
            timing.ticks_to_edge = count - ticks;
        } else if (ticks == count) {
            timing.ticks_to_edge = 1;
        }
        break;
    }
    return timing;
}

int pit_get_count_at(PITChannelState *s, int64_t current_time, bool is_8253)
{
    uint64_t ticks = pit_elapsed_ticks(s, current_time);
    unsigned count = pit_reload_count(s);
    unsigned phase, high_ticks;

    switch (pit_effective_mode(s)) {
    case 0:
    case 1:
    case 4:
    case 5:
        return (count - ticks) & 0xffff;
    case 3:
        phase = ticks % count;
        high_ticks = (count + 1) / 2;
        /*
         * The 8253 reloads the odd count and makes its first decrement
         * one or three. The 8254 loads an even counting element instead.
         */
        if (is_8253 && (count & 1)) {
            bool high = phase < high_ticks;

            if (!high) {
                phase -= high_ticks;
            }
            return phase ? count - 2 * phase + (high ? 1 : -1) : count;
        }
        if (phase >= high_ticks) {
            phase -= high_ticks;
        }
        return (count & ~1U) - 2 * phase;
    default:
        return count - ticks % count;
    }
}

int pit_get_out(PITChannelState *s, int64_t current_time)
{
    return pit_timing_elapsed(s, pit_elapsed_ticks(s, current_time)).out;
}

static int64_t pit_transition_time(PITChannelState *s, int64_t current_time,
                                   uint64_t elapsed, PITTiming timing)
{
    if (!timing.ticks_to_edge) {
        return -1;
    }

    /* Round up to the first nanosecond at or after the hardware edge. */
    uint64_t next_time = (uint64_t)s->count_load_time +
        muldiv64_round_up(elapsed + timing.ticks_to_edge,
                          NANOSECONDS_PER_SECOND, PIT_FREQ);

    if (next_time > INT64_MAX || current_time == INT64_MAX) {
        return -1;
    }
    if ((int64_t)next_time <= current_time) {
        return current_time + 1;
    }
    return next_time;
}

int64_t pit_get_next_transition_time(PITChannelState *s, int64_t current_time)
{
    uint64_t elapsed = pit_elapsed_ticks(s, current_time);
    PITTiming timing = pit_timing_elapsed(s, elapsed);

    return pit_transition_time(s, current_time, elapsed, timing);
}

void pit_get_irq_timing(PITChannelState *s, int64_t current_time,
                        int *out, int64_t *next_transition)
{
    uint64_t elapsed = pit_elapsed_ticks(s, current_time);
    PITTiming timing = pit_timing_elapsed(s, elapsed);

    *out = timing.out;
    *next_transition = pit_transition_time(s, current_time, elapsed, timing);
}

void pit_get_channel_info_common(PITCommonState *s, PITChannelState *sc,
                                 PITChannelInfo *info)
{
    info->gate = sc->gate;
    info->mode = pit_effective_mode(sc);
    info->initial_count = sc->count;
    info->out = pit_get_out(sc, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
}

void pit_get_channel_info(PITCommonState *pit, int channel, PITChannelInfo *info)
{
    PITChannelState *s = &pit->channels[channel];
    PITCommonClass *c = PIT_COMMON_GET_CLASS(pit);

    c->get_channel_info(pit, s, info);
}

void pit_reset_common(PITCommonState *pit)
{
    PITChannelState *s;
    int i;

    pit->pending_initial_count = 0;
    for (i = 0; i < 3; i++) {
        s = &pit->channels[i];
        s->latched_count = 0;
        s->count_latched = 0;
        s->status_latched = 0;
        s->status = 0;
        s->read_state = 3;  /* LSB followed by MSB */
        s->write_state = 3;
        s->write_latch = 0;
        s->rw_mode = 3;
        s->mode = 3;
        s->bcd = 0;
        s->gate = (i != 2);
        s->next_transition_time = -1;
        s->count_load_time = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
        s->count = 0x10000;
        if (i == 0 && !s->irq_disabled) {
            s->next_transition_time =
                pit_get_next_transition_time(s, s->count_load_time);
        }
    }
}

static void pit_common_realize(DeviceState *dev, Error **errp)
{
    ISADevice *isadev = ISA_DEVICE(dev);
    PITCommonState *pit = PIT_COMMON(dev);

    isa_register_ioport(isadev, &pit->ioports, pit->iobase);

    qdev_set_legacy_instance_id(dev, pit->iobase, 2);
}

static const VMStateDescription vmstate_pit_channel = {
    .name = "pit channel",
    .version_id = 2,
    .minimum_version_id = 2,
    .fields = (const VMStateField[]) {
        VMSTATE_INT32(count, PITChannelState),
        VMSTATE_UINT16(latched_count, PITChannelState),
        VMSTATE_UINT8(count_latched, PITChannelState),
        VMSTATE_UINT8(status_latched, PITChannelState),
        VMSTATE_UINT8(status, PITChannelState),
        VMSTATE_UINT8(read_state, PITChannelState),
        VMSTATE_UINT8(write_state, PITChannelState),
        VMSTATE_UINT8(write_latch, PITChannelState),
        VMSTATE_UINT8(rw_mode, PITChannelState),
        VMSTATE_UINT8(mode, PITChannelState),
        VMSTATE_UINT8(bcd, PITChannelState),
        VMSTATE_UINT8(gate, PITChannelState),
        VMSTATE_INT64(count_load_time, PITChannelState),
        VMSTATE_INT64(next_transition_time, PITChannelState),
        VMSTATE_END_OF_LIST()
    }
};

static int pit_dispatch_pre_save(void *opaque)
{
    PITCommonState *s = opaque;
    PITCommonClass *c = PIT_COMMON_GET_CLASS(s);

    if (c->pre_save) {
        c->pre_save(s);
    }

    return 0;
}

static int pit_dispatch_post_load(void *opaque, int version_id)
{
    PITCommonState *s = opaque;
    PITCommonClass *c = PIT_COMMON_GET_CLASS(s);

    if (c->post_load) {
        c->post_load(s);
    }
    return 0;
}

static bool pit_pending_count_needed(void *opaque)
{
    PITCommonState *s = opaque;

    return s->pending_initial_count != 0;
}

static int pit_pending_count_pre_load(void *opaque)
{
    PITCommonState *s = opaque;

    s->pending_initial_count = 0;
    return 0;
}

static int pit_pending_count_post_load(void *opaque, int version_id)
{
    PITCommonState *s = opaque;

    return (s->pending_initial_count & ~7U) ? -EINVAL : 0;
}

static const VMStateDescription vmstate_pit_pending_count = {
    .name = "i8254/pending-initial-count",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = pit_pending_count_needed,
    .post_load = pit_pending_count_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(pending_initial_count, PITCommonState),
        VMSTATE_END_OF_LIST()
    }
};

static const VMStateDescription vmstate_pit_common = {
    .name = "i8254",
    .version_id = 3,
    .minimum_version_id = 2,
    .pre_save = pit_dispatch_pre_save,
    .pre_load = pit_pending_count_pre_load,
    .post_load = pit_dispatch_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT32_V(channels[0].irq_disabled, PITCommonState, 3),
        VMSTATE_STRUCT_ARRAY(channels, PITCommonState, 3, 2,
                             vmstate_pit_channel, PITChannelState),
        VMSTATE_INT64(channels[0].next_transition_time,
                      PITCommonState), /* formerly irq_timer */
        VMSTATE_END_OF_LIST()
    },
    .subsections = (const VMStateDescription * const []) {
        &vmstate_pit_pending_count,
        NULL
    }
};

static const Property pit_common_properties[] = {
    DEFINE_PROP_UINT32("iobase", PITCommonState, iobase,  -1),
};

static void pit_common_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = pit_common_realize;
    dc->vmsd = &vmstate_pit_common;
    /*
     * Reason: unlike ordinary ISA devices, the PIT may need to be
     * wired to the HPET, and because of that, some wiring is always
     * done by board code.
     */
    dc->user_creatable = false;
    device_class_set_props(dc, pit_common_properties);
}

static const TypeInfo pit_common_type = {
    .name          = TYPE_PIT_COMMON,
    .parent        = TYPE_ISA_DEVICE,
    .instance_size = sizeof(PITCommonState),
    .class_size    = sizeof(PITCommonClass),
    .class_init    = pit_common_class_init,
    .abstract      = true,
};

static void register_devices(void)
{
    type_register_static(&pit_common_type);
}

type_init(register_devices);
