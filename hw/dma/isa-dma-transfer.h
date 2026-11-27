/*
 * Shared ISA DMA transfer address and ordering helpers.
 * SPDX-License-Identifier: MIT
 */
#ifndef HW_DMA_ISA_DMA_TRANSFER_H
#define HW_DMA_ISA_DMA_TRANSFER_H

typedef struct ISADMASpan {
    uint32_t addr;
    unsigned len;
    bool reverse;
} ISADMASpan;

/*
 * Positions and lengths are bytes, even for word channels. In decrement
 * mode the units are reversed, never the byte lanes within a word.
 * Extended EISA addressing retains linear page carry.
 */
static inline ISADMASpan isa_dma_span(uint32_t page, uint32_t start,
                                    unsigned shift, bool linear,
                                    bool decrement, unsigned pos,
                                    unsigned len)
{
    unsigned unit = 1U << shift;
    uint32_t mask = linear ? UINT32_MAX : (0x10000U << shift) - 1;
    unsigned lane = pos & (unit - 1);
    uint32_t delta = pos & ~(unit - 1);
    uint32_t offset = (start + (decrement ? -delta : delta)) & mask;
    uint32_t base = linear ? 0 : page & ~mask;
    ISADMASpan span = { .addr = base | (offset + lane), .len = len };

    if (!decrement) {
        uint64_t available = (uint64_t)mask - offset - lane + 1;
        span.len = MIN((uint64_t)len, available);
    } else if (lane || len < unit) {
        span.len = MIN(len, unit - lane);
    } else {
        unsigned units = MIN((uint64_t)(len / unit),
                             (uint64_t)offset / unit + 1);

        span.len = units * unit;
        span.addr = base | (offset - (span.len - unit));
        span.reverse = units > 1;
    }
    return span;
}

static inline void isa_dma_reverse_units(uint8_t *dst, const uint8_t *src,
                                        unsigned len, unsigned shift)
{
    unsigned unit = 1U << shift;

    for (unsigned i = 0; i < len; i += unit) {
        memcpy(dst + i, src + len - unit - i, unit);
    }
}

#endif
