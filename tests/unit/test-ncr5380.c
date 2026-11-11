/*
 * NCR 5380 / 53C80 register-core tests
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/scsi/ncr5380.h"

static void test_data_register_is_direction_multiplexed(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_set_current_data(&s, 0xa5);
    ncr5380_core_write(&s, NCR5380_REG_OUTPUT_DATA, 0x5a);

    g_assert_cmphex(ncr5380_core_read(&s, NCR5380_REG_CURRENT_DATA), ==, 0xa5);
    g_assert_cmphex(s.output_data, ==, 0x5a);
}

static void test_icr_read_write_meanings_are_separate(void)
{
    NCR5380Core s;
    uint8_t icr;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_write(&s, NCR5380_REG_ICR,
                       NCR5380_ICR_TEST_MODE | NCR5380_ICR_DIFF_ENABLE |
                       NCR5380_ICR_ASSERT_ACK | NCR5380_ICR_ASSERT_DATA);
    icr = ncr5380_core_read(&s, NCR5380_REG_ICR);

    g_assert_cmphex(icr & (NCR5380_ICR_AIP |
                           NCR5380_ICR_LOST_ARBITRATION), ==, 0);
    g_assert_cmphex(icr & (NCR5380_ICR_ASSERT_ACK |
                           NCR5380_ICR_ASSERT_DATA), ==,
                    NCR5380_ICR_ASSERT_ACK | NCR5380_ICR_ASSERT_DATA);
    g_assert_true(s.test_mode);
}

static void test_phase_match_is_derived(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_write(&s, NCR5380_REG_TCR,
                       NCR5380_TCR_ASSERT_CD | NCR5380_TCR_ASSERT_IO);
    ncr5380_core_set_bus_status(&s, NCR5380_SR_CD | NCR5380_SR_IO);
    g_assert_true(ncr5380_core_read(&s, NCR5380_REG_BASR) &
                  NCR5380_BASR_PHASE_MATCH);

    ncr5380_core_set_bus_status(&s,
                                NCR5380_SR_MSG | NCR5380_SR_CD |
                                NCR5380_SR_IO);
    g_assert_false(ncr5380_core_read(&s, NCR5380_REG_BASR) &
                   NCR5380_BASR_PHASE_MATCH);
}

static void test_reset_parity_interrupt_read_is_destructive(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_set_bus_status(&s, NCR5380_SR_BSY);
    ncr5380_core_write(&s, NCR5380_REG_MODE,
                       NCR5380_MR_DMA | NCR5380_MR_PARITY_CHECK);
    ncr5380_core_set_parity_error(&s, true);
    s.irq = true;
    s.busy_error = true;
    ncr5380_core_set_end_dma(&s, true);
    ncr5380_core_set_dma_request(&s, true);

    (void)ncr5380_core_read(&s, NCR5380_REG_RESET_PARITY_INTERRUPT);

    g_assert_false(s.parity_error);
    g_assert_false(s.irq);
    g_assert_false(s.busy_error);
    g_assert_true(s.end_dma);
    g_assert_true(s.drq);
}

static void test_last_byte_sent_is_53c80_only(void)
{
    NCR5380Core nmos, cmos;

    ncr5380_core_init(&nmos, NCR5380_VARIANT_5380);
    ncr5380_core_init(&cmos, NCR5380_VARIANT_53C80);
    ncr5380_core_set_last_byte_sent(&nmos, true);
    ncr5380_core_set_last_byte_sent(&cmos, true);

    g_assert_false(ncr5380_core_read(&nmos, NCR5380_REG_TCR) &
                   NCR5380_TCR_LAST_BYTE_SENT);
    g_assert_true(ncr5380_core_read(&cmos, NCR5380_REG_TCR) &
                  NCR5380_TCR_LAST_BYTE_SENT);
}

static void test_dma_start_registers_select_direction(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_set_bus_status(&s, NCR5380_SR_BSY);
    ncr5380_core_write(&s, NCR5380_REG_MODE, NCR5380_MR_DMA);

    ncr5380_core_write(&s, NCR5380_REG_START_DMA_SEND, 0xff);
    g_assert_cmpint(s.dma_op, ==, NCR5380_DMA_SEND);

    ncr5380_core_write(&s, NCR5380_REG_START_DMA_INITIATOR_RECV, 0x00);
    g_assert_cmpint(s.dma_op, ==, NCR5380_DMA_INITIATOR_RECEIVE);

    ncr5380_core_write(&s, NCR5380_REG_MODE,
                       NCR5380_MR_DMA | NCR5380_MR_TARGET);
    ncr5380_core_write(&s, NCR5380_REG_START_DMA_TARGET_RECV, 0x55);
    g_assert_cmpint(s.dma_op, ==, NCR5380_DMA_TARGET_RECEIVE);
}

static void test_assert_rst_preserves_rst_and_irq(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_set_bus_status(&s, NCR5380_SR_BSY);
    ncr5380_core_write(&s, NCR5380_REG_MODE,
                       NCR5380_MR_DMA | NCR5380_MR_PARITY_CHECK);
    ncr5380_core_write(&s, NCR5380_REG_TCR,
                       NCR5380_TCR_ASSERT_MSG | NCR5380_TCR_ASSERT_CD);
    ncr5380_core_write(&s, NCR5380_REG_SELECT_ENABLE, 0x80);

    ncr5380_core_write(&s, NCR5380_REG_ICR,
                       NCR5380_ICR_ASSERT_RST | NCR5380_ICR_ASSERT_ACK);

    g_assert_cmphex(ncr5380_core_read(&s, NCR5380_REG_ICR), ==,
                    NCR5380_ICR_ASSERT_RST);
    g_assert_true(s.irq);
    g_assert_cmphex(s.mode, ==, 0);
    g_assert_cmphex(s.tcr, ==, 0);
    g_assert_cmphex(s.select_enable, ==, 0);
}

static void test_monitor_busy_loss_clears_outputs_and_dma(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_set_bus_status(&s, NCR5380_SR_BSY);
    ncr5380_core_write(&s, NCR5380_REG_ICR,
                       NCR5380_ICR_ASSERT_ACK | NCR5380_ICR_ASSERT_DATA);
    ncr5380_core_write(&s, NCR5380_REG_MODE,
                       NCR5380_MR_MONITOR_BSY | NCR5380_MR_DMA);

    ncr5380_core_set_bus_status(&s, 0);

    g_assert_true(s.busy_error);
    g_assert_true(s.irq);
    g_assert_false(s.mode & NCR5380_MR_DMA);
    g_assert_cmphex(ncr5380_core_read(&s, NCR5380_REG_ICR) & 0x3f, ==, 0);
}

static void test_req_rising_with_dma_phase_mismatch_raises_irq(void)
{
    NCR5380Core s;

    ncr5380_core_init(&s, NCR5380_VARIANT_5380);
    ncr5380_core_set_bus_status(&s, NCR5380_SR_BSY);
    ncr5380_core_write(&s, NCR5380_REG_TCR, NCR5380_TCR_ASSERT_IO);
    ncr5380_core_write(&s, NCR5380_REG_MODE, NCR5380_MR_DMA);

    ncr5380_core_set_bus_status(&s,
                                NCR5380_SR_BSY | NCR5380_SR_REQ |
                                NCR5380_SR_CD);

    g_assert_true(s.irq);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    g_test_add_func("/ncr5380/data-direction-multiplex",
                    test_data_register_is_direction_multiplexed);
    g_test_add_func("/ncr5380/icr-read-write-meanings",
                    test_icr_read_write_meanings_are_separate);
    g_test_add_func("/ncr5380/phase-match",
                    test_phase_match_is_derived);
    g_test_add_func("/ncr5380/reset-parity-interrupt",
                    test_reset_parity_interrupt_read_is_destructive);
    g_test_add_func("/ncr5380/53c80-last-byte-sent",
                    test_last_byte_sent_is_53c80_only);
    g_test_add_func("/ncr5380/dma-start-direction",
                    test_dma_start_registers_select_direction);
    g_test_add_func("/ncr5380/assert-rst",
                    test_assert_rst_preserves_rst_and_irq);
    g_test_add_func("/ncr5380/monitor-busy",
                    test_monitor_busy_loss_clears_outputs_and_dma);
    g_test_add_func("/ncr5380/phase-mismatch-irq",
                    test_req_rising_with_dma_phase_mismatch_raises_irq);

    return g_test_run();
}
