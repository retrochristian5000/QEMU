/*
 * Shared original Intel UPI-41 peripheral controller implementation.
 * Intel MCS-48 and UPI-41 Assembly Language Reference Manual, 9800255D,
 * December 1978, sections 1 and 4.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/input/intel-8741-device.h"
#include "qapi/error.h"
#include "qemu/module.h"

void intel_8741_connect_keyboard(Intel8741State *s,
                                 Intel8741KeyboardRead read_byte,
                                 void *opaque)
{
    assert(!s->keyboard_read);
    assert(read_byte);
    s->keyboard_read = read_byte;
    s->keyboard_opaque = opaque;
}

typedef struct Intel8741Search {
    Intel8741State *available;
    unsigned int total;
    unsigned int free;
} Intel8741Search;

static int intel_8741_find_controller(Object *obj, void *opaque)
{
    Intel8741Search *search = opaque;
    Intel8741State *s =
        (Intel8741State *)object_dynamic_cast(obj, TYPE_INTEL_UPI41);

    if (s && DEVICE(s)->realized) {
        search->total++;
        if (!s->keyboard_read) {
            search->available = s;
            search->free++;
        }
    }
    return 0;
}

Intel8741State *intel_8741_attach_keyboard(DeviceState *owner,
                                          const char *controller_id,
                                          Intel8741KeyboardRead read_byte,
                                          void *opaque, Error **errp)
{
    Intel8741State *s;
    Intel8741Search search = { 0 };
    Object *obj;

    if (controller_id) {
        obj = object_resolve_path_component(
            machine_get_container("peripheral"), controller_id);
        s = obj ? (Intel8741State *)object_dynamic_cast(obj, TYPE_INTEL_UPI41)
                : NULL;
        if (!s || !DEVICE(s)->realized) {
            error_setg(errp, "Intel UPI-41 controller '%s' is not available",
                       controller_id);
            return NULL;
        }
        if (s->keyboard_read) {
            error_setg(errp, "Intel UPI-41 controller '%s' already has a keyboard",
                       controller_id);
            return NULL;
        }
    } else {
        object_child_foreach(machine_get_container("peripheral"),
                             intel_8741_find_controller, &search);
        object_child_foreach(machine_get_container("peripheral-anon"),
                             intel_8741_find_controller, &search);
        if (search.free > 1) {
            error_setg(errp, "Multiple Intel UPI-41 controllers are available; "
                       "select one using controller-id");
            return NULL;
        }
        if (search.total && !search.free) {
            error_setg(errp, "All explicit Intel UPI-41 controllers already "
                       "have keyboards");
            return NULL;
        }
        s = search.available;
    }

    if (s) {
        object_ref(OBJECT(s));
        intel_8741_connect_keyboard(s, read_byte, opaque);
        return s;
    }

    /* Keep the existing QOM child path for an implicit controller. */
    s = INTEL_8741(qdev_new(TYPE_INTEL_8741));
    object_property_add_child(OBJECT(owner), "controller", OBJECT(s));
    intel_8741_connect_keyboard(s, read_byte, opaque);
    if (!qdev_realize(DEVICE(s), NULL, errp)) {
        s->keyboard_read = NULL;
        s->keyboard_opaque = NULL;
        object_unparent(OBJECT(s));
        object_unref(OBJECT(s));
        return NULL;
    }
    return s;
}

void intel_8741_detach_keyboard(DeviceState *owner, Intel8741State *s,
                               void *opaque)
{
    if (!s) {
        return;
    }

    if (s->keyboard_opaque == opaque) {
        s->keyboard_read = NULL;
        s->keyboard_opaque = NULL;
    }
    if (object_resolve_path_component(OBJECT(owner), "controller") ==
        OBJECT(s)) {
        qdev_unrealize(DEVICE(s));
        object_unparent(OBJECT(s));
    }
    object_unref(OBJECT(s));
}

bool intel_8741_read_keyboard(Intel8741State *s, uint8_t *value)
{
    return DEVICE(s)->realized && s->keyboard_read &&
           s->keyboard_read(s->keyboard_opaque, value);
}

static bool intel_8741_keyboard_attached(Object *obj, Error **errp)
{
    return INTEL_UPI41(obj)->keyboard_read != NULL;
}

static void intel_8741_reset(DeviceState *dev)
{
    Intel8741State *s = INTEL_UPI41(dev);

    intel_8741_core_reset(&s->core);
    intel_8741_program_reset(&s->program);
}

static void intel_8741_realize(DeviceState *dev, Error **errp)
{
    /* An explicitly declared controller may acquire its keyboard later. */
    intel_8741_reset(dev);
}

static void intel_upi41_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    object_class_property_add_bool(klass, "keyboard-attached",
                                   intel_8741_keyboard_attached, NULL);
    dc->realize = intel_8741_realize;
    device_class_set_legacy_reset(dc, intel_8741_reset);
    dc->hotpluggable = false;
    set_bit(DEVICE_CATEGORY_BRIDGE, dc->categories);
}

static const TypeInfo intel_upi41_info = {
    .name = TYPE_INTEL_UPI41,
    .parent = TYPE_DEVICE,
    .instance_size = sizeof(Intel8741State),
    .abstract = true,
    .class_init = intel_upi41_class_init,
};

static void intel_upi41_register_types(void)
{
    type_register_static(&intel_upi41_info);
    type_register_static(&intel_8041_info);
    type_register_static(&intel_8741_info);
}

type_init(intel_upi41_register_types)
