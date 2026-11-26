/*
 * AT&T 302 keyboard-side protocol core.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Reference: Olivetti M24/M21 Theory of Operation, November 1984,
 * chapter 6, pp. 6-1 through 6-4 (keyboard scan code encoding).
 * https://bitsavers.org/pdf/olivetti/m21_m24/Olivetti_M21_M24_Theory_of_Operation_Nov84.pdf
 *
 * Model only raw make/break bytes here. The motherboard controller owns
 * transport timing, command exchange and interrupt delivery. The exact
 * AT&T key layout and typematic behavior need separate verification.
 */

#include "qemu/osdep.h"
#include "hw/input/att-kbd302.h"

void att_kbd302_core_reset(AttKbd302Core *s)
{
    memset(s, 0, sizeof(*s));
}

bool att_kbd302_core_key(AttKbd302Core *s, unsigned int code, bool down)
{
    unsigned int tail;

    if (code == 0 || code > ATT_KBD302_SCAN_MAX) {
        return false;
    }
    if (s->pressed[code] == down) {
        return true;
    }
    if (s->count == ATT_KBD302_QUEUE_SIZE) {
        return false;
    }

    tail = (s->head + s->count) % ATT_KBD302_QUEUE_SIZE;
    s->queue[tail] = code | (down ? 0 : 0x80);
    s->count++;
    s->pressed[code] = down;
    return true;
}

bool att_kbd302_core_read(AttKbd302Core *s, uint8_t *value)
{
    if (!s->count) {
        return false;
    }
    *value = s->queue[s->head];
    s->head = (s->head + 1) % ATT_KBD302_QUEUE_SIZE;
    s->count--;
    return true;
}
