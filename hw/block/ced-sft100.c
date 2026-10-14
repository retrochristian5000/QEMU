/*
 * RCA SelectaVision SFT100 VideoDisc player: QOM/front-panel wrapper.
 * The physical RCA unit is not a CPU bus peripheral; do not invent an
 * ISA/MMIO/IDE interface.  No guest-facing device until integrated with
 * a documented television/AV model and real CED data path.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/block/ced-sft100.h"
#include "qemu/module.h"
#include "qapi/error.h"
#include "migration/blocker.h"
#include "qemu/timer.h"
#include "qom/object.h"

#define SFT100_TICK_NS INT64_C(10000000) /* 10 ms virtual-time resolution */

struct RcaSft100State {
    DeviceState parent_obj;
    CedSft100Control control;
    QEMUTimer *timer;
    Error *migration_blocker;
    int64_t last_ns;
};

/* The virtual clock stops when VM execution stops. */
static void rca_sft100_sync(RcaSft100State *s)
{
    int64_t now;

    if (!s->timer) {
        return;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (now >= s->last_ns) {
        ced_sft100_advance_ns(&s->control,
                             ((uint64_t)now - (uint64_t)s->last_ns));
    }
    /* A restored or reset clock must never produce unsigned time wrap. */
    s->last_ns = now;
}

static void rca_sft100_reschedule(RcaSft100State *s)
{
    int64_t now;

    if (!s->timer) {
        return;
    }
    timer_del(s->timer);
    if (!ced_sft100_clock_active(&s->control)) {
        return;
    }
    now = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    if (now > INT64_MAX - SFT100_TICK_NS) {
        return;
    }
    timer_mod(s->timer, now + SFT100_TICK_NS);
}

static void rca_sft100_tick(void *opaque)
{
    RcaSft100State *s = opaque;

    rca_sft100_sync(s);
    rca_sft100_reschedule(s);
}

/* All mutation goes through the same sync/transition/timer sequence. */
#define RCA_SFT100_COMMAND(dev, call)       \
    do {                                    \
        bool ok;                            \
        if (!(dev) || !(dev)->timer) {      \
            return false;                   \
        }                                   \
        rca_sft100_sync(dev);               \
        ok = (call);                        \
        rca_sft100_reschedule(dev);         \
        return ok;                          \
    } while (0)

bool rca_sft100_set_lever(RcaSft100State *s, CedSft100Lever lever)
{
    RCA_SFT100_COMMAND(s, ced_sft100_set_lever(&s->control, lever));
}

bool rca_sft100_insert(RcaSft100State *s, const CedMedia *media, uint8_t side)
{
    RCA_SFT100_COMMAND(s, ced_sft100_insert(&s->control, media, side));
}

bool rca_sft100_remove(RcaSft100State *s)
{
    RCA_SFT100_COMMAND(s, ced_sft100_remove(&s->control));
}

bool rca_sft100_pause_toggle(RcaSft100State *s)
{
    RCA_SFT100_COMMAND(s, ced_sft100_pause_toggle(&s->control));
}

bool rca_sft100_search(RcaSft100State *s, bool forward)
{
    RCA_SFT100_COMMAND(s, ced_sft100_search(&s->control, forward));
}

bool rca_sft100_search_release(RcaSft100State *s)
{
    RCA_SFT100_COMMAND(s, ced_sft100_search_release(&s->control));
}

bool rca_sft100_rapid_access(RcaSft100State *s, uint32_t target_field)
{
    RCA_SFT100_COMMAND(s, ced_sft100_rapid_access(&s->control, target_field));
}

bool rca_sft100_select_channel(RcaSft100State *s, uint8_t channel)
{
    RCA_SFT100_COMMAND(s, ced_sft100_select_channel(&s->control, channel));
}

void rca_sft100_get_status(RcaSft100State *s, RcaSft100Status *out)
{
    if (!s || !out) {
        return;
    }
    rca_sft100_sync(s);
    *out = (RcaSft100Status) {
        .lever = s->control.lever,
        .state = s->control.player.state,
        .rf_source = ced_sft100_rf_source(&s->control),
        .field = s->control.player.position_fields,
        .side = s->control.player.side,
        .rf_channel = s->control.player.rf_channel,
        .motor_running = ced_sft100_motor_running(&s->control),
        .video_visible = ced_sft100_video_visible(&s->control),
        .audio_audible = ced_sft100_audio_audible(&s->control),
        .stylus_engaged = s->control.lever == CED_SFT100_PLAY &&
            ced_player_stylus_engaged(&s->control.player),
    };
}

static bool rca_sft100_qom_motor(Object *obj, Error **errp)
{
    RcaSft100Status st;

    (void)errp;
    rca_sft100_get_status(RCA_SFT100(obj), &st);
    return st.motor_running;
}

static bool rca_sft100_qom_video(Object *obj, Error **errp)
{
    RcaSft100Status st;

    (void)errp;
    rca_sft100_get_status(RCA_SFT100(obj), &st);
    return st.video_visible;
}

static bool rca_sft100_qom_audio(Object *obj, Error **errp)
{
    RcaSft100Status st;

    (void)errp;
    rca_sft100_get_status(RCA_SFT100(obj), &st);
    return st.audio_audible;
}

static bool rca_sft100_qom_antenna(Object *obj, Error **errp)
{
    RcaSft100Status st;

    (void)errp;
    rca_sft100_get_status(RCA_SFT100(obj), &st);
    return st.rf_source == CED_SFT100_RF_ANTENNA;
}

static void rca_sft100_instance_init(Object *obj)
{
    RcaSft100State *s = RCA_SFT100(obj);

    ced_sft100_control_init(&s->control);
    /* QOM telemetry is deliberately read-only, unlike the front controls. */
    object_property_add_bool(obj, "motor-running", rca_sft100_qom_motor, NULL);
    object_property_add_bool(obj, "video-visible", rca_sft100_qom_video, NULL);
    object_property_add_bool(obj, "audio-audible", rca_sft100_qom_audio, NULL);
    object_property_add_bool(obj, "antenna-passthrough",
                             rca_sft100_qom_antenna, NULL);
    object_property_add_uint32_ptr(obj, "position-fields",
                                   &s->control.player.position_fields,
                                   OBJ_PROP_FLAG_READ);
    object_property_add_uint8_ptr(obj, "side", &s->control.player.side,
                                  OBJ_PROP_FLAG_READ);
    object_property_add_uint8_ptr(obj, "rf-channel",
                                  &s->control.player.rf_channel,
                                  OBJ_PROP_FLAG_READ);
}

static void rca_sft100_realize(DeviceState *dev, Error **errp)
{
    RcaSft100State *s = RCA_SFT100(dev);

    /* Until there is a VMState schema, never silently drop player state. */
    error_setg(&s->migration_blocker,
               "RCA SFT100 cannot migrate or snapshot without CED VMState");
    if (migrate_add_blocker(&s->migration_blocker, errp) < 0) {
        return;
    }
    s->last_ns = qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL);
    s->timer = timer_new_ns(QEMU_CLOCK_VIRTUAL, rca_sft100_tick, s);
}

static void rca_sft100_unrealize(DeviceState *dev)
{
    RcaSft100State *s = RCA_SFT100(dev);

    if (s->timer) {
        timer_free(s->timer);
        s->timer = NULL;
    }
    migrate_del_blocker(&s->migration_blocker);
}

static void rca_sft100_class_init(ObjectClass *oc, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(oc);

    (void)data;
    dc->desc = "RCA SelectaVision SFT100 CED transport (no RF decoder)";
    dc->realize = rca_sft100_realize;
    dc->unrealize = rca_sft100_unrealize;
    /* External standalone appliance: no virtual machine port/TV attached. */
    dc->user_creatable = false;
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);
}

static const TypeInfo rca_sft100_info = {
    .name = TYPE_RCA_SFT100,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(RcaSft100State),
    .instance_init = rca_sft100_instance_init,
    .class_init = rca_sft100_class_init,
};

static void rca_sft100_register_types(void)
{
    type_register_static(&rca_sft100_info);
}

type_init(rca_sft100_register_types)
