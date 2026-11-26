/*
 * AT&T 301 keyboard-side protocol core.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_ATT_KBD301_H
#define HW_INPUT_ATT_KBD301_H

/* Related Olivetti M24 Keyboard 1, positions 1 through 83. */
#define ATT_KBD301_SCAN_MAX 0x53
#define ATT_KBD301_QUEUE_SIZE 256

typedef struct AttKbd301Core {
    bool pressed[ATT_KBD301_SCAN_MAX + 1];
    uint8_t queue[ATT_KBD301_QUEUE_SIZE];
    unsigned int head;
    unsigned int count;
} AttKbd301Core;

void att_kbd301_core_reset(AttKbd301Core *s);
/* Return false on invalid code or full queue. Repeated state is a no-op. */
bool att_kbd301_core_key(AttKbd301Core *s, unsigned int code, bool down);
/* Provisional M24 Keyboard 1 physical-key map; zero means no mapping. */
uint8_t att_kbd301_linux_to_scan(unsigned int key);
bool att_kbd301_core_linux_key(AttKbd301Core *s, unsigned int key, bool down);
/* Return false if empty; do not modify the destination in that case. */
bool att_kbd301_core_read(AttKbd301Core *s, uint8_t *value);

#endif
