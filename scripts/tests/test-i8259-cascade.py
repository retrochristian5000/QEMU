#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the software 8259 cascade with the actual PIC implementation."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "hw" / "intc" / "i8259.c"

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef uint64_t hwaddr;
typedef struct IRQLine {
    void (*handler)(void *, int, int);
    void *opaque;
    int n;
    int level;
} *qemu_irq;

typedef struct PICCommonState {
    uint8_t last_irr, irr, imr, isr, priority_add, irq_base;
    uint8_t read_reg_select, poll, special_mask, init_state;
    uint8_t auto_eoi, rotate_on_auto_eoi, special_fully_nested_mode;
    uint8_t init4, single_mode, elcr, ltim;
    uint32_t master;
    qemu_irq int_out[1];
} PICCommonState;

static PICCommonState *slave_pic;

#define trace_pic_update_irq(...) ((void)0)
#define trace_pic_set_irq(...) ((void)0)
#define trace_pic_interrupt(...) ((void)0)
#define trace_pic_ioport_write(...) ((void)0)

static uint8_t ror8(uint8_t v, unsigned int n)
{
    return (v >> n) | (v << ((8 - n) & 7));
}

static int ctz32(uint32_t v)
{
    assert(v);
    return __builtin_ctz(v);
}

static void qemu_irq_raise(qemu_irq irq)
{
    irq->level = 1;
    if (irq->handler) {
        irq->handler(irq->opaque, irq->n, 1);
    }
}

static void qemu_irq_lower(qemu_irq irq)
{
    irq->level = 0;
    if (irq->handler) {
        irq->handler(irq->opaque, irq->n, 0);
    }
}

static void pic_stat_update_irq(int irq, int level)
{
    (void)irq;
    (void)level;
}

static void pic_init_reset(PICCommonState *s)
{
    (void)s;
    assert(!"unexpected PIC initialization");
}
"""

CASES = r"""
static PICCommonState master, slave;
static struct IRQLine cpu_line, cascade;

static void reset_pair(bool slave_auto_eoi)
{
    memset(&master, 0, sizeof(master));
    memset(&slave, 0, sizeof(slave));
    memset(&cpu_line, 0, sizeof(cpu_line));
    cascade = (struct IRQLine) {
        .handler = pic_set_irq, .opaque = &master, .n = 2,
    };
    master.master = 1;
    master.irq_base = 0x20;
    master.int_out[0] = &cpu_line;
    slave.irq_base = 0x28;
    slave.int_out[0] = &cascade;
    slave.auto_eoi = slave_auto_eoi;
    slave_pic = &slave;
}

static void pulse(PICCommonState *s, int irq)
{
    pic_set_irq(s, irq, 1);
    pic_set_irq(s, irq, 0);
}

static void eoi(PICCommonState *s)
{
    pic_ioport_write(s, 0, 0x20, 1);
}

static void test_slave_auto_eoi(void)
{
    reset_pair(true);
    pulse(&slave, 6);
    pulse(&slave, 7);
    assert(cpu_line.level && cascade.level);
    assert(pic_read_irq(&master) == 0x2e);
    assert(slave.irr == 0x80);
    assert(master.irr & 4);
    assert(master.isr & 4);
    assert(!cpu_line.level);

    eoi(&master);
    assert(cpu_line.level);
    assert(pic_read_irq(&master) == 0x2f);
    eoi(&master);
    assert(!cpu_line.level && !cascade.level);
    assert(!master.irr && !slave.irr);
}

static void test_normal_eoi(void)
{
    reset_pair(false);
    pulse(&slave, 6);
    pulse(&slave, 7);
    assert(pic_read_irq(&master) == 0x2e);
    assert(slave.isr == 0x40 && slave.irr == 0x80);
    assert(!cascade.level && !(master.irr & 4));

    eoi(&slave);
    assert(cascade.level && (master.irr & 4));
    assert(!cpu_line.level);
    eoi(&master);
    assert(cpu_line.level);
    assert(pic_read_irq(&master) == 0x2f);
    eoi(&slave);
    eoi(&master);
    assert(!cpu_line.level && !cascade.level);
    assert(!master.irr && !slave.irr);
}

static void test_level_auto_eoi(void)
{
    reset_pair(true);
    slave.elcr = 0x08;
    pic_set_irq(&slave, 3, 1);
    assert(pic_read_irq(&master) == 0x2b);
    assert(master.irr & 4);
    eoi(&master);
    assert(cpu_line.level);
    /* A level request remains valid until the device deasserts it. */
    assert(pic_read_irq(&master) == 0x2b);
    pic_set_irq(&slave, 3, 0);
    eoi(&master);
    /* The edge-latched cascade may now be acknowledged as spurious IRQ15. */
    assert(pic_read_irq(&master) == 0x2f);
    assert(!slave.isr && (master.isr & 4));
    eoi(&master);
    assert(!cpu_line.level && !cascade.level);
}

static void test_master_and_spurious(void)
{
    reset_pair(false);
    pulse(&master, 0);
    assert(cpu_line.level);
    assert(pic_read_irq(&master) == 0x20);
    eoi(&master);
    assert(!cpu_line.level);
    assert(pic_read_irq(&master) == 0x27);
    assert(!master.isr);

    /* Master latched IR2, but the slave no longer has an eligible IRQ. */
    pulse(&master, 2);
    assert(pic_read_irq(&master) == 0x2f);
    assert(master.isr == 4 && !slave.isr && !master.irr);
    eoi(&master);
    assert(!cpu_line.level);
}

int main(void)
{
    test_slave_auto_eoi();
    test_normal_eoi();
    test_level_auto_eoi();
    test_master_and_spurious();
    return 0;
}
"""


class PICCascadeTests(unittest.TestCase):
    def test_interrupt_acknowledgement(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("static int get_priority(")
        end = source.index("\nstatic void pic_init_reset(", start)
        write_start = source.index("static void pic_ioport_write(")
        write_end = source.index("\nstatic uint64_t pic_ioport_read(",
                                 write_start)
        implementation = source[start:end] + "\n" + source[write_start:write_end]
        cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(cc, "native C compiler required")
        with tempfile.TemporaryDirectory(prefix="qemu-pic-cascade-") as work:
            c_path = Path(work) / "test.c"
            binary = Path(work) / "test"
            c_path.write_text(STUBS + implementation + CASES, encoding="utf-8")
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-Wno-unused-parameter", str(c_path), "-o",
                            str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
