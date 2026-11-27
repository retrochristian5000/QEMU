/*
 * TCG software TLB occupancy accounting.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "accel/tcg/tlb-bounds.h"

static void test_usage_transitions(void)
{
    size_t used = 0;

    tlb_usage_update(&used, false, false);
    g_assert_cmpuint(used, ==, 0);
    tlb_usage_update(&used, false, true);
    g_assert_cmpuint(used, ==, 1);

    /* Refill or replace an occupied slot without inflating occupancy. */
    for (unsigned i = 0; i < 10000; i++) {
        tlb_usage_update(&used, true, true);
    }
    g_assert_cmpuint(used, ==, 1);
    tlb_usage_update(&used, true, false);
    g_assert_cmpuint(used, ==, 0);

    /* Promote a victim entry into an empty main-table slot. */
    tlb_usage_update(&used, false, true);
    g_assert_cmpuint(used, ==, 1);
    tlb_usage_update(&used, true, false);
    g_assert_cmpuint(used, ==, 0);
}

static void test_usage_against_slots(void)
{
    bool slots[256] = { false };
    size_t used = 0;
    GRand *rng = g_rand_new_with_seed(0x544c42);

    for (unsigned i = 0; i < 20000; i++) {
        unsigned slot = g_rand_int_range(rng, 0, G_N_ELEMENTS(slots));
        bool next = g_rand_int_range(rng, 0, 2);
        size_t actual = 0;

        tlb_usage_update(&used, slots[slot], next);
        slots[slot] = next;
        for (unsigned j = 0; j < G_N_ELEMENTS(slots); j++) {
            actual += slots[j];
        }
        g_assert_cmpuint(used, ==, actual);
    }
    g_rand_free(rng);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/tlb/usage/transitions", test_usage_transitions);
    g_test_add_func("/tlb/usage/slots", test_usage_against_slots);
    return g_test_run();
}
