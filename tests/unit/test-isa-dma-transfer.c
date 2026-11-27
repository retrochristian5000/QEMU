/*
 * Regression tests for ISA DMA address and transfer ordering.
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include "hw/dma/isa-dma-transfer.h"

static void test_dma_boundaries(void)
{
    ISADMASpan s;

    s = isa_dma_span(0x120000, 0xfffe, 0, false, false, 0, 4);
    g_assert_cmphex(s.addr, ==, 0x12fffe);
    g_assert_cmpuint(s.len, ==, 2);
    s = isa_dma_span(0x120000, 0xfffe, 0, false, false, 2, 2);
    g_assert_cmphex(s.addr, ==, 0x120000);
    s = isa_dma_span(0x130000, 0x1fffe, 1, false, false, 0, 4);
    g_assert_cmphex(s.addr, ==, 0x13fffe);
    g_assert_cmpuint(s.len, ==, 2);
    s = isa_dma_span(0x130000, 0x1fffe, 1, false, false, 2, 2);
    g_assert_cmphex(s.addr, ==, 0x120000);
    s = isa_dma_span(0, 0x12fffe, 0, true, false, 0, 4);
    g_assert_cmphex(s.addr, ==, 0x12fffe);
    g_assert_cmpuint(s.len, ==, 4);
}

static void test_dma_order(void)
{
    const uint8_t src[] = { 1, 2, 3, 4, 5, 6 };
    const uint8_t bytes[] = { 6, 5, 4, 3, 2, 1 };
    const uint8_t words[] = { 5, 6, 3, 4, 1, 2 };
    uint8_t dst[sizeof(src)];

    isa_dma_reverse_units(dst, src, sizeof(src), 0);
    g_assert_cmpmem(dst, sizeof(dst), bytes, sizeof(bytes));
    isa_dma_reverse_units(dst, src, sizeof(src), 1);
    g_assert_cmpmem(dst, sizeof(dst), words, sizeof(words));
}

static void test_dma_spans(void)
{
    GRand *rng = g_rand_new_with_seed(0x8237);

    for (unsigned i = 0; i < 20000; i++) {
        unsigned shift = i & 1;
        bool decrement = i & 2;
        bool linear = i & 4;
        unsigned unit = 1U << shift;
        uint32_t mask = (0x10000U << shift) - 1;
        uint32_t page = g_rand_int(rng) & 0x7fff0000;
        uint32_t start = (g_rand_int(rng) & mask) & ~(unit - 1);
        unsigned pos = g_rand_int_range(rng, 0, 65536);
        unsigned len = g_rand_int_range(rng, 1, 257);
        unsigned done = 0;

        if (linear) {
            start |= page;
        }
        while (done < len) {
            ISADMASpan s = isa_dma_span(page, start, shift, linear,
                                        decrement, pos + done, len - done);

            g_assert_cmpuint(s.len, >, 0);
            g_assert_cmpuint(s.len, <=, len - done);
            for (unsigned j = 0; j < s.len; j++) {
                unsigned p = pos + done + j;
                uint32_t delta = (p / unit) * unit;
                uint32_t addr = decrement ? start - delta : start + delta;
                uint32_t actual = s.addr + j;

                addr += p % unit;
                if (!linear) {
                    addr = (page & ~mask) | (addr & mask);
                }
                if (s.reverse) {
                    actual = s.addr + s.len - unit -
                             (j / unit) * unit + j % unit;
                }
                g_assert_cmphex(actual, ==, addr);
            }
            done += s.len;
        }
    }
    g_rand_free(rng);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/isa-dma/boundaries", test_dma_boundaries);
    g_test_add_func("/isa-dma/order", test_dma_order);
    g_test_add_func("/isa-dma/spans", test_dma_spans);
    return g_test_run();
}
