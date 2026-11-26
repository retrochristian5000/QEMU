/*
 * AT&T PC 6300 / Olivetti M24 keyboard register decode.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Olivetti M24/M21 Theory of Operation, November 1984, pp. 2-44,
 * 2-53 through 2-55: BA2 selects data versus command/status.
 * This is the motherboard bus interface, not the keyboard wire protocol.
 */

#include "qemu/osdep.h"
#include "hw/input/att-kbd302-io.h"

bool att_kbd302_io_read(Intel8741Core *core, unsigned int port,
                       uint8_t *value)
{
    switch (port) {
    case ATT_KBD302_DATA_PORT:
        return intel_8741_host_read(core, value);
    case ATT_KBD302_COMMAND_PORT:
        *value = intel_8741_status(core);
        return true;
    default:
        return false;
    }
}

bool att_kbd302_io_write(Intel8741Core *core, unsigned int port,
                        uint8_t value)
{
    switch (port) {
    case ATT_KBD302_DATA_PORT:
        return intel_8741_host_write(core, value, false);
    case ATT_KBD302_COMMAND_PORT:
        return intel_8741_host_write(core, value, true);
    default:
        return false;
    }
}
