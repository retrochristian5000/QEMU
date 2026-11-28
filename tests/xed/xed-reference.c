/* SPDX-License-Identifier: Apache-2.0 */
/* Standalone Intel XED reference. No QEMU headers or libraries. */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <xed-interface.h>

enum { MAX_BYTES = 15 };

static int hex_digit(char c)
{
    if (c >= '0' && c <= '9') {
        return c - '0';
    }
    if (c >= 'a' && c <= 'f') {
        return c - 'a' + 10;
    }
    if (c >= 'A' && c <= 'F') {
        return c - 'A' + 10;
    }
    return -1;
}

static unsigned parse_bytes(const char *hex, xed_uint8_t *bytes)
{
    size_t len = strlen(hex);
    if (!len || len % 2 || len > MAX_BYTES * 2) {
        return 0;
    }
    for (size_t i = 0; i < len / 2; i++) {
        int hi = hex_digit(hex[2 * i]);
        int lo = hex_digit(hex[2 * i + 1]);
        if (hi < 0 || lo < 0) {
            return 0;
        }
        bytes[i] = (xed_uint8_t)((hi << 4) | lo);
    }
    return (unsigned)(len / 2);
}

static xed_error_enum_t decode(xed_decoded_inst_t *inst,
                               xed_machine_mode_enum_t mode,
                               xed_address_width_enum_t stack,
                               xed_chip_enum_t chip,
                               const xed_uint8_t *bytes, unsigned len)
{
    xed_state_t state;
    xed_state_init2(&state, mode, stack);
    xed_decoded_inst_zero_set_mode(inst, &state);
    xed_decoded_inst_set_input_chip(inst, chip);
    return xed_decode(inst, bytes, len);
}

static int selftest(void)
{
    static const struct {
        const char *hex;
        xed_machine_mode_enum_t mode;
        unsigned mem_bytes;
        unsigned address_bits;
        unsigned imm_bits;
        uint64_t imm;
    } cases[] = {
        { "8b00", XED_MACHINE_MODE_REAL_16, 2, 16, 0, 0 },
        { "668b00", XED_MACHINE_MODE_REAL_16, 4, 16, 0, 0 },
        { "678b00", XED_MACHINE_MODE_REAL_16, 2, 32, 0, 0 },
        { "66678b00", XED_MACHINE_MODE_REAL_16, 4, 32, 0, 0 },
        { "8b00", XED_MACHINE_MODE_LEGACY_32, 4, 32, 0, 0 },
        { "668b00", XED_MACHINE_MODE_LEGACY_32, 2, 32, 0, 0 },
        { "678b00", XED_MACHINE_MODE_LEGACY_32, 4, 16, 0, 0 },
        { "c2ffff", XED_MACHINE_MODE_LEGACY_32, 0, 0, 16, 65535 },
        { "caffff", XED_MACHINE_MODE_LEGACY_32, 0, 0, 16, 65535 },
        { "c8008021", XED_MACHINE_MODE_LEGACY_32, 0, 0, 16, 32768 },
    };
    for (size_t i = 0; i < sizeof(cases) / sizeof(cases[0]); i++) {
        xed_uint8_t bytes[MAX_BYTES];
        xed_decoded_inst_t inst;
        unsigned len = parse_bytes(cases[i].hex, bytes);
        xed_address_width_enum_t stack =
            cases[i].mode == XED_MACHINE_MODE_LEGACY_32 ?
            XED_ADDRESS_WIDTH_32b : XED_ADDRESS_WIDTH_16b;
        xed_error_enum_t err = decode(&inst, cases[i].mode, stack,
                                       XED_CHIP_PENTIUMMMX, bytes, len);
        if (err != XED_ERROR_NONE ||
            xed_decoded_inst_get_length(&inst) != len ||
            (cases[i].mem_bytes &&
             (xed_decoded_inst_number_of_memory_operands(&inst) != 1 ||
              xed_decoded_inst_get_memory_operand_length(&inst, 0) !=
              cases[i].mem_bytes ||
              xed_decoded_inst_get_memop_address_width(&inst, 0) !=
              cases[i].address_bits)) ||
            (cases[i].imm_bits &&
             (xed_decoded_inst_get_immediate_width_bits(&inst) !=
              cases[i].imm_bits ||
              xed_decoded_inst_get_unsigned_immediate(&inst) != cases[i].imm))) {
            fprintf(stderr, "XED selftest failed: case %zu (%s), %s\n",
                    i + 1, cases[i].hex, xed_error_enum_t2str(err));
            return EXIT_FAILURE;
        }
    }
    puts("XED reference selftest: 10 cases passed");
    return EXIT_SUCCESS;
}

static int compare_trace(xed_machine_mode_enum_t mode,
                         xed_address_width_enum_t stack,
                         xed_chip_enum_t chip)
{
    char line[256];
    size_t records = 0, mismatches = 0;

    while (fgets(line, sizeof(line), stdin)) {
        uint64_t pc;
        size_t length;
        char hex[31], extra;
        xed_uint8_t bytes[MAX_BYTES];
        xed_decoded_inst_t inst;
        unsigned len;
        xed_error_enum_t err;

        if (strncmp(line, "XEDTRACE ", 9)) {
            continue;
        }
        records++;
        if (!strchr(line, '\n') ||
            sscanf(line, "XEDTRACE %" SCNx64 " %zu %30s %c",
                   &pc, &length, hex, &extra) != 3 ||
            !(len = parse_bytes(hex, bytes)) || length != len) {
            fprintf(stderr, "Malformed/unavailable trace record %zu\n", records);
            mismatches++;
            continue;
        }
        err = decode(&inst, mode, stack, chip, bytes, len);
        if (err != XED_ERROR_NONE) {
            fprintf(stderr, "0x%" PRIx64 ": XED %s (%s)\n",
                    pc, xed_error_enum_t2str(err), hex);
            mismatches++;
            continue;
        }
        if (xed_decoded_inst_get_length(&inst) != length ||
            !xed_decoded_inst_valid_for_chip(&inst, chip)) {
            fprintf(stderr, "0x%" PRIx64 ": TCG length %zu, XED length %u, "
                    "chip-valid %u (%s)\n", pc, length,
                    xed_decoded_inst_get_length(&inst),
                    (unsigned)xed_decoded_inst_valid_for_chip(&inst, chip),
                    hex);
            mismatches++;
        }
    }

    if (ferror(stdin) || !records) {
        fputs("No complete XED trace records available\n", stderr);
        return EXIT_FAILURE;
    }
    printf("XED trace: %zu records, %zu mismatches\n", records, mismatches);
    return mismatches ? EXIT_FAILURE : EXIT_SUCCESS;
}

int main(int argc, char **argv)
{
    xed_machine_mode_enum_t mode;
    xed_address_width_enum_t stack;
    xed_chip_enum_t chip;

    xed_tables_init();
    if (argc == 2 && !strcmp(argv[1], "--selftest")) {
        return selftest();
    }
    if (argc != 4) {
        goto usage;
    }
    if (!strcmp(argv[1], "real16")) {
        mode = XED_MACHINE_MODE_REAL_16;
    } else if (!strcmp(argv[1], "legacy16")) {
        mode = XED_MACHINE_MODE_LEGACY_16;
    } else if (!strcmp(argv[1], "legacy32")) {
        mode = XED_MACHINE_MODE_LEGACY_32;
    } else {
        goto usage;
    }
    if (!strcmp(argv[2], "16")) {
        stack = XED_ADDRESS_WIDTH_16b;
    } else if (!strcmp(argv[2], "32")) {
        stack = XED_ADDRESS_WIDTH_32b;
    } else {
        goto usage;
    }
    if (!strcmp(argv[3], "pentium")) {
        chip = XED_CHIP_PENTIUM;
    } else if (!strcmp(argv[3], "pentium_mmx")) {
        chip = XED_CHIP_PENTIUMMMX;
    } else {
        goto usage;
    }
    return compare_trace(mode, stack, chip);

usage:
    fprintf(stderr, "Usage: %s --selftest | "
            "{real16|legacy16|legacy32} {16|32} "
            "{pentium|pentium_mmx} < trace.log\n", argv[0]);
    return EXIT_FAILURE;
}
