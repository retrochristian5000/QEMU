/* Fairchild F8 register model tests (no assumption about chip power-on). */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../target/f8/regs.h"

#define CHECK(cond) do { if (!(cond)) { \
    fprintf(stderr, "failure line %d: %s\n", __LINE__, #cond); \
    exit(EXIT_FAILURE); \
} } while (0)

static void core_and_flags(void)
{
    F8Registers r;
    f8_regs_init_for_test(&r);
    CHECK(r.core.a == 0 && r.core.w == 0);
    CHECK(r.addr.pc0 == 0 && r.addr.pc1 == 0);
    CHECK(r.addr.dc0 == 0 && r.addr.dc1 == 0);
    CHECK(sizeof(r.core.scratchpad) == 64);
    CHECK(F8_W_SIGN == 1 && F8_W_CARRY == 2 && F8_W_ZERO == 4);
    CHECK(F8_W_OVERFLOW == 8 && F8_W_INTERRUPT == 16);
    f8_regs_set_w(&r.core, 0xff);
    CHECK(r.core.w == 0x1f);
    r.core.a = 0xfe;
    f8_regs_a_to_isar(&r.core);
    CHECK(r.core.isar == 0x3e);
    r.core.a = 0;
    f8_regs_isar_to_a(&r.core);
    CHECK(r.core.a == 0x3e);
    f8_regs_set_isar_upper(&r.core, 0xff);
    CHECK(r.core.isar == 0x3e);
    f8_regs_set_isar_lower(&r.core, 0xff);
    CHECK(r.core.isar == 0x3f);
    f8_regs_set_isar_upper(&r.core, 0);
    CHECK(r.core.isar == 7);
}

static void direct_and_indirect(void)
{
    F8Registers r;
    uint8_t value = 0x55, index = 0xaa;
    f8_regs_init_for_test(&r);
    for (int i = 0; i < 12; i++) {
        CHECK(f8_regs_write_scratch(&r.core, i, i + 10));
        CHECK(f8_regs_read_scratch(&r.core, i, &value));
        CHECK(value == i + 10);
    }
    f8_regs_set_isar(&r.core, 0x17); /* Octal 27. */
    CHECK(f8_regs_write_scratch(&r.core, 13, 0xd7));
    CHECK(r.core.scratchpad[0x17] == 0xd7);
    CHECK(r.core.isar == 0x10); /* Octal 20, NOT 30. */
    CHECK(f8_regs_write_scratch(&r.core, 14, 0xe0));
    CHECK(r.core.scratchpad[0x10] == 0xe0);
    CHECK(r.core.isar == 0x17);
    CHECK(f8_regs_read_scratch(&r.core, 12, &value));
    CHECK(value == 0xd7 && r.core.isar == 0x17);
    CHECK(!f8_regs_scratch_index(&r.core, 15, &index));
    CHECK(index == 0xaa && r.core.isar == 0x17);
    CHECK(!f8_regs_scratch_index(&r.core, 0xff, &index));
    CHECK(!f8_regs_read_scratch(&r.core, 12, NULL));
    CHECK(!f8_regs_write_scratch(NULL, 0, 0));
    CHECK(!f8_regs_scratch_index(NULL, 12, &index));
}

static void scratchpad_aliases(void)
{
    F8Registers r;
    uint16_t val = 0;
    f8_regs_init_for_test(&r);
    CHECK(f8_regs_set_pair(&r.core, F8_PAIR_H, 0xabcd));
    CHECK(r.core.scratchpad[10] == 0xab && r.core.scratchpad[11] == 0xcd);
    CHECK(f8_regs_set_pair(&r.core, F8_PAIR_K, 0x1234));
    CHECK(r.core.scratchpad[12] == 0x12 && r.core.scratchpad[13] == 0x34);
    CHECK(f8_regs_set_pair(&r.core, F8_PAIR_Q, 0x5678));
    CHECK(r.core.scratchpad[14] == 0x56 && r.core.scratchpad[15] == 0x78);
    CHECK(f8_regs_get_pair(&r.core, F8_PAIR_H, &val) && val == 0xabcd);
    CHECK(f8_regs_get_pair(&r.core, F8_PAIR_K, &val) && val == 0x1234);
    CHECK(f8_regs_get_pair(&r.core, F8_PAIR_Q, &val) && val == 0x5678);
    CHECK(!f8_regs_get_pair(&r.core, (F8ScratchPair)9, &val));
    CHECK(!f8_regs_set_pair(&r.core, (F8ScratchPair)9, 0xffff));
    r.core.w = 0x13;
    f8_regs_w_to_j(&r.core);
    CHECK(r.core.scratchpad[9] == 0x13);
    r.core.w = 0;
    f8_regs_j_to_w(&r.core);
    CHECK(r.core.w == 0x13);
    r.core.scratchpad[9] = 0xff;
    f8_regs_j_to_w(&r.core);
    CHECK(r.core.w == 0x1f);
}

static void distinct_address_registers(void)
{
    F8Registers r;
    f8_regs_init_for_test(&r);
    r.addr.pc0 = 0xfffe;
    r.addr.pc1 = 0x1280;
    r.addr.dc0 = 0x3400;
    r.addr.dc1 = 0x5600;
    CHECK(r.addr.pc0 == 0xfffe && r.addr.pc1 == 0x1280);
    CHECK(r.addr.dc0 == 0x3400 && r.addr.dc1 == 0x5600);
    CHECK(r.core.scratchpad[12] == 0 && r.core.scratchpad[15] == 0);
    CHECK(sizeof(r.addr.pc0) == 2 && sizeof(r.addr.dc1) == 2);
}

int main(void)
{
    puts("1..4");
    core_and_flags();
    puts("ok 1 - core width and flags");
    direct_and_indirect();
    puts("ok 2 - direct, indirect and ISAR octal wrap");
    scratchpad_aliases();
    puts("ok 3 - H/K/Q and J/W scratchpad aliases");
    distinct_address_registers();
    puts("ok 4 - distinct PC/DC address counters");
    return 0;
}
