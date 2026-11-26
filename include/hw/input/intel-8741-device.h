/*
 * Intel 8741 device-side peripheral connection.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_INTEL_8741_DEVICE_H
#define HW_INPUT_INTEL_8741_DEVICE_H

#include "hw/core/qdev.h"
#include "hw/input/intel-8741.h"
#include "hw/input/intel-8741-program.h"

#define TYPE_INTEL_8741 "intel-8741"
OBJECT_DECLARE_SIMPLE_TYPE(Intel8741State, INTEL_8741)

/*
 * The owner provides a byte source until it explicitly disconnects.
 * False means no byte is available and leaves the destination unchanged.
 * This is a byte-level connection, not yet a serial-clock or pin model.
 */
typedef bool (*Intel8741KeyboardRead)(void *opaque, uint8_t *value);

struct Intel8741State {
    DeviceState parent_obj;
    Intel8741Core core;
    Intel8741Program program;
    Intel8741KeyboardRead keyboard_read;
    void *keyboard_opaque;
};

void intel_8741_connect_keyboard(Intel8741State *s,
                                 Intel8741KeyboardRead read_byte,
                                 void *opaque);
/*
 * Resolve a realized explicit controller by ID or by unique availability,
 * otherwise create a private child. Returns an owned reference on success.
 */
Intel8741State *intel_8741_attach_keyboard(DeviceState *owner,
                                          const char *controller_id,
                                          Intel8741KeyboardRead read_byte,
                                          void *opaque, Error **errp);
void intel_8741_detach_keyboard(DeviceState *owner, Intel8741State *s,
                               void *opaque);
bool intel_8741_read_keyboard(Intel8741State *s, uint8_t *value);

#endif
