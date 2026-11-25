/* SPDX-License-Identifier: MIT */
#ifndef HW_BLOCK_DVDROM_H
#define HW_BLOCK_DVDROM_H

#include <stddef.h>
#include <stdint.h>

/*
 * Generate a DVD-ROM structure response into a full-size buffer.
 * sectors counts 2048-byte logical blocks. Returns response length or
 * -EINVAL (unsupported format/layer), -ENOMEDIUM, or -ENOSPC.
 */
int dvdrom_read_structure(uint64_t sectors, uint8_t layer, uint8_t format,
                          uint8_t *buf, size_t capacity);

#endif
