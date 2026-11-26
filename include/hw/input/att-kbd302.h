/*
 * AT&T 302 keyboard-side protocol core.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_ATT_KBD302_H
#define HW_INPUT_ATT_KBD302_H

/* Upper bound from the related Olivetti extended keyboard scan table.
 * This is a raw code domain, not a verified Model 302 host-key map.
 */
#define ATT_KBD302_SCAN_MAX 0x67
#define ATT_KBD302_QUEUE_SIZE 256

typedef struct AttKbd302Core {
    bool pressed[ATT_KBD302_SCAN_MAX + 1];
    uint8_t queue[ATT_KBD302_QUEUE_SIZE];
    unsigned int head;
    unsigned int count;
} AttKbd302Core;

void att_kbd302_core_reset(AttKbd302Core *s);
/* Return false on invalid code or full queue. Repeated state is a no-op. */
bool att_kbd302_core_key(AttKbd302Core *s, unsigned int code, bool down);
/* Provisional M24 deluxe physical-key map; zero means no mapping. */
uint8_t att_kbd302_linux_to_scan(unsigned int key);
bool att_kbd302_core_linux_key(AttKbd302Core *s, unsigned int key, bool down);
/* Return false if empty; do not modify the destination in that case. */
bool att_kbd302_core_read(AttKbd302Core *s, uint8_t *value);

#endif
