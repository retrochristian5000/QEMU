/* SPDX-License-Identifier: Apache-2.0 */
/* Offset-only XED address generation, with explicit guest state. */
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "xed-reference.h"

enum {
    GPR_AX, GPR_CX, GPR_DX, GPR_BX, GPR_SP, GPR_BP, GPR_SI, GPR_DI,
    GPR_COUNT
};
enum { SEG_CS, SEG_DS, SEG_ES, SEG_SS, SEG_FS, SEG_GS, SEG_COUNT };

typedef struct {
    uint32_t gpr[GPR_COUNT];
    uint32_t seg[SEG_COUNT];
} AddressState;

static int segment_index(xed_reg_enum_t reg)
{
    switch (reg) {
    case XED_REG_CS: return SEG_CS;
    case XED_REG_DS: return SEG_DS;
    case XED_REG_ES: return SEG_ES;
    case XED_REG_SS: return SEG_SS;
    case XED_REG_FS: return SEG_FS;
    case XED_REG_GS: return SEG_GS;
    default: return -1;
    }
}

static xed_uint64_t read_register(xed_reg_enum_t reg, void *context,
                                  xed_bool_t *error)
{
    const AddressState *state = context;

    *error = 0;
    switch (reg) {
    case XED_REG_AX: return (uint16_t)state->gpr[GPR_AX];
    case XED_REG_CX: return (uint16_t)state->gpr[GPR_CX];
    case XED_REG_DX: return (uint16_t)state->gpr[GPR_DX];
    case XED_REG_BX: return (uint16_t)state->gpr[GPR_BX];
    case XED_REG_SP: return (uint16_t)state->gpr[GPR_SP];
    case XED_REG_BP: return (uint16_t)state->gpr[GPR_BP];
    case XED_REG_SI: return (uint16_t)state->gpr[GPR_SI];
    case XED_REG_DI: return (uint16_t)state->gpr[GPR_DI];
    case XED_REG_EAX: return state->gpr[GPR_AX];
    case XED_REG_ECX: return state->gpr[GPR_CX];
    case XED_REG_EDX: return state->gpr[GPR_DX];
    case XED_REG_EBX: return state->gpr[GPR_BX];
    case XED_REG_ESP: return state->gpr[GPR_SP];
    case XED_REG_EBP: return state->gpr[GPR_BP];
    case XED_REG_ESI: return state->gpr[GPR_SI];
    case XED_REG_EDI: return state->gpr[GPR_DI];
    default:
        /*
         * Supply a zero selector to XED in real mode, so it computes
         * the offset without truncating the linear segment-base sum.
         */
        if (segment_index(reg) < 0) {
            *error = 1;
        }
        return 0;
    }
}

static xed_uint64_t zero_segment_base(xed_reg_enum_t reg, void *context,
                                      xed_bool_t *error)
{
    (void)context;
    *error = segment_index(reg) < 0;
    return 0;
}

static bool parse_u32(const char *s, uint32_t *value)
{
    size_t len;
    if (!s || !(len = strlen(s)) || len > 8 ||
        strspn(s, "0123456789abcdefABCDEF") != len) {
        return false;
    }
    *value = (uint32_t)strtoul(s, NULL, 16);
    return true;
}

/*
 * Limit the reference to one explicit memory operand of scalar MOV.
 * Implicit stack/string accesses and address-only LEA require their
 * own access-order contracts and must not be guessed here.
 */
static bool check_address(const char *hex, uint32_t observed,
                          unsigned access_bytes, char direction,
                          AddressState *state, xed_machine_mode_enum_t mode,
                          xed_address_width_enum_t stack, xed_chip_enum_t chip)
{
    xed_uint8_t bytes[MAX_BYTES];
    xed_decoded_inst_t inst;
    unsigned len = xed_ref_parse_bytes(hex, bytes);
    xed_uint64_t offset = 0;
    unsigned width;
    int seg;
    uint32_t base, linear;
    xed_error_enum_t err;

    if (!len) {
        return false;
    }
    err = xed_ref_decode(&inst, mode, stack, chip, bytes, len);
    if (err != XED_ERROR_NONE ||
        xed_decoded_inst_get_length(&inst) != len ||
        !xed_decoded_inst_valid_for_chip(&inst, chip) ||
        xed_decoded_inst_get_iclass(&inst) != XED_ICLASS_MOV ||
        xed_decoded_inst_number_of_memory_operands(&inst) != 1) {
        fprintf(stderr, "Unsupported MOV address record: %s (%s)\n",
                hex, xed_error_enum_t2str(err));
        return false;
    }

    if (access_bytes &&
        (xed_decoded_inst_get_memory_operand_length(&inst, 0) != access_bytes ||
         (direction == 'r' &&
          !xed_decoded_inst_mem_read(&inst, 0)) ||
         (direction == 'w' &&
          !xed_decoded_inst_mem_written(&inst, 0)))) {
        fprintf(stderr, "%s: observed %c/%u bytes, XED %u bytes "
                "(read=%u write=%u)\n", hex, direction, access_bytes,
                xed_decoded_inst_get_memory_operand_length(&inst, 0),
                (unsigned)xed_decoded_inst_mem_read(&inst, 0),
                (unsigned)xed_decoded_inst_mem_written(&inst, 0));
        return false;
    }

    width = xed_decoded_inst_get_memop_address_width(&inst, 0);
    seg = segment_index(xed_decoded_inst_get_seg_reg(&inst, 0));
    if ((width != 16 && width != 32) || seg < 0) {
        fprintf(stderr, "Unsupported address width or segment: %s\n", hex);
        return false;
    }

    err = xed_agen(&inst, 0, state, &offset);
    if (err != XED_ERROR_NONE ||
        offset > (width == 16 ? UINT16_MAX : UINT32_MAX)) {
        fprintf(stderr, "XED offset calculation failed: %s (%s)\n",
                hex, xed_error_enum_t2str(err));
        return false;
    }

    base = state->seg[seg];
    if (mode == XED_MACHINE_MODE_REAL_16) {
        /*
         * Ordinary real mode only: selectors, not cached descriptor
         * bases. This is a linear address before any A20 masking.
         */
        if (offset > UINT16_MAX) {
            fputs("Extended real-mode offset is outside reference scope\n",
                  stderr);
            return false;
        }
        base <<= 4;
    }
    linear = base + (uint32_t)offset;
    if (linear != observed) {
        fprintf(stderr, "%s: observed=%08" PRIx32
                " reference=%08" PRIx32 " offset=%08" PRIx64
                " base=%08" PRIx32 "\n",
                hex, observed, linear, (uint64_t)offset, base);
        return false;
    }
    return true;
}

int xed_ref_compare_addresses(xed_machine_mode_enum_t mode,
                              xed_address_width_enum_t stack,
                              xed_chip_enum_t chip)
{
    char line[512];
    const char *delim = " \t\r\n";
    size_t records = 0, failures = 0;

    xed_agen_register_callback(read_register, zero_segment_base);
    while (fgets(line, sizeof(line), stdin)) {
        AddressState state = {0};
        char *tag, *hex;
        uint32_t observed, access_bytes = 0;
        char direction = 0;
        bool valid, memory_record;

        if (!strchr(line, '\n')) {
            fputs("Incomplete or oversized address record\n", stderr);
            return EXIT_FAILURE;
        }
        tag = strtok(line, delim);
        if (!tag || tag[0] == '#') {
            continue;
        }
        records++;
        hex = strtok(NULL, delim);
        if (!strcmp(tag, "XEDCAPTURE_ERROR")) {
            fprintf(stderr, "TCG capture error in record %zu\n", records);
            failures++;
            continue;
        }
        memory_record = !strcmp(tag, "XEDMEM");
        valid = (memory_record || !strcmp(tag, "XEDAGEN")) && hex &&
                parse_u32(strtok(NULL, delim), &observed);
        if (valid && memory_record) {
            char *access;
            valid = parse_u32(strtok(NULL, delim), &access_bytes) &&
                    (access_bytes == 1 || access_bytes == 2 ||
                     access_bytes == 4);
            access = strtok(NULL, delim);
            valid = valid && access &&
                    (!strcmp(access, "r") || !strcmp(access, "w"));
            if (valid) {
                direction = access[0];
            }
        }
        for (unsigned i = 0; valid && i < GPR_COUNT; i++) {
            valid = parse_u32(strtok(NULL, delim), &state.gpr[i]);
        }
        for (unsigned i = 0; valid && i < SEG_COUNT; i++) {
            valid = parse_u32(strtok(NULL, delim), &state.seg[i]);
            if (mode == XED_MACHINE_MODE_REAL_16 &&
                state.seg[i] > UINT16_MAX) {
                valid = false;
            }
        }
        if (!valid || strtok(NULL, delim)) {
            fprintf(stderr, "Malformed XEDAGEN record %zu\n", records);
            failures++;
            continue;
        }
        if (!check_address(hex, observed, access_bytes, direction,
                           &state, mode, stack, chip)) {
            failures++;
        }
    }
    if (ferror(stdin) || !records) {
        fputs("No complete address records available\n", stderr);
        return EXIT_FAILURE;
    }
    printf("XED addresses: %zu records, %zu failures\n", records, failures);
    return failures ? EXIT_FAILURE : EXIT_SUCCESS;
}
