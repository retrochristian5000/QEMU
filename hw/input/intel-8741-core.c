/*
 * Intel 8741 UPI-41 host data bus interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Intel MCS-48 and UPI-41 Assembly Language Manual (1978),
 * order 9800255C, sections 1-12 through 1-13 and 4-2.
 * The original UPI-41 has one shared data bus buffer, not the two
 * independent buffers introduced in the UPI-41A.
 *
 * No instruction execution, board I/O decoding, or interrupt wiring
 * is implied by this handshake model. Undefined upper status bits
 * are returned as zero; invalid transfers are rejected at the API.
 */

#include "qemu/osdep.h"
#include "hw/input/intel-8741.h"

void intel_8741_core_reset(Intel8741Core *s)
{
    s->dbb = 0;
    s->status = 0;
}

uint8_t intel_8741_status(const Intel8741Core *s)
{
    return s->status;
}

void intel_8741_mcu_set_f0(Intel8741Core *s, bool value)
{
    s->status = (s->status & ~INTEL_8741_F0) |
                (value ? INTEL_8741_F0 : 0);
}

void intel_8741_mcu_set_f1(Intel8741Core *s, bool value)
{
    s->status = (s->status & ~INTEL_8741_F1) |
                (value ? INTEL_8741_F1 : 0);
}

bool intel_8741_host_write(Intel8741Core *s, uint8_t value, bool command)
{
    if (s->status & (INTEL_8741_IBF | INTEL_8741_OBF)) {
        return false;
    }
    s->dbb = value;
    intel_8741_mcu_set_f1(s, command);
    s->status |= INTEL_8741_IBF;
    return true;
}

bool intel_8741_host_read(Intel8741Core *s, uint8_t *value)
{
    if (!(s->status & INTEL_8741_OBF)) {
        return false;
    }
    *value = s->dbb;
    s->status &= ~INTEL_8741_OBF;
    return true;
}

bool intel_8741_mcu_read(Intel8741Core *s, uint8_t *value, bool *command)
{
    if (!(s->status & INTEL_8741_IBF) || (s->status & INTEL_8741_OBF)) {
        return false;
    }
    *value = s->dbb;
    *command = !!(s->status & INTEL_8741_F1);
    s->status &= ~INTEL_8741_IBF;
    return true;
}

bool intel_8741_mcu_write(Intel8741Core *s, uint8_t value)
{
    if (s->status & (INTEL_8741_IBF | INTEL_8741_OBF)) {
        return false;
    }
    s->dbb = value;
    s->status |= INTEL_8741_OBF;
    return true;
}
