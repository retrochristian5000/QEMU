/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Embedded MCS-51 instruction interpreter. Intel MCS-51 User's Manual. */
#include "qemu/osdep.h"
#include "hw/cpu/mcs51.h"

#define SFR(s, a) ((s)->sfr[(a) - 0x80])
#define ACC SFR(s, 0xe0)
#define PSW SFR(s, 0xd0)
#define B SFR(s, 0xf0)
#define SP SFR(s, 0x81)
#define CY 0x80
#define AC 0x40
#define OV 0x04

static const MCS51Model models[] = {
    { "intel-8052", 8192, 256, true, false },
    { "intel-80c52", 8192, 256, true, true },
};

const MCS51Model *mcs51_model_find(const char *name)
{
    for (size_t i = 0; i < ARRAY_SIZE(models); i++) {
        if (!strcmp(name, models[i].name)) {
            return &models[i];
        }
    }
    return NULL;
}

void mcs51_reset(MCS51State *s)
{
    s->pc = 0;
    memset(s->ram, 0, sizeof(s->ram));
    memset(s->sfr, 0, sizeof(s->sfr));
    SP = 7;
    for (unsigned int i = 0; i < 4; i++) {
        SFR(s, 0x80 + i * 0x10) = 0xff;
    }
}

static uint8_t direct_read(MCS51State *s, uint8_t addr, bool rmw)
{
    if (addr < 0x80) {
        return s->ram[addr];
    }
    if (!rmw && s->port_read && addr <= 0xb0 && !(addr & 15)) {
        return SFR(s, addr) & s->port_read(s->opaque, (addr - 0x80) >> 4);
    }
    return SFR(s, addr);
}

static void direct_write(MCS51State *s, uint8_t addr, uint8_t value)
{
    if (addr < 0x80) {
        s->ram[addr] = value;
    } else {
        SFR(s, addr) = value;
    }
}

static uint8_t *reg(MCS51State *s, unsigned int n)
{
    return &s->ram[(PSW & 0x18) + n];
}

static uint8_t *indirect(MCS51State *s, unsigned int n)
{
    return &s->ram[*reg(s, n)];
}

static uint16_t dptr(MCS51State *s)
{
    return (SFR(s, 0x83) << 8) | SFR(s, 0x82);
}

static void set_dptr(MCS51State *s, uint16_t val)
{
    SFR(s, 0x82) = val;
    SFR(s, 0x83) = val >> 8;
}

static uint8_t bit_addr(uint8_t bit)
{
    return bit < 0x80 ? 0x20 + (bit >> 3) : bit & 0xf8;
}

static bool bit_read(MCS51State *s, uint8_t bit, bool rmw)
{
    return (direct_read(s, bit_addr(bit), rmw) >> (bit & 7)) & 1;
}

static void bit_write(MCS51State *s, uint8_t bit, bool value)
{
    uint8_t addr = bit_addr(bit);
    uint8_t mask = 1U << (bit & 7);
    uint8_t old = direct_read(s, addr, true);

    direct_write(s, addr, (old & ~mask) | (value ? mask : 0));
}

static void carry(MCS51State *s, bool value)
{
    PSW = (PSW & ~CY) | (value ? CY : 0);
}

static void arithmetic(MCS51State *s, uint8_t val, bool sub, bool with_carry)
{
    unsigned int a = ACC;
    unsigned int c = with_carry && (PSW & CY);
    unsigned int result = sub ? a - val - c : a + val + c;
    bool cy = sub ? a < val + c : result > 255;
    bool ac = sub ? (a & 15) < (val & 15) + c :
                    (a & 15) + (val & 15) + c > 15;
    bool ov = sub ? ((a ^ val) & (a ^ result) & 0x80) :
                    (~(a ^ val) & (a ^ result) & 0x80);

    ACC = result;
    PSW = (PSW & ~(CY | AC | OV)) | (cy ? CY : 0) |
          (ac ? AC : 0) | (ov ? OV : 0);
}

static void push(MCS51State *s, uint8_t value)
{
    SP++;
    s->ram[SP] = value;
}

static uint8_t pop(MCS51State *s)
{
    uint8_t value = s->ram[SP];
    SP--;
    return value;
}

static void call(MCS51State *s, uint16_t addr)
{
    push(s, s->pc);
    push(s, s->pc >> 8);
    s->pc = addr;
}

static void branch(MCS51State *s, uint8_t rel)
{
    s->pc += (int8_t)rel;
}

/* Operand encoding for accumulator ALU and MOV A,source instructions. */
static uint8_t operand(MCS51State *s, uint8_t op, uint8_t arg)
{
    unsigned int n = op & 15;

    if (n == 4) {
        return arg;
    }
    if (n == 5) {
        return direct_read(s, arg, false);
    }
    if (n < 8) {
        return *indirect(s, n & 1);
    }
    return *reg(s, n & 7);
}

static unsigned int instruction_size(uint8_t op)
{
    unsigned int lo = op & 15;
    unsigned int hi = op >> 4;

    if ((op & 0x1f) == 1 || (op & 0x1f) == 0x11) {
        return 2;
    }
    if ((hi == 0xb && lo >= 4) || op == 0x02 || op == 0x12 || op == 0x10 ||
        op == 0x20 || op == 0x30 || op == 0x43 || op == 0x53 ||
        op == 0x63 || op == 0x75 || op == 0x85 || op == 0x90 ||
        op == 0xd5) {
        return 3;
    }
    if ((lo == 5 && hi != 0x8 && hi != 0xb && hi != 0xa) ||
        (lo == 4 && hi >= 2 && hi <= 9 && hi != 8) ||
        (hi == 7 && lo >= 6) || (hi == 8 && lo >= 6) ||
        (hi == 0xa && lo >= 6) || (hi == 0xd && lo >= 8) ||
        op == 0x40 || op == 0x50 || op == 0x60 || op == 0x70 ||
        op == 0x80 || op == 0x42 || op == 0x52 || op == 0x62 ||
        op == 0x72 || op == 0x82 || op == 0x92 || op == 0xa0 ||
        op == 0xa2 || op == 0xb0 || op == 0xb2 || op == 0xc0 ||
        op == 0xc2 || op == 0xd0 || op == 0xd2) {
        return 2;
    }
    return 1;
}

bool mcs51_step(MCS51State *s)
{
    uint8_t op, x = 0, y = 0, v, old;
    unsigned int size, hi, lo, result;
    uint16_t addr;
    uint8_t *r;

    if (s->pc >= s->model->rom_size) {
        return false;
    }
    op = s->rom[s->pc];
    size = instruction_size(op);
    if (size > (unsigned int)(s->model->rom_size - s->pc) || op == 0xa5 ||
        op == 0x32) {
        /* RETI requires an interrupt controller, not just a stack pop. */
        return false;
    }
    if (size > 1) {
        x = s->rom[s->pc + 1];
    }
    if (size > 2) {
        y = s->rom[s->pc + 2];
    }
    s->pc += size;
    hi = op >> 4;
    lo = op & 15;

    if ((op & 0x1f) == 1 || (op & 0x1f) == 0x11) {
        addr = (s->pc & 0xf800) | ((op & 0xe0) << 3) | x;
        if (op & 0x10) {
            call(s, addr);
        } else {
            s->pc = addr;
        }
        goto done;
    }
    if (lo >= 4 && ((hi >= 2 && hi <= 6) || hi == 9 || hi == 0xe)
        && (hi != 0xe || lo >= 5)) {
        v = operand(s, op, x);
        switch (hi) {
        case 2: arithmetic(s, v, false, false); break;
        case 3: arithmetic(s, v, false, true); break;
        case 4: ACC |= v; break;
        case 5: ACC &= v; break;
        case 6: ACC ^= v; break;
        case 9: arithmetic(s, v, true, true); break;
        case 0xe: ACC = v; break;
        }
        goto done;
    }

    if (lo >= 6) {
        r = lo < 8 ? indirect(s, lo & 1) : reg(s, lo & 7);
        switch (hi) {
        case 0: ++*r; goto done;
        case 1: --*r; goto done;
        case 7: *r = x; goto done;
        case 8: direct_write(s, x, *r); goto done;
        case 0xa: *r = direct_read(s, x, false); goto done;
        case 0xb:
            v = *r;
            carry(s, v < x);
            if (v != x) {
                branch(s, y);
            }
            goto done;
        case 0xc: v = *r; *r = ACC; ACC = v; goto done;
        case 0xd:
            if (lo >= 8) {
                if (--*r) {
                    branch(s, x);
                }
            } else {
                v = *r;
                *r = (v & 0xf0) | (ACC & 15);
                ACC = (ACC & 0xf0) | (v & 15);
            }
            goto done;
        case 0xf: *r = ACC; goto done;
        }
    }

    switch (op) {
    case 0x00: break;
    case 0x02: s->pc = (x << 8) | y; break;
    case 0x03: ACC = (ACC >> 1) | (ACC << 7); break;
    case 0x04: ++ACC; break;
    case 0x05: direct_write(s, x, direct_read(s, x, true) + 1); break;
    case 0x10:
        if (bit_read(s, x, true)) {
            bit_write(s, x, false);
            branch(s, y);
        }
        break;
    case 0x12: call(s, (x << 8) | y); break;
    case 0x13: old = ACC; ACC = (ACC >> 1) | (PSW & CY);
               carry(s, old & 1); break;
    case 0x14: --ACC; break;
    case 0x15: direct_write(s, x, direct_read(s, x, true) - 1); break;
    case 0x20: if (bit_read(s, x, false)) { branch(s, y); } break;
    case 0x22: addr = (uint16_t)pop(s) << 8;
               s->pc = addr | pop(s); break;
    case 0x23: ACC = (ACC << 1) | (ACC >> 7); break;
    case 0x30: if (!bit_read(s, x, false)) { branch(s, y); } break;
    case 0x33: old = ACC; ACC = (ACC << 1) | !!(PSW & CY);
               carry(s, old & 0x80); break;
    case 0x40: if (PSW & CY) { branch(s, x); } break;
    case 0x50: if (!(PSW & CY)) { branch(s, x); } break;
    case 0x60: if (!ACC) { branch(s, x); } break;
    case 0x70: if (ACC) { branch(s, x); } break;
    case 0x42: case 0x43: case 0x52: case 0x53: case 0x62: case 0x63:
        v = direct_read(s, x, true);
        old = op & 1 ? y : ACC;
        direct_write(s, x, hi == 4 ? v | old : hi == 5 ? v & old : v ^ old);
        break;
    case 0x72: case 0x82: case 0xa0: case 0xb0:
        v = bit_read(s, x, false);
        if (op == 0xa0 || op == 0xb0) {
            v = !v;
        }
        carry(s, op == 0x72 || op == 0xa0 ? (PSW & CY) || v :
                                           (PSW & CY) && v);
        break;
    case 0x73: s->pc = dptr(s) + ACC; break;
    case 0x74: ACC = x; break;
    case 0x75: direct_write(s, x, y); break;
    case 0x80: branch(s, x); break;
    case 0x83: case 0x93:
        addr = (op == 0x83 ? s->pc : dptr(s)) + ACC;
        if (addr >= s->model->rom_size) {
            return false;
        }
        ACC = s->rom[addr];
        break;
    case 0x84:
        PSW &= ~(CY | OV);
        if (!B) {
            PSW |= OV;
        } else {
            v = ACC;
            ACC = v / B;
            B = v % B;
        }
        break;
    case 0x85: direct_write(s, y, direct_read(s, x, false)); break;
    case 0x90: set_dptr(s, (x << 8) | y); break;
    case 0x92: bit_write(s, x, PSW & CY); break;
    case 0xa2: carry(s, bit_read(s, x, false)); break;
    case 0xa3: set_dptr(s, dptr(s) + 1); break;
    case 0xa4:
        result = ACC * B;
        ACC = result;
        B = result >> 8;
        PSW = (PSW & ~(CY | OV)) | (B ? OV : 0);
        break;
    case 0xb2: bit_write(s, x, !bit_read(s, x, true)); break;
    case 0xb3: carry(s, !(PSW & CY)); break;
    case 0xb4: case 0xb5:
        v = op == 0xb4 ? x : direct_read(s, x, false);
        carry(s, ACC < v);
        if (ACC != v) { branch(s, y); }
        break;
    case 0xc0: v = direct_read(s, x, false); push(s, v); break;
    case 0xc2: bit_write(s, x, false); break;
    case 0xc3: carry(s, false); break;
    case 0xc4: ACC = (ACC << 4) | (ACC >> 4); break;
    case 0xc5: v = direct_read(s, x, true);
               direct_write(s, x, ACC); ACC = v; break;
    case 0xd0: v = pop(s); direct_write(s, x, v); break;
    case 0xd2: bit_write(s, x, true); break;
    case 0xd3: carry(s, true); break;
    case 0xd4:
        result = ACC;
        if ((result & 15) > 9 || (PSW & AC)) { result += 6; }
        if (result > 0x9f || (PSW & CY)) { result += 0x60; }
        if (result > 255) { carry(s, true); }
        ACC = result;
        break;
    case 0xd5:
        v = direct_read(s, x, true) - 1;
        direct_write(s, x, v);
        if (v) { branch(s, y); }
        break;
    case 0xe0: case 0xe2: case 0xe3:
        addr = op == 0xe0 ? dptr(s) :
               (SFR(s, 0xa0) << 8) | *reg(s, op & 1);
        ACC = s->xread ? s->xread(s->opaque, addr) : 0xff;
        break;
    case 0xe4: ACC = 0; break;
    case 0xf0: case 0xf2: case 0xf3:
        addr = op == 0xf0 ? dptr(s) :
               (SFR(s, 0xa0) << 8) | *reg(s, op & 1);
        if (s->xwrite) { s->xwrite(s->opaque, addr, ACC); }
        break;
    case 0xf4: ACC = ~ACC; break;
    case 0xf5: direct_write(s, x, ACC); break;
    default: return false;
    }

done:
    PSW = (PSW & ~1) | (__builtin_popcount((unsigned int)ACC) & 1);
    return true;
}
