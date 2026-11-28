/* SPDX-License-Identifier: Apache-2.0 */
#ifndef XED_REFERENCE_H
#define XED_REFERENCE_H

#include <stdbool.h>
#include <xed-interface.h>

enum { MAX_BYTES = 15 };

unsigned xed_ref_parse_bytes(const char *hex, xed_uint8_t *bytes);
xed_error_enum_t xed_ref_decode(xed_decoded_inst_t *inst,
                               xed_machine_mode_enum_t mode,
                               xed_address_width_enum_t stack,
                               xed_chip_enum_t chip,
                               const xed_uint8_t *bytes, unsigned len);
int xed_ref_compare_addresses(xed_machine_mode_enum_t mode,
                              xed_address_width_enum_t stack,
                              xed_chip_enum_t chip);

#endif
