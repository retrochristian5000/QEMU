/*
 * QEMU PowerMac Awacs Screamer device support
 *
 * Copyright (c) 2016 Mark Cave-Ayland
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */
#ifndef HW_AUDIO_SCREAMER_H
#define HW_AUDIO_SCREAMER_H

#include "hw/core/sysbus.h"
#include "hw/ppc/mac_dbdma.h"
#include "qemu/audio.h"
#include "qemu/timer.h"

#define TYPE_SCREAMER "screamer"
OBJECT_DECLARE_SIMPLE_TYPE(ScreamerState, SCREAMER)

#define SCREAMER_BUFFER_SIZE 0x10000
#define SCREAMER_MMIO_REGS 6

struct ScreamerState {
    SysBusDevice parent_obj;

    MemoryRegion mem;
    qemu_irq irq;
    qemu_irq dma_tx_irq;
    qemu_irq dma_rx_irq;

    AudioBackend *audio_be;
    SWVoiceOut *voice;

    DBDMAState *dbdma;
    int tx_channel;
    int rx_channel;
    QEMUTimer *rx_timer;
    DBDMA_io *rx_io;

    uint32_t regs[SCREAMER_MMIO_REGS];
    uint16_t codec_ctrl_regs[8];
    uint32_t rate;

    uint8_t tx_buffer[SCREAMER_BUFFER_SIZE];
    uint32_t tx_rpos;
    uint32_t tx_wpos;
    uint32_t tx_count;
};

void macio_screamer_register_dma(ScreamerState *s, DBDMAState *dbdma,
                                 int tx_channel, int rx_channel);

#endif /* HW_AUDIO_SCREAMER_H */
