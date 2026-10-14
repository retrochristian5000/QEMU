/* ISA decoder regression.  TAP protocol, independent of host GLib install. */
#include <stdlib.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../../target/f8/isa.h"

/* Tests must remain active in QEMU release builds with NDEBUG. */
#define CHECK(expr) do { \
    if (!(expr)) { \
        fprintf(stderr, "failure %s:%d: %s\n", __FILE__, __LINE__, #expr); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

static void test_opcodes(void)
{
    int reserved = 0, disputed = 0, extended = 0;
    for (int i = 0; i < 256; ++i) {
        F8Instruction op = f8_instruction((uint8_t)i);
        CHECK(op.length >= 1 && op.length <= 3);
        CHECK(op.mnemonic && *op.mnemonic);
        reserved += op.status == F8_OPCODE_RESERVED;
        disputed += op.status == F8_OPCODE_DISPUTED;
        extended += op.length > 1;
    }
    CHECK(reserved == 10); /* 2D-2F; 3F,4F,5F,CF,DF,EF,FF */
    CHECK(disputed == 4); /* A2 A3 B2 B3 ambiguous between references */
    CHECK(extended == 36); /* 8 immediate, 3 absolute, 25 relative */
}

static void test_length_and_buffer(void)
{
    uint8_t bytes[] = { 0x28, 0x12, 0x34 };
    F8Instruction out = { 0 };
    CHECK(!f8_decode_bytes(NULL, 3, &out));
    CHECK(!f8_decode_bytes(bytes, 0, &out));
    CHECK(!f8_decode_bytes(bytes, 3, NULL));
    CHECK(!f8_decode_bytes(bytes, 2, &out));
    CHECK(f8_decode_bytes(bytes, 3, &out));
    CHECK(out.length == 3 && !strcmp(out.mnemonic, "PI"));
    bytes[0] = 0x24;
    CHECK(!f8_decode_bytes(bytes, 1, &out));
    CHECK(f8_decode_bytes(bytes, 2, &out) && out.length == 2);
    bytes[0] = 0x2b;
    CHECK(f8_decode_bytes(bytes, 1, &out) && out.length == 1);
}

static void test_families(void)
{
    F8Instruction op;
    op = f8_instruction(0x1e);
    CHECK(!strcmp(op.mnemonic, "LR J,W"));
    op = f8_instruction(0x2c);
    CHECK(!strcmp(op.mnemonic, "XDC"));
    op = f8_instruction(0x6b);
    CHECK(!strcmp(op.mnemonic, "LISL") && op.operand == 3);
    op = f8_instruction(0x7f);
    CHECK(!strcmp(op.mnemonic, "LIS") && op.operand == 15);
    op = f8_instruction(0x81);
    CHECK(!strcmp(op.mnemonic, "BP") && op.length == 2);
    op = f8_instruction(0x8f);
    CHECK(!strcmp(op.mnemonic, "BR7") && op.length == 2);
    op = f8_instruction(0x9f);
    CHECK(!strcmp(op.mnemonic, "BF") && op.operand_kind == F8_OPERAND_MASK_REL8);
    op = f8_instruction(0x4e);
    CHECK(!strcmp(op.mnemonic, "LR A") && op.operand_kind == F8_OPERAND_ISAR);
    op = f8_instruction(0xff);
    CHECK(op.status == F8_OPCODE_RESERVED);
    op = f8_instruction(0xa2);
    CHECK(op.status == F8_OPCODE_DISPUTED);
}

int main(int argc, char **argv)
{
    (void)argc;
    (void)argv;
    puts("1..3");
    test_opcodes();
    puts("ok 1 - F8 byte map and uncertainties");
    test_length_and_buffer();
    puts("ok 2 - truncation and multi-byte lengths");
    test_families();
    puts("ok 3 - special groups and reversed register transfer");
    return 0;
}
