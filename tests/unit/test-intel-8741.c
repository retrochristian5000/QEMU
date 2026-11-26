/*
 * Intel 8741 host-interface and AT&T keyboard transfer tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/input/intel-8741.h"
#include "hw/input/intel-8741-program.h"
#include "hw/input/att-kbd302.h"

static void test_host_transfer(void)
{
    Intel8741Core s;
    uint8_t value = 0xee;
    bool command = false;

    intel_8741_core_reset(&s);
    g_assert_cmphex(intel_8741_status(&s), ==, 0);
    g_assert_false(intel_8741_host_read(&s, &value));
    g_assert_false(intel_8741_mcu_read(&s, &value, &command));
    g_assert_cmphex(value, ==, 0xee);
    g_assert_false(command);

    intel_8741_mcu_set_f0(&s, true);
    g_assert_true(intel_8741_host_write(&s, 0x05, true));
    g_assert_cmphex(intel_8741_status(&s), ==,
                    INTEL_8741_IBF | INTEL_8741_F0 | INTEL_8741_F1);
    g_assert_false(intel_8741_host_write(&s, 0xff, false));
    g_assert_false(intel_8741_mcu_write(&s, 0xff));
    g_assert_true(intel_8741_mcu_read(&s, &value, &command));
    g_assert_cmphex(value, ==, 0x05);
    g_assert_true(command);
    g_assert_cmphex(intel_8741_status(&s), ==,
                    INTEL_8741_F0 | INTEL_8741_F1);

    g_assert_true(intel_8741_host_write(&s, 0x12, false));
    g_assert_true(intel_8741_mcu_read(&s, &value, &command));
    g_assert_cmphex(value, ==, 0x12);
    g_assert_false(command);
    intel_8741_mcu_set_f1(&s, true);
    intel_8741_mcu_set_f0(&s, false);
    g_assert_cmphex(intel_8741_status(&s), ==, INTEL_8741_F1);
}

static void test_mcu_transfer(void)
{
    Intel8741Core s;
    uint8_t value = 0;
    bool command = true;

    intel_8741_core_reset(&s);
    g_assert_true(intel_8741_mcu_write(&s, 0xab));
    g_assert_cmphex(intel_8741_status(&s), ==, INTEL_8741_OBF);
    g_assert_false(intel_8741_mcu_write(&s, 0xcd));
    g_assert_false(intel_8741_host_write(&s, 0xef, true));
    g_assert_false(intel_8741_mcu_read(&s, &value, &command));
    g_assert_cmphex(value, ==, 0);
    g_assert_true(command);
    g_assert_true(intel_8741_host_read(&s, &value));
    g_assert_cmphex(value, ==, 0xab);
    g_assert_cmphex(intel_8741_status(&s), ==, 0);
    g_assert_false(intel_8741_host_read(&s, &value));
    g_assert_true(intel_8741_mcu_write(&s, 0x55));
    intel_8741_core_reset(&s);
    g_assert_cmphex(intel_8741_status(&s), ==, 0);
    g_assert_false(intel_8741_host_read(&s, &value));
    g_assert_true(intel_8741_host_write(&s, 0x11, true));
    intel_8741_core_reset(&s);
    g_assert_false(intel_8741_mcu_read(&s, &value, &command));
    g_assert_cmphex(intel_8741_status(&s), ==, 0);
}

/* Exercise the future board bridge's handshake using actual keyboard bytes.
 * This is not an implementation of AT&T controller firmware.
 */
static void test_keyboard_transfer(void)
{
    Intel8741Core s;
    AttKbd302Core kbd;
    uint8_t value;

    intel_8741_core_reset(&s);
    att_kbd302_core_reset(&kbd);
    g_assert_true(att_kbd302_core_key(&kbd, 0x60, true));
    g_assert_true(att_kbd302_core_key(&kbd, 0x60, false));

    g_assert_true(att_kbd302_core_read(&kbd, &value));
    g_assert_true(intel_8741_mcu_write(&s, value));
    g_assert_cmphex(intel_8741_status(&s), ==, INTEL_8741_OBF);
    g_assert_false(intel_8741_mcu_write(&s, 0xe0));
    g_assert_cmpuint(kbd.count, ==, 1);
    g_assert_true(intel_8741_host_read(&s, &value));
    g_assert_cmphex(value, ==, 0x60);

    g_assert_true(att_kbd302_core_read(&kbd, &value));
    g_assert_true(intel_8741_mcu_write(&s, value));
    g_assert_true(intel_8741_host_read(&s, &value));
    g_assert_cmphex(value, ==, 0xe0);
    g_assert_false(att_kbd302_core_read(&kbd, &value));
    g_assert_cmphex(intel_8741_status(&s), ==, 0);
}

static void test_program_echo(void)
{
    /* Poll for input, read it, echo it, then wait for the host to read. */
    static const uint8_t rom[INTEL_8741_PROGRAM_SIZE] = {
        0xd6, 0x00, /* JNIBF 0 */
        0x22,       /* IN A,DBB */
        0x02,       /* OUT DBB,A */
        0x86, 0x04, /* JOBF 4 */
        0x04, 0x00, /* JMP 0 */
    };
    Intel8741Core core;
    Intel8741Program cpu;
    uint8_t value = 0;

    intel_8741_core_reset(&core);
    intel_8741_program_reset(&cpu);
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_OK);
    g_assert_cmpuint(cpu.pc, ==, 0);
    g_assert_true(intel_8741_host_write(&core, 0x6a, false));
    for (unsigned int i = 0; i < 4; i++) {
        g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                        ==, INTEL_8741_STEP_OK);
    }
    g_assert_cmpuint(cpu.pc, ==, 4);
    g_assert_cmphex(intel_8741_status(&core), ==, INTEL_8741_OBF);
    g_assert_true(intel_8741_host_read(&core, &value));
    g_assert_cmphex(value, ==, 0x6a);
    for (unsigned int i = 0; i < 2; i++) {
        g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                        ==, INTEL_8741_STEP_OK);
    }
    g_assert_cmpuint(cpu.pc, ==, 0);
}

static void test_program_errors(void)
{
    static const uint8_t rom[INTEL_8741_PROGRAM_SIZE] = {
        0x22, 0x02, 0xe5, 0x23, 0x55, 0x64, 0xaa,
    };
    Intel8741Core core;
    Intel8741Program cpu;

    intel_8741_core_reset(&core);
    intel_8741_program_reset(&cpu);
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom) - 1),
                    ==, INTEL_8741_STEP_INVALID);
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_HANDSHAKE);
    g_assert_cmpuint(cpu.pc, ==, 0);
    g_assert_true(intel_8741_host_write(&core, 0xa5, true));
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_OK);
    g_assert_cmphex(cpu.acc, ==, 0xa5);
    g_assert_cmpuint(cpu.pc, ==, 1);
    g_assert_true(intel_8741_host_write(&core, 0x12, false));
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_HANDSHAKE);
    g_assert_cmpuint(cpu.pc, ==, 1);
    g_assert_cmphex(core.dbb, ==, 0x12);
    intel_8741_core_reset(&core);
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_OK);
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_UNSUPPORTED);
    g_assert_cmpuint(cpu.pc, ==, 2);
    cpu.pc = 3;
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_OK);
    g_assert_cmphex(cpu.acc, ==, 0x55);
    g_assert_cmpint(intel_8741_program_step(&cpu, &core, rom, sizeof(rom)),
                    ==, INTEL_8741_STEP_OK);
    g_assert_cmphex(cpu.pc, ==, 0x3aa);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/intel-8741/host-transfer", test_host_transfer);
    g_test_add_func("/intel-8741/mcu-transfer", test_mcu_transfer);
    g_test_add_func("/intel-8741/keyboard-transfer", test_keyboard_transfer);
    g_test_add_func("/intel-8741/program-echo", test_program_echo);
    g_test_add_func("/intel-8741/program-errors", test_program_errors);
    return g_test_run();
}
