/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_CPU_MCS51_H
#define HW_CPU_MCS51_H

typedef struct MCS51Model {
    const char *name;
    uint16_t rom_size;
    uint16_t ram_size;
    bool timer2;
    bool cmos;
} MCS51Model;

typedef struct MCS51State {
    const MCS51Model *model;
    const uint8_t *rom;
    uint16_t pc;
    uint8_t ram[256];
    uint8_t sfr[128];
    void *opaque;
    uint8_t (*port_read)(void *opaque, unsigned int port);
    uint8_t (*xread)(void *opaque, uint16_t addr);
    void (*xwrite)(void *opaque, uint16_t addr, uint8_t value);
} MCS51State;

const MCS51Model *mcs51_model_find(const char *name);
void mcs51_reset(MCS51State *s);
/* False means an unsupported opcode or an out-of-ROM fetch. */
bool mcs51_step(MCS51State *s);

#endif
