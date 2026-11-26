/*
 * AT&T PC 6300 motherboard keyboard register decode.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_ATT_KBD302_IO_H
#define HW_INPUT_ATT_KBD302_IO_H

#include "hw/input/intel-8741.h"

#define ATT_KBD302_DATA_PORT 0x60
#define ATT_KBD302_COMMAND_PORT 0x64
#define ATT_KBD302_IRQ 1

/* Invalid ports and out-of-handshake transfers leave state unchanged. */
bool att_kbd302_io_read(Intel8741Core *core, unsigned int port,
                       uint8_t *value);
bool att_kbd302_io_write(Intel8741Core *core, unsigned int port,
                        uint8_t value);

#endif
