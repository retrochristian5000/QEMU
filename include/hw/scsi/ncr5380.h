/*
 * NCR 5380 / 53C80 SCSI protocol-controller register core
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_HW_SCSI_NCR5380_H
#define QEMU_HW_SCSI_NCR5380_H

#include <stdbool.h>
#include <stdint.h>

typedef enum NCR5380Variant {
    NCR5380_VARIANT_5380 = 0,
    NCR5380_VARIANT_53C80,
} NCR5380Variant;

typedef enum NCR5380DMAOperation {
    NCR5380_DMA_NONE = 0,
    NCR5380_DMA_SEND,
    NCR5380_DMA_TARGET_RECEIVE,
    NCR5380_DMA_INITIATOR_RECEIVE,
} NCR5380DMAOperation;

typedef struct NCR5380Core {
    NCR5380Variant variant;

    /* CPU-visible latches. Live bus inputs are kept separately below. */
    uint8_t output_data;
    uint8_t current_data;
    uint8_t icr;
    uint8_t mode;
    uint8_t tcr;
    uint8_t select_enable;
    uint8_t input_data;

    /* Current SCSI bus signals visible through register 4 and BASR. */
    uint8_t bus_status;
    bool bus_atn;
    bool bus_ack;

    /* Read-side status and internal latches. */
    bool test_mode;
    bool arbitration_in_progress;
    bool lost_arbitration;
    bool end_dma;
    bool drq;
    bool parity_error;
    bool irq;
    bool busy_error;
    bool last_byte_sent;

    NCR5380DMAOperation dma_op;
} NCR5380Core;

/* Read/write-multiplexed register addresses. */
#define NCR5380_REG_CURRENT_DATA             0
#define NCR5380_REG_OUTPUT_DATA              0
#define NCR5380_REG_ICR                      1
#define NCR5380_REG_MODE                     2
#define NCR5380_REG_TCR                      3
#define NCR5380_REG_CURRENT_BUS_STATUS       4
#define NCR5380_REG_SELECT_ENABLE            4
#define NCR5380_REG_BASR                     5
#define NCR5380_REG_START_DMA_SEND           5
#define NCR5380_REG_INPUT_DATA               6
#define NCR5380_REG_START_DMA_TARGET_RECV    6
#define NCR5380_REG_RESET_PARITY_INTERRUPT   7
#define NCR5380_REG_START_DMA_INITIATOR_RECV 7

/* Initiator Command Register: bits 6 and 5 have different read/write meanings. */
#define NCR5380_ICR_ASSERT_RST       0x80
#define NCR5380_ICR_AIP              0x40 /* read */
#define NCR5380_ICR_TEST_MODE        0x40 /* write */
#define NCR5380_ICR_LOST_ARBITRATION 0x20 /* read */
#define NCR5380_ICR_DIFF_ENABLE      0x20 /* write; NCR 5381 only */
#define NCR5380_ICR_ASSERT_ACK       0x10
#define NCR5380_ICR_ASSERT_BSY       0x08
#define NCR5380_ICR_ASSERT_SEL       0x04
#define NCR5380_ICR_ASSERT_ATN       0x02
#define NCR5380_ICR_ASSERT_DATA      0x01

#define NCR5380_MR_BLOCK_DMA         0x80
#define NCR5380_MR_TARGET            0x40
#define NCR5380_MR_PARITY_CHECK      0x20
#define NCR5380_MR_PARITY_IRQ        0x10
#define NCR5380_MR_EOP_IRQ           0x08
#define NCR5380_MR_MONITOR_BSY       0x04
#define NCR5380_MR_DMA               0x02
#define NCR5380_MR_ARBITRATE         0x01

#define NCR5380_TCR_LAST_BYTE_SENT   0x80 /* NCR 53C80 only */
#define NCR5380_TCR_ASSERT_REQ       0x08
#define NCR5380_TCR_ASSERT_MSG       0x04
#define NCR5380_TCR_ASSERT_CD        0x02
#define NCR5380_TCR_ASSERT_IO        0x01

#define NCR5380_SR_RST               0x80
#define NCR5380_SR_BSY               0x40
#define NCR5380_SR_REQ               0x20
#define NCR5380_SR_MSG               0x10
#define NCR5380_SR_CD                0x08
#define NCR5380_SR_IO                0x04
#define NCR5380_SR_SEL               0x02
#define NCR5380_SR_DBP               0x01

#define NCR5380_BASR_END_DMA         0x80
#define NCR5380_BASR_DRQ             0x40
#define NCR5380_BASR_PARITY_ERROR    0x20
#define NCR5380_BASR_IRQ             0x10
#define NCR5380_BASR_PHASE_MATCH     0x08
#define NCR5380_BASR_BUSY_ERROR      0x04
#define NCR5380_BASR_ATN             0x02
#define NCR5380_BASR_ACK             0x01

void ncr5380_core_init(NCR5380Core *s, NCR5380Variant variant);
void ncr5380_core_hard_reset(NCR5380Core *s);
uint8_t ncr5380_core_read(NCR5380Core *s, unsigned reg);
void ncr5380_core_write(NCR5380Core *s, unsigned reg, uint8_t value);

/* Inputs/events supplied by a board/SCSI-bus wrapper. */
void ncr5380_core_set_bus_status(NCR5380Core *s, uint8_t status);
void ncr5380_core_set_atn_ack(NCR5380Core *s, bool atn, bool ack);
void ncr5380_core_set_arbitration(NCR5380Core *s, bool in_progress, bool lost);
void ncr5380_core_set_current_data(NCR5380Core *s, uint8_t data);
void ncr5380_core_set_input_data(NCR5380Core *s, uint8_t data);
void ncr5380_core_set_dma_request(NCR5380Core *s, bool active);
void ncr5380_core_set_end_dma(NCR5380Core *s, bool active);
void ncr5380_core_set_parity_error(NCR5380Core *s, bool active);
void ncr5380_core_set_last_byte_sent(NCR5380Core *s, bool active);

#endif /* QEMU_HW_SCSI_NCR5380_H */
