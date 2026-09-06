/*
 * NCR 5380 / 53C80 SCSI protocol-controller register core
 *
 * This file models the CPU-visible eight-register interface and the status
 * latches that are intrinsic to the NCR chip. Board-specific pseudo-DMA/DACK,
 * DTACK/BERR and Macintosh address decoding belong in the board wrapper.
 *
 * Register semantics follow NCR, "5380-53C80 SCSI Interface Chip Design
 * Manual", SP-1051 (March 1986), section 6 and appendix A5.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/scsi/ncr5380.h"

#define NCR5380_ICR_WRITABLE (NCR5380_ICR_ASSERT_RST | \
                              NCR5380_ICR_ASSERT_ACK | \
                              NCR5380_ICR_ASSERT_BSY | \
                              NCR5380_ICR_ASSERT_SEL | \
                              NCR5380_ICR_ASSERT_ATN | \
                              NCR5380_ICR_ASSERT_DATA)
#define NCR5380_TCR_WRITABLE (NCR5380_TCR_ASSERT_REQ | \
                              NCR5380_TCR_ASSERT_MSG | \
                              NCR5380_TCR_ASSERT_CD | \
                              NCR5380_TCR_ASSERT_IO)

static void ncr5380_internal_reset(NCR5380Core *s, bool preserve_rst,
                                   bool preserve_irq)
{
    uint8_t rst = preserve_rst ? s->icr & NCR5380_ICR_ASSERT_RST : 0;
    bool irq = preserve_irq ? s->irq : false;

    s->output_data = 0;
    s->icr = rst;
    s->mode = 0;
    s->tcr = 0;
    s->select_enable = 0;
    s->input_data = 0;
    s->test_mode = false;
    s->arbitration_in_progress = false;
    s->lost_arbitration = false;
    s->end_dma = false;
    s->drq = false;
    s->parity_error = false;
    s->irq = irq;
    s->busy_error = false;
    s->last_byte_sent = false;
    s->dma_op = NCR5380_DMA_NONE;
}

void ncr5380_core_init(NCR5380Core *s, NCR5380Variant variant)
{
    memset(s, 0, sizeof(*s));
    s->variant = variant;
}

void ncr5380_core_hard_reset(NCR5380Core *s)
{
    ncr5380_internal_reset(s, false, false);
}

static bool ncr5380_phase_matches(const NCR5380Core *s)
{
    uint8_t bus_phase = (s->bus_status &
                         (NCR5380_SR_MSG | NCR5380_SR_CD | NCR5380_SR_IO)) >> 2;

    return bus_phase == (s->tcr & 0x07);
}

uint8_t ncr5380_core_read(NCR5380Core *s, unsigned reg)
{
    uint8_t value;

    switch (reg & 7) {
    case NCR5380_REG_CURRENT_DATA:
        return s->current_data;
    case NCR5380_REG_ICR:
        value = s->icr & NCR5380_ICR_WRITABLE;
        if ((s->mode & NCR5380_MR_ARBITRATE) && s->arbitration_in_progress) {
            value |= NCR5380_ICR_AIP;
        }
        if ((s->mode & NCR5380_MR_ARBITRATE) && s->lost_arbitration) {
            value |= NCR5380_ICR_LOST_ARBITRATION;
        }
        return value;
    case NCR5380_REG_MODE:
        return s->mode;
    case NCR5380_REG_TCR:
        value = s->tcr & NCR5380_TCR_WRITABLE;
        if (s->variant == NCR5380_VARIANT_53C80 && s->last_byte_sent) {
            value |= NCR5380_TCR_LAST_BYTE_SENT;
        }
        return value;
    case NCR5380_REG_CURRENT_BUS_STATUS:
        return s->bus_status;
    case NCR5380_REG_BASR:
        value = 0;
        if (s->end_dma) {
            value |= NCR5380_BASR_END_DMA;
        }
        if (s->drq) {
            value |= NCR5380_BASR_DRQ;
        }
        if (s->parity_error) {
            value |= NCR5380_BASR_PARITY_ERROR;
        }
        if (s->irq) {
            value |= NCR5380_BASR_IRQ;
        }
        if (ncr5380_phase_matches(s)) {
            value |= NCR5380_BASR_PHASE_MATCH;
        }
        if (s->busy_error) {
            value |= NCR5380_BASR_BUSY_ERROR;
        }
        if (s->bus_atn) {
            value |= NCR5380_BASR_ATN;
        }
        if (s->bus_ack) {
            value |= NCR5380_BASR_ACK;
        }
        return value;
    case NCR5380_REG_INPUT_DATA:
        return s->input_data;
    case NCR5380_REG_RESET_PARITY_INTERRUPT:
        s->parity_error = false;
        s->irq = false;
        s->busy_error = false;
        return 0;
    default:
        return 0;
    }
}

void ncr5380_core_write(NCR5380Core *s, unsigned reg, uint8_t value)
{
    switch (reg & 7) {
    case NCR5380_REG_OUTPUT_DATA:
        s->output_data = value;
        break;
    case NCR5380_REG_ICR:
        if (value & NCR5380_ICR_ASSERT_RST) {
            /* RST resets all internal state except the IRQ latch and RST bit. */
            s->icr = NCR5380_ICR_ASSERT_RST;
            s->irq = true;
            ncr5380_internal_reset(s, true, true);
        } else {
            s->icr = value & NCR5380_ICR_WRITABLE;
            s->test_mode = !!(value & NCR5380_ICR_TEST_MODE);
            /* Bit 5 write-side DIFF ENABLE belongs to the NCR 5381. */
        }
        break;
    case NCR5380_REG_MODE:
        /* The data book requires BSY to be active before DMA mode is set. */
        if ((value & NCR5380_MR_DMA) && !(s->bus_status & NCR5380_SR_BSY)) {
            value &= ~NCR5380_MR_DMA;
        }
        if (!(value & NCR5380_MR_DMA)) {
            s->end_dma = false;
            s->drq = false;
            s->last_byte_sent = false;
            s->dma_op = NCR5380_DMA_NONE;
        }
        if (!(value & NCR5380_MR_ARBITRATE)) {
            s->arbitration_in_progress = false;
            s->lost_arbitration = false;
        }
        s->mode = value;
        break;
    case NCR5380_REG_TCR:
        s->tcr = value & NCR5380_TCR_WRITABLE;
        break;
    case NCR5380_REG_SELECT_ENABLE:
        s->select_enable = value;
        break;
    case NCR5380_REG_START_DMA_SEND:
        if (s->mode & NCR5380_MR_DMA) {
            s->dma_op = NCR5380_DMA_SEND;
            s->last_byte_sent = false;
        }
        break;
    case NCR5380_REG_START_DMA_TARGET_RECV:
        if ((s->mode & (NCR5380_MR_DMA | NCR5380_MR_TARGET)) ==
            (NCR5380_MR_DMA | NCR5380_MR_TARGET)) {
            s->dma_op = NCR5380_DMA_TARGET_RECEIVE;
        }
        break;
    case NCR5380_REG_START_DMA_INITIATOR_RECV:
        if ((s->mode & NCR5380_MR_DMA) && !(s->mode & NCR5380_MR_TARGET)) {
            s->dma_op = NCR5380_DMA_INITIATOR_RECEIVE;
        }
        break;
    }
}

void ncr5380_core_set_bus_status(NCR5380Core *s, uint8_t status)
{
    bool old_rst = !!(s->bus_status & NCR5380_SR_RST);
    bool new_rst = !!(status & NCR5380_SR_RST);
    bool old_bsy = !!(s->bus_status & NCR5380_SR_BSY);
    bool new_bsy = !!(status & NCR5380_SR_BSY);
    bool old_req = !!(s->bus_status & NCR5380_SR_REQ);
    bool new_req = !!(status & NCR5380_SR_REQ);

    s->bus_status = status;

    if (!old_rst && new_rst) {
        /* Received SCSI RST performs the same internal reset and latches IRQ. */
        s->irq = true;
        ncr5380_internal_reset(s, true, true);
    }

    if (!old_req && new_req && (s->mode & NCR5380_MR_DMA) &&
        !ncr5380_phase_matches(s)) {
        s->irq = true;
    }

    if (old_bsy && !new_bsy && (s->mode & NCR5380_MR_MONITOR_BSY)) {
        s->busy_error = true;
        s->irq = true;
        s->icr &= ~0x3f;
        s->mode &= ~NCR5380_MR_DMA;
        s->drq = false;
        s->dma_op = NCR5380_DMA_NONE;
    }
}

void ncr5380_core_set_atn_ack(NCR5380Core *s, bool atn, bool ack)
{
    s->bus_atn = atn;
    s->bus_ack = ack;
}

void ncr5380_core_set_arbitration(NCR5380Core *s, bool in_progress, bool lost)
{
    s->arbitration_in_progress = in_progress;
    s->lost_arbitration = lost;
}

void ncr5380_core_set_current_data(NCR5380Core *s, uint8_t data)
{
    s->current_data = data;
}

void ncr5380_core_set_input_data(NCR5380Core *s, uint8_t data)
{
    s->input_data = data;
}

void ncr5380_core_set_dma_request(NCR5380Core *s, bool active)
{
    s->drq = active && (s->mode & NCR5380_MR_DMA);
}

void ncr5380_core_set_end_dma(NCR5380Core *s, bool active)
{
    s->end_dma = active && (s->mode & NCR5380_MR_DMA);
    if (s->end_dma && (s->mode & NCR5380_MR_EOP_IRQ)) {
        s->irq = true;
    }
}

void ncr5380_core_set_parity_error(NCR5380Core *s, bool active)
{
    s->parity_error = active && (s->mode & NCR5380_MR_PARITY_CHECK);
    if (s->parity_error && (s->mode & NCR5380_MR_PARITY_IRQ)) {
        s->irq = true;
    }
}

void ncr5380_core_set_last_byte_sent(NCR5380Core *s, bool active)
{
    s->last_byte_sent = active;
}
