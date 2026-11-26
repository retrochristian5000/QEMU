/*
 * QEMU 8253/8254 interval timer emulation
 *
 * Copyright (c) 2003-2004 Fabrice Bellard
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
#include "hw/core/irq.h"
#include "qemu/module.h"
#include "qemu/timer.h"
#include "hw/timer/i8254.h"
#include "hw/timer/hpet.h"
#include "hw/timer/i8254_internal.h"
#include "qom/object.h"
#include "trace.h"

//#define DEBUG_PIT

#define RW_STATE_LSB 1
#define RW_STATE_MSB 2
#define RW_STATE_WORD0 3
#define RW_STATE_WORD1 4

typedef struct PITClass PITClass;
typedef struct PITState PITState;
DECLARE_OBJ_CHECKERS(PITState, PITClass, PIT, TYPE_I8254)

struct PITState {
    PITCommonState parent_obj;
    char *model;
    bool is_8253;
    bool board_wired;
};

struct PITClass {
    PITCommonClass parent_class;

    DeviceRealize parent_realize;
    const char *fixed_model;
};

static void pit_irq_timer_update(PITChannelState *s, int64_t current_time);

static int pit_get_count(PITChannelState *s, bool is_8253)
{
    uint64_t d;
    int counter;

    d = muldiv64(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) - s->count_load_time, PIT_FREQ,
                 NANOSECONDS_PER_SECOND);
    switch (pit_effective_mode(s)) {
    case 0:
    case 1:
    case 4:
    case 5:
        counter = (s->count - d) & 0xffff;
        break;
    case 3: {
        unsigned int phase = d % s->count;
        unsigned int high_ticks = (s->count + 1) / 2;

        /*
         * Unlike the 8254, the 8253 reloads the full odd count at
         * both edges. The first decrement is one while OUT is high
         * and three while OUT is low; subsequent decrements are two.
         */
        if (is_8253 && (s->count & 1)) {
            bool high = phase < high_ticks;

            if (!high) {
                phase -= high_ticks;
            }
            if (phase == 0) {
                counter = s->count;
            } else {
                counter = s->count - 2 * phase + (high ? 1 : -1);
            }
            break;
        }

        /*
         * The 8254 loads an even counting element in both half-cycles.
         * For odd divisors, the high half includes one tick at zero.
         */
        if (phase >= high_ticks) {
            phase -= high_ticks;
        }
        counter = (s->count & ~1) - 2 * phase;
        break;
    }
    default:
        counter = s->count - (d % s->count);
        break;
    }
    return counter;
}

/* val must be 0 or 1 */
static void pit_set_channel_gate(PITCommonState *s, PITChannelState *sc,
                                 int val)
{
    switch (pit_effective_mode(sc)) {
    default:
    case 0:
    case 4:
        /* XXX: just disable/enable counting */
        break;
    case 1:
    case 5:
        if (sc->gate < val) {
            /* restart counting on rising edge */
            sc->count_load_time = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            pit_irq_timer_update(sc, sc->count_load_time);
        }
        break;
    case 2:
    case 3:
        if (sc->gate < val) {
            /* restart counting on rising edge */
            sc->count_load_time = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
            pit_irq_timer_update(sc, sc->count_load_time);
        }
        /* XXX: disable/enable counting */
        break;
    }
    sc->gate = val;
}

static inline void pit_load_count(PITChannelState *s, int val)
{
    if (val == 0)
        val = 0x10000;
    s->count_load_time = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    s->count = val;
    pit_irq_timer_update(s, s->count_load_time);
}

/* if already latched, do not latch again */
static void pit_latch_count(PITChannelState *s, bool is_8253)
{
    if (!s->count_latched) {
        s->latched_count = pit_get_count(s, is_8253);
        s->count_latched = s->rw_mode;
    }
}

static void pit_ioport_write(void *opaque, hwaddr addr,
                             uint64_t val, unsigned size)
{
    PITState *ps = PIT(opaque);
    PITCommonState *pit = &ps->parent_obj;
    int channel, access;
    PITChannelState *s;

    trace_pit_ioport_write(addr, val);

    addr &= 3;
    if (addr == 3) {
        channel = val >> 6;
        if (channel == 3) {
            /* Counter select 3 is reserved on the original 8253. */
            if (ps->is_8253) {
                return;
            }
            /* read back command */
            for(channel = 0; channel < 3; channel++) {
                s = &pit->channels[channel];
                if (val & (2 << channel)) {
                    if (!(val & 0x20)) {
                        pit_latch_count(s, ps->is_8253);
                    }
                    if (!(val & 0x10) && !s->status_latched) {
                        /* status latch */
                        /* BCD counting and deferred reloads remain TODO. */
                        s->status =
                            (pit_get_out(s,
                                         qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)) << 7) |
                            ((pit->pending_initial_count & (1U << channel))
                             ? 0x40 : 0) |
                            (s->rw_mode << 4) |
                            (s->mode << 1) |
                            s->bcd;
                        s->status_latched = 1;
                    }
                }
            }
        } else {
            s = &pit->channels[channel];
            access = (val >> 4) & 3;
            if (access == 0) {
                pit_latch_count(s, ps->is_8253);
            } else {
                /* Reprogramming releases any outstanding count latch. */
                s->count_latched = 0;
                /* Preserve the default model's historical status semantics. */
                if (ps->model && !ps->is_8253) {
                    pit->pending_initial_count |= 1U << channel;
                }
                s->rw_mode = access;
                s->read_state = access;
                s->write_state = access;

                s->mode = (val >> 1) & 7;
                s->bcd = val & 1;
                /* XXX: update irq timer ? */
            }
        }
    } else {
        s = &pit->channels[addr];
        switch(s->write_state) {
        default:
        case RW_STATE_LSB:
            pit_load_count(s, val);
            pit->pending_initial_count &= ~(1U << addr);
            break;
        case RW_STATE_MSB:
            pit_load_count(s, val << 8);
            pit->pending_initial_count &= ~(1U << addr);
            break;
        case RW_STATE_WORD0:
            s->write_latch = val;
            s->write_state = RW_STATE_WORD1;
            break;
        case RW_STATE_WORD1:
            pit_load_count(s, s->write_latch | (val << 8));
            /* The existing timing engine loads complete counts immediately. */
            pit->pending_initial_count &= ~(1U << addr);
            s->write_state = RW_STATE_WORD0;
            break;
        }
    }
}

static uint64_t pit_ioport_read(void *opaque, hwaddr addr,
                                unsigned size)
{
    PITState *ps = PIT(opaque);
    PITCommonState *pit = &ps->parent_obj;
    int ret, count;
    PITChannelState *s;

    addr &= 3;

    if (addr == 3) {
        /* Mode/Command register is write only, read is ignored */
        return 0;
    }

    s = &pit->channels[addr];
    if (s->status_latched) {
        s->status_latched = 0;
        ret = s->status;
    } else if (s->count_latched) {
        switch(s->count_latched) {
        default:
        case RW_STATE_LSB:
            ret = s->latched_count & 0xff;
            s->count_latched = 0;
            break;
        case RW_STATE_MSB:
            ret = s->latched_count >> 8;
            s->count_latched = 0;
            break;
        case RW_STATE_WORD0:
            ret = s->latched_count & 0xff;
            s->count_latched = RW_STATE_MSB;
            break;
        }
    } else {
        switch(s->read_state) {
        default:
        case RW_STATE_LSB:
            count = pit_get_count(s, ps->is_8253);
            ret = count & 0xff;
            break;
        case RW_STATE_MSB:
            count = pit_get_count(s, ps->is_8253);
            ret = (count >> 8) & 0xff;
            break;
        case RW_STATE_WORD0:
            count = pit_get_count(s, ps->is_8253);
            ret = count & 0xff;
            s->read_state = RW_STATE_WORD1;
            break;
        case RW_STATE_WORD1:
            count = pit_get_count(s, ps->is_8253);
            ret = (count >> 8) & 0xff;
            s->read_state = RW_STATE_WORD0;
            break;
        }
    }

    trace_pit_ioport_read(addr, ret);

    return ret;
}

static void pit_irq_timer_update(PITChannelState *s, int64_t current_time)
{
    int64_t expire_time;
    int irq_level;

    if (!s->irq_timer || s->irq_disabled) {
        return;
    }
    pit_get_irq_timing(s, current_time, &irq_level, &expire_time);
    qemu_set_irq(s->irq, irq_level);
#ifdef DEBUG_PIT
    printf("irq_level=%d next_delay=%f\n",
           irq_level,
           (double)(expire_time - current_time) / NANOSECONDS_PER_SECOND);
#endif
    s->next_transition_time = expire_time;
    if (expire_time != -1)
        timer_mod(s->irq_timer, expire_time);
    else
        timer_del(s->irq_timer);
}

static void pit_irq_timer(void *opaque)
{
    PITChannelState *s = opaque;

    pit_irq_timer_update(s, s->next_transition_time);
}

static void pit_reset(DeviceState *dev)
{
    PITCommonState *pit = PIT_COMMON(dev);
    PITChannelState *s;

    pit_reset_common(pit);

    s = &pit->channels[0];
    if (!s->irq_disabled) {
        timer_mod(s->irq_timer, s->next_transition_time);
    }
}

/* When HPET is operating in legacy mode, suppress the ignored timer IRQ,
 * reenable it when legacy mode is left again. */
static void pit_irq_control(void *opaque, int n, int enable)
{
    PITCommonState *pit = opaque;
    PITChannelState *s = &pit->channels[0];

    if (enable) {
        s->irq_disabled = 0;
        pit_irq_timer_update(s, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL));
    } else {
        s->irq_disabled = 1;
        timer_del(s->irq_timer);
    }
}

static const MemoryRegionOps pit_ioport_ops = {
    .read = pit_ioport_read,
    .write = pit_ioport_write,
    .impl = {
        .min_access_size = 1,
        .max_access_size = 1,
    },
    .endianness = DEVICE_LITTLE_ENDIAN,
};

static void pit_post_load(PITCommonState *s)
{
    PITChannelState *sc = &s->channels[0];

    if (sc->next_transition_time != -1 && !sc->irq_disabled) {
        timer_mod(sc->irq_timer, sc->next_transition_time);
    } else {
        timer_del(sc->irq_timer);
    }
}

void i8254_pit_set_board_wiring(ISADevice *dev)
{
    PIT(dev)->board_wired = true;
}

static int pit_check_peer(DeviceState *peer, void *opaque)
{
    DeviceState *dev = opaque;

    if (peer != dev && qdev_is_realized(peer) &&
        qdev_get_parent_bus(peer) == qdev_get_parent_bus(dev) &&
        object_dynamic_cast(OBJECT(peer), TYPE_PIT_COMMON)) {
        return -1;
    }
    return 0;
}

static void pit_realizefn(DeviceState *dev, Error **errp)
{
    PITState *ps = PIT(dev);
    PITCommonState *pit = &ps->parent_obj;
    PITClass *pc = PIT_GET_CLASS(dev);
    PITChannelState *s;
    ISADevice *isadev = ISA_DEVICE(dev);
    ISABus *bus = isa_bus_from_device(isadev);

    if (pc->fixed_model) {
        if (ps->model && strcmp(ps->model, pc->fixed_model)) {
            error_setg(errp, "%s requires model=%s",
                       object_get_typename(OBJECT(dev)), pc->fixed_model);
            return;
        }
        if (!ps->model) {
            ps->model = g_strdup(pc->fixed_model);
        }
    }

    if (!ps->board_wired) {
        if (qbus_walk_children(BUS(bus), pit_check_peer,
                               NULL, NULL, NULL, dev)) {
            error_setg(errp, "%s: ISA bus already has a system PIT; "
                       "disable the motherboard PIT before adding another",
                       object_get_typename(OBJECT(dev)));
            return;
        }
        if (hpet_find()) {
            error_setg(errp, "%s: explicit ISA PIT requires HPET disabled; "
                       "the motherboard normally wires their interrupts",
                       object_get_typename(OBJECT(dev)));
            return;
        }
        if (pit->iobase == UINT32_MAX) {
            pit->iobase = 0x40;
        }
        if (!bus->irqs_in || !bus->irqs_in[0]) {
            error_setg(errp, "%s: ISA IRQ0 is not connected",
                       object_get_typename(OBJECT(dev)));
            return;
        }
        if (!isa_ioport_range_available(isadev, pit->iobase, 4, errp)) {
            return;
        }
    }

    if (ps->model && strcmp(ps->model, "i8253") == 0) {
        ps->is_8253 = true;
    } else if (ps->model && strcmp(ps->model, "i8254") != 0) {
        error_setg(errp, "Unsupported ISA PIT model '%s'; use i8253 or i8254",
                   ps->model);
        return;
    }

    s = &pit->channels[0];
    /* the timer 0 is connected to an IRQ */
    s->irq_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, pit_irq_timer, s);
    qdev_init_gpio_out(dev, &s->irq, 1);

    memory_region_init_io(&pit->ioports, OBJECT(pit), &pit_ioport_ops,
                          pit, "pit", 4);

    qdev_init_gpio_in(dev, pit_irq_control, 1);

    pc->parent_realize(dev, errp);
    if (!ps->board_wired) {
        isa_connect_gpio_out(isadev, 0, 0);
    }
}

static const Property pit_properties[] = {
    DEFINE_PROP_STRING("model", PITState, model),
};

static void pit_class_initfn(ObjectClass *klass, const void *data)
{
    PITClass *pc = PIT_CLASS(klass);
    PITCommonClass *k = PIT_COMMON_CLASS(klass);
    DeviceClass *dc = DEVICE_CLASS(klass);

    device_class_set_parent_realize(dc, pit_realizefn, &pc->parent_realize);
    dc->desc = "Generic ISA programmable interval timer (8253/8254 compatible)";
    dc->user_creatable = true;
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
    k->set_channel_gate = pit_set_channel_gate;
    k->get_channel_info = pit_get_channel_info_common;
    k->post_load = pit_post_load;
    device_class_set_legacy_reset(dc, pit_reset);
    device_class_set_props(dc, pit_properties);
}

static const TypeInfo pit_info = {
    .name          = TYPE_I8254,
    .parent        = TYPE_PIT_COMMON,
    .instance_size = sizeof(PITState),
    .class_init    = pit_class_initfn,
    .class_size    = sizeof(PITClass),
};

static void pit_model_class_init(ObjectClass *klass, const void *data)
{
    PITClass *pc = PIT_CLASS(klass);
    DeviceClass *dc = DEVICE_CLASS(klass);

    pc->fixed_model = data;
    dc->desc = !strcmp(pc->fixed_model, "i8253") ?
        "Intel 8253 programmable interval timer" :
        "Intel 8254 programmable interval timer";
}

static const TypeInfo pit_8253_info = {
    .name = TYPE_INTEL_8253,
    .parent = TYPE_I8254,
    .class_init = pit_model_class_init,
    .class_data = "i8253",
};

static const TypeInfo pit_8254_info = {
    .name = TYPE_INTEL_8254,
    .parent = TYPE_I8254,
    .class_init = pit_model_class_init,
    .class_data = "i8254",
};

static void pit_register_types(void)
{
    type_register_static(&pit_info);
    type_register_static(&pit_8253_info);
    type_register_static(&pit_8254_info);
}

type_init(pit_register_types)
