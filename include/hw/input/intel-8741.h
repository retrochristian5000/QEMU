/*
 * Intel 8741 UPI-41 host interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_INTEL_8741_H
#define HW_INPUT_INTEL_8741_H

#define INTEL_8741_OBF 0x01
#define INTEL_8741_IBF 0x02
#define INTEL_8741_F0  0x04
#define INTEL_8741_F1  0x08

typedef struct Intel8741Core {
    uint8_t dbb;
    uint8_t status;
} Intel8741Core;

void intel_8741_core_reset(Intel8741Core *s);
uint8_t intel_8741_status(const Intel8741Core *s);
/*
 * Shared DBB: only one transfer may be outstanding. The API rejects
 * out-of-handshake accesses rather than specifying undocumented results.
 * A rejected operation leaves the state and any output arguments unchanged.
 */
bool intel_8741_host_write(Intel8741Core *s, uint8_t value, bool command);
bool intel_8741_host_read(Intel8741Core *s, uint8_t *value);
bool intel_8741_mcu_read(Intel8741Core *s, uint8_t *value, bool *command);
bool intel_8741_mcu_write(Intel8741Core *s, uint8_t value);
void intel_8741_mcu_set_f0(Intel8741Core *s, bool value);
void intel_8741_mcu_set_f1(Intel8741Core *s, bool value);

#endif
