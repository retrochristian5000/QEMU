/*
 * QEMU IDE disk and CD/DVD-ROM Emulator
 *
 * Copyright (c) 2003 Fabrice Bellard
 * Copyright (c) 2006 Openedhand Ltd.
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

#include "qemu/osdep.h"
#include "hw/core/irq.h"
#include "hw/isa/isa.h"
#include "migration/vmstate.h"
#include "qemu/error-report.h"
#include "qemu/main-loop.h"
#include "qemu/timer.h"
#include "qemu/hw-version.h"
#include "qemu/memalign.h"
#include "system/system.h"
#include "system/blockdev.h"
#include "system/dma.h"
#include "hw/block/block.h"
#include "system/block-backend.h"
#include "qapi/error.h"
#include "qemu/cutils.h"
#include "system/replay.h"
#include "system/runstate.h"
#include "ide-internal.h"
#include "trace.h"

const char *IDE_DMA_CMD_lookup[IDE_DMA__COUNT] = {
    [IDE_DMA_READ] = "DMA READ",
    [IDE_DMA_WRITE] = "DMA WRITE",
    [IDE_DMA_TRIM] = "DMA TRIM",
    [IDE_DMA_ATAPI] = "DMA ATAPI"
};

static const char *IDE_DMA_CMD_str(enum ide_dma_cmd enval)
{
    if ((unsigned)enval < IDE_DMA__COUNT) {
        return IDE_DMA_CMD_lookup[enval];
    }
    return "DMA UNKNOWN CMD";
}

static void ide_dummy_transfer_stop(IDEState *s);
static int transfer_end_table_idx(EndTransferFunc *fn);

static void ide_set_signature(IDEState *s)
{
    s->select &= ~(ATA_DEV_HS); /* clear head */
    /* put signature */
    s->nsector = 1;
    s->sector = 1;
    if (s->drive_kind == IDE_CD) {
        s->lcyl = 0x14;
        s->hcyl = 0xeb;
    } else if (s->blk) {
        s->lcyl = 0;
        s->hcyl = 0;
    } else {
        s->lcyl = 0xff;
        s->hcyl = 0xff;
    }
}

static bool ide_sect_range_ok(IDEState *s,
                              uint64_t sector, uint64_t nb_sectors)
{
    uint64_t total_sectors;

    blk_get_geometry(s->blk, &total_sectors);
    if (sector > total_sectors || nb_sectors > total_sectors - sector) {
        return false;
    }
    return true;
}

typedef struct TrimAIOCB {
    BlockAIOCB common;
    IDEState *s;
    QEMUBH *bh;
    int ret;
    QEMUIOVector *qiov;
    bool canceled;
} TrimAIOCB;

static void trim_aio_cancel(BlockAIOCB *acb)
{
    TrimAIOCB *iocb = container_of(acb, TrimAIOCB, common);

    /* Exit the loop so ide_trim_co_entry will not continue */
    iocb->canceled = true;
}

static const AIOCBInfo trim_aiocb_info = {
    .aiocb_size         = sizeof(TrimAIOCB),
    .cancel_async       = trim_aio_cancel,
};

static void ide_trim_bh_cb(void *opaque)
{
    TrimAIOCB *iocb = opaque;
    BlockBackend *blk = iocb->s->blk;

    iocb->common.cb(iocb->common.opaque, iocb->ret);

    qemu_bh_delete(iocb->bh);
    iocb->bh = NULL;
    qemu_aio_unref(iocb);

    /* Paired with blk_co_start_request in ide_trim_co_entry() */
    blk_end_request(blk);
}

static void coroutine_fn ide_trim_co_entry(void *opaque)
{
    TrimAIOCB *iocb = opaque;
    IDEState *s = iocb->s;
    size_t offset;
    int ret;

    /* Paired with blk_end_request in ide_trim_bh_cb() */
    blk_co_start_request(s->blk);

    /*
     * ATA DSM TRIM uses 8-byte descriptors in the *logical* DMA stream.
     * PCI PRD boundaries do not have to coincide with descriptor boundaries.
     * In particular, a descriptor may be split across two iovecs.
     */
    if (iocb->qiov->size % sizeof(uint64_t)) {
        block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_UNMAP);
        iocb->ret = -EINVAL;
        goto done;
    }

    for (offset = 0; offset < iocb->qiov->size; offset += sizeof(uint64_t)) {
        uint64_t raw_entry;
        uint64_t entry;
        uint64_t sector;
        uint16_t count;

        if (qemu_iovec_to_buf(iocb->qiov, offset, &raw_entry,
                              sizeof(raw_entry)) != sizeof(raw_entry)) {
            block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_UNMAP);
            iocb->ret = -EINVAL;
            goto done;
        }

        /* 6-byte LBA + 2-byte range per entry */
        entry = le64_to_cpu(raw_entry);
        sector = entry & 0x0000ffffffffffffULL;
        count = entry >> 48;

        if (count == 0) {
            continue;
        }

        if (iocb->canceled) {
            iocb->ret = -ECANCELED;
            goto done;
        }

        if (!ide_sect_range_ok(s, sector, count)) {
            block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_UNMAP);
            iocb->ret = -EINVAL;
            goto done;
        }

        block_acct_start(blk_get_stats(s->blk), &s->acct,
                         count << BDRV_SECTOR_BITS, BLOCK_ACCT_UNMAP);

        ret = blk_co_pdiscard(s->blk,
                              sector << BDRV_SECTOR_BITS,
                              count << BDRV_SECTOR_BITS,
                              BDRV_REQ_NO_QUEUE);
        if (ret >= 0) {
            block_acct_done(blk_get_stats(s->blk), &s->acct);
        } else {
            iocb->ret = ret;
            block_acct_failed(blk_get_stats(s->blk), &s->acct);
            goto done;
        }
    }

    iocb->ret = 0;
done:
    if (iocb->bh) {
        replay_bh_schedule_event(iocb->bh);
    }
}

BlockAIOCB *ide_issue_trim(
        int64_t offset, QEMUIOVector *qiov,
        BlockCompletionFunc *cb, void *cb_opaque, void *opaque)
{
    IDEState *s = opaque;
    IDEDevice *dev = s->unit ? s->bus->slave : s->bus->master;
    TrimAIOCB *iocb;
    Coroutine *co;

    iocb = blk_aio_get(&trim_aiocb_info, s->blk, cb, cb_opaque);
    iocb->s = s;
    iocb->bh = qemu_bh_new_guarded(ide_trim_bh_cb, iocb,
                                   &DEVICE(dev)->mem_reentrancy_guard);
    iocb->ret = 0;
    iocb->qiov = qiov;
    iocb->canceled = false;

    co = qemu_coroutine_create(ide_trim_co_entry, iocb);
    aio_co_enter(qemu_get_current_aio_context(), co);

    return &iocb->common;
}

void ide_abort_command(IDEState *s)
{
    s->status = READY_STAT | ERR_STAT;
    s->error = ABRT_ERR;
    ide_transfer_stop(s);
}

static void ide_set_retry(IDEState *s)
{
    s->bus->retry_unit = s->unit;
    s->bus->retry_sector_num = ide_get_sector(s);
    s->bus->retry_nsector = s->nsector;
}

static void ide_clear_retry(IDEState *s)
{
    s->bus->retry_unit = -1;
    s->bus->retry_sector_num = 0;
    s->bus->retry_nsector = 0;
}

static void ide_set_end_transfer_func(IDEState *s, EndTransferFunc *fn)
{
    int idx = transfer_end_table_idx(fn);

    assert(idx >= 0);
    s->end_transfer_func = fn;
    s->end_transfer_fn_idx = idx;
}

/* prepare data transfer and tell what to do after */
bool ide_transfer_start_norecurse(IDEState *s, uint8_t *buf, int size,
                                  EndTransferFunc *end_transfer_func)
{
    s->data_ptr = buf;
    s->data_end = buf + size;
    ide_set_retry(s);
    if (!(s->status & ERR_STAT)) {
        s->status |= DRQ_STAT;
    }
    if (!s->bus->dma->ops->pio_transfer) {
        ide_set_end_transfer_func(s, end_transfer_func);
        return false;
    }
    s->bus->dma->ops->pio_transfer(s->bus->dma);
    return true;
}

void ide_transfer_start(IDEState *s, uint8_t *buf, int size,
                        EndTransferFunc *end_transfer_func)
{
    if (ide_transfer_start_norecurse(s, buf, size, end_transfer_func)) {
        end_transfer_func(s);
    }
}

static void ide_cmd_done(IDEState *s)
{
    if (s->bus->dma->ops->cmd_done) {
        s->bus->dma->ops->cmd_done(s->bus->dma);
    }
}

static void ide_transfer_halt(IDEState *s)
{
    ide_set_end_transfer_func(s, ide_transfer_stop);
    s->data_ptr = s->io_buffer;
    s->data_end = s->io_buffer;
    s->status &= ~DRQ_STAT;
}

void ide_transfer_stop(IDEState *s)
{
    ide_transfer_halt(s);
    ide_cmd_done(s);
}

int64_t ide_get_sector(IDEState *s)
{
    int64_t sector_num;
    if (s->select & (ATA_DEV_LBA)) {
        if (s->lba48) {
            sector_num = ((int64_t)s->hob_hcyl << 40) |
                ((int64_t) s->hob_lcyl << 32) |
                ((int64_t) s->hob_sector << 24) |
                ((int64_t) s->hcyl << 16) |
                ((int64_t) s->lcyl << 8) | s->sector;
        } else {
            /* LBA28 */
            sector_num = ((s->select & (ATA_DEV_LBA_MSB)) << 24) |
                (s->hcyl << 16) | (s->lcyl << 8) | s->sector;
        }
    } else {
        /* CHS */
        sector_num = ((s->hcyl << 8) | s->lcyl) * s->heads * s->sectors +
            (s->select & (ATA_DEV_HS)) * s->sectors + (s->sector - 1);
    }

    return sector_num;
}

void ide_set_sector(IDEState *s, int64_t sector_num)
{
    unsigned int cyl, r;
    if (s->select & (ATA_DEV_LBA)) {
        if (s->lba48) {
            s->sector = sector_num;
            s->lcyl = sector_num >> 8;
            s->hcyl = sector_num >> 16;
            s->hob_sector = sector_num >> 24;
            s->hob_lcyl = sector_num >> 32;
            s->hob_hcyl = sector_num >> 40;
        } else {
            /* LBA28 */
            s->select = (s->select & ~(ATA_DEV_LBA_MSB)) |
                ((sector_num >> 24) & (ATA_DEV_LBA_MSB));
            s->hcyl = (sector_num >> 16);
            s->lcyl = (sector_num >> 8);
            s->sector = (sector_num);
        }
    } else {
        /* CHS */
        cyl = sector_num / (s->heads * s->sectors);
        r = sector_num % (s->heads * s->sectors);
        s->hcyl = cyl >> 8;
        s->lcyl = cyl;
        s->select = (s->select & ~(ATA_DEV_HS)) |
            ((r / s->sectors) & (ATA_DEV_HS));
        s->sector = (r % s->sectors) + 1;
    }
}

static void ide_rw_error(IDEState *s) {
    ide_abort_command(s);
    ide_bus_set_irq(s->bus);
}

static void ide_buffered_readv_cb(void *opaque, int ret)
{
    IDEBufferedRequest *req = opaque;
    if (!req->orphaned) {
        if (!ret) {
            assert(req->qiov.size == req->original_qiov->size);
            qemu_iovec_from_buf(req->original_qiov, 0,
                                req->qiov.local_iov.iov_base,
                                req->original_qiov->size);
        }
        req->original_cb(req->original_opaque, ret);
    }
    QLIST_REMOVE(req, list);
    qemu_vfree(qemu_iovec_buf(&req->qiov));
    g_free(req);
}

#define MAX_BUFFERED_REQS 16

BlockAIOCB *ide_buffered_readv(IDEState *s, int64_t sector_num,
                               QEMUIOVector *iov, int nb_sectors,
                               BlockCompletionFunc *cb, void *opaque)
{
    BlockAIOCB *aioreq;
    IDEBufferedRequest *req;
    int c = 0;

    QLIST_FOREACH(req, &s->buffered_requests, list) {
        c++;
    }
    if (c > MAX_BUFFERED_REQS) {
        return blk_abort_aio_request(s->blk, cb, opaque, -EIO);
    }

    req = g_new0(IDEBufferedRequest, 1);
    req->original_qiov = iov;
    req->original_cb = cb;
    req->original_opaque = opaque;
    qemu_iovec_init_buf(&req->qiov, blk_blockalign(s->blk, iov->size),
                        iov->size);

    aioreq = blk_aio_preadv(s->blk, sector_num << BDRV_SECTOR_BITS,
                            &req->qiov, 0, ide_buffered_readv_cb, req);

    QLIST_INSERT_HEAD(&s->buffered_requests, req, list);
    return aioreq;
}

/**
 * Cancel all pending DMA requests.
 * Any buffered DMA requests are instantly canceled,
 * but any pending unbuffered DMA requests must be waited on.
 */
void ide_cancel_dma_sync(IDEState *s)
{
    IDEBufferedRequest *req;

    /* First invoke the callbacks of all buffered requests
     * and flag those requests as orphaned. Ideally there
     * are no unbuffered (Scatter Gather DMA Requests or
     * write requests) pending and we can avoid to drain. */
    QLIST_FOREACH(req, &s->buffered_requests, list) {
        if (!req->orphaned) {
            trace_ide_cancel_dma_sync_buffered(req->original_cb, req);
            req->original_cb(req->original_opaque, -ECANCELED);
        }
        req->orphaned = true;
    }

    /*
     * We can't cancel Scatter Gather DMA in the middle of the
     * operation or a partial (not full) DMA transfer would reach
     * the storage so we wait for completion instead (we behave
     * like if the DMA was completed by the time the guest trying
     * to cancel dma with bmdma_cmd_writeb with BM_CMD_START not
     * set).
     *
     * In the future we'll be able to safely cancel the I/O if the
     * whole DMA operation will be submitted to disk with a single
     * aio operation with preadv/pwritev.
     *
     * Note: s->bus->dma->aiocb might belong to the adjacent IDEState,
     * so we have to drain both drives to get it cleared.
     */
    if (s->bus->dma->aiocb) {
        trace_ide_cancel_dma_sync_remaining();
        for (int i = 0; i < 2; i++) {
            if (s->bus->ifs[i].blk) {
                blk_drain(s->bus->ifs[i].blk);
            }
        }
        assert(s->bus->dma->aiocb == NULL);
    }
}

static void ide_sector_read(IDEState *s);

static void ide_sector_read_cb(void *opaque, int ret)
{
    IDEState *s = opaque;
    int n;

    s->pio_aiocb = NULL;
    s->status &= ~BUSY_STAT;

    if (ret != 0) {
        if (ide_handle_rw_error(s, -ret, IDE_RETRY_PIO |
                                IDE_RETRY_READ)) {
            return;
        }
    }

    block_acct_done(blk_get_stats(s->blk), &s->acct);

    n = s->nsector;
    if (n > s->req_nb_sectors) {
        n = s->req_nb_sectors;
    }

    ide_set_sector(s, ide_get_sector(s) + n);
    s->nsector -= n;
    /* Allow the guest to read the io_buffer */
    ide_transfer_start(s, s->io_buffer, n * BDRV_SECTOR_SIZE, ide_sector_read);
    ide_bus_set_irq(s->bus);
}

static void ide_sector_read(IDEState *s)
{
    int64_t sector_num;
    int n;

    s->status = READY_STAT | SEEK_STAT;
    s->error = 0; /* not needed by IDE spec, but needed by Windows */
    sector_num = ide_get_sector(s);
    n = s->nsector;
    ide_set_retry(s);

    if (n == 0) {
        ide_transfer_stop(s);
        return;
    }

    s->status |= BUSY_STAT;

    if (n > s->req_nb_sectors) {
        n = s->req_nb_sectors;
    }

    trace_ide_sector_read(sector_num, n);

    if (!ide_sect_range_ok(s, sector_num, n)) {
        ide_rw_error(s);
        block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_READ);
        return;
    }

    qemu_iovec_init_buf(&s->qiov, s->io_buffer, n * BDRV_SECTOR_SIZE);

    block_acct_start(blk_get_stats(s->blk), &s->acct,
                     n * BDRV_SECTOR_SIZE, BLOCK_ACCT_READ);
    s->pio_aiocb = ide_buffered_readv(s, sector_num, &s->qiov, n,
                                      ide_sector_read_cb, s);
}

void ide_dma_buf_commit(IDEState *s, uint32_t tx_bytes)
{
    if (s->bus->dma->ops->commit_buf) {
        s->bus->dma->ops->commit_buf(s->bus->dma, tx_bytes);
    }
    s->io_buffer_offset += tx_bytes;
    qemu_sglist_destroy(&s->sg);
}

void ide_set_inactive(IDEState *s, bool more)
{
    s->bus->dma->aiocb = NULL;
    ide_clear_retry(s);
    if (s->bus->dma->ops->set_inactive) {
        s->bus->dma->ops->set_inactive(s->bus->dma, more);
    }
    ide_cmd_done(s);
}

void ide_dma_error(IDEState *s)
{
    ide_dma_buf_commit(s, 0);
    ide_abort_command(s);
    ide_set_inactive(s, false);
    ide_bus_set_irq(s->bus);
}

int ide_handle_rw_error(IDEState *s, int error, int op)
{
    bool is_read = (op & IDE_RETRY_READ) != 0;
    BlockErrorAction action = blk_get_error_action(s->blk, is_read, error);

    if (action == BLOCK_ERROR_ACTION_STOP) {
        assert(s->bus->retry_unit == s->unit);
        s->bus->error_status = op;
    } else if (action == BLOCK_ERROR_ACTION_REPORT) {
        block_acct_failed(blk_get_stats(s->blk), &s->acct);
        if (IS_IDE_RETRY_DMA(op)) {
            ide_dma_error(s);
        } else if (IS_IDE_RETRY_ATAPI(op)) {
            ide_atapi_io_error(s, -error);
        } else {
            ide_rw_error(s);
        }
    }
    blk_error_action(s->blk, action, is_read, error);
    return action != BLOCK_ERROR_ACTION_IGNORE;
}

static void ide_dma_cb(void *opaque, int ret)
{
    IDEState *s = opaque;
    int n;
    int64_t sector_num;
    uint64_t offset;
    bool stay_active = false;
    int32_t prep_size = 0;

    if (ret == -EINVAL) {
        ide_dma_error(s);
        return;
    }

    if (ret < 0) {
        if (ide_handle_rw_error(s, -ret, ide_dma_cmd_to_retry(s->dma_cmd))) {
            s->bus->dma->aiocb = NULL;
            ide_dma_buf_commit(s, 0);
            return;
        }
    }

    if (s->io_buffer_size > s->nsector * 512) {
        /*
         * The PRDs were longer than needed for this request.
         * The Active bit must remain set after the request completes.
         */
        n = s->nsector;
        stay_active = true;
    } else {
        n = s->io_buffer_size >> 9;
    }

    sector_num = ide_get_sector(s);
    if (n > 0) {
        assert(n * 512 == s->sg.size);
        ide_dma_buf_commit(s, s->sg.size);
        sector_num += n;
        ide_set_sector(s, sector_num);
        s->nsector -= n;
    }

    /* end of transfer ? */
    if (s->nsector == 0) {
        s->status = READY_STAT | SEEK_STAT;
        ide_bus_set_irq(s->bus);
        goto eot;
    }

    /* launch next transfer */
    n = s->nsector;
    s->io_buffer_index = 0;
    s->io_buffer_size = n * 512;
    prep_size = s->bus->dma->ops->prepare_buf(s->bus->dma, s->io_buffer_size);
    if (prep_size < 0) {
        ide_dma_error(s);
        return;
    }
    /* If prepare_buf() succeeds, it must respect the limit. */
    assert(prep_size <= n * 512);

    /*
     * Now prep_size stores the number of bytes in the sglist, and
     * s->io_buffer_size stores the number of bytes described by the PRDs.
     */

    if (prep_size < n * 512) {
        /*
         * The PRDs are too short for this request. Error condition!
         * Reset the Active bit and don't raise the interrupt.
         */
        s->status = READY_STAT | SEEK_STAT;
        ide_dma_buf_commit(s, 0);
        goto eot;
    }

    trace_ide_dma_cb(s, sector_num, n, IDE_DMA_CMD_str(s->dma_cmd));

    if ((s->dma_cmd == IDE_DMA_READ || s->dma_cmd == IDE_DMA_WRITE) &&
        !ide_sect_range_ok(s, sector_num, n)) {
        ide_dma_error(s);
        block_acct_invalid(blk_get_stats(s->blk), s->acct.type);
        return;
    }

    offset = sector_num << BDRV_SECTOR_BITS;
    switch (s->dma_cmd) {
    case IDE_DMA_READ:
        s->bus->dma->aiocb = dma_blk_read(s->blk, &s->sg, offset,
                                          BDRV_SECTOR_SIZE, ide_dma_cb, s);
        break;
    case IDE_DMA_WRITE:
        s->bus->dma->aiocb = dma_blk_write(s->blk, &s->sg, offset,
                                           BDRV_SECTOR_SIZE, ide_dma_cb, s);
        break;
    case IDE_DMA_TRIM:
        s->bus->dma->aiocb = dma_blk_io(&s->sg, offset, BDRV_SECTOR_SIZE,
                                        ide_issue_trim, s, ide_dma_cb, s,
                                        DMA_DIRECTION_TO_DEVICE);
        break;
    default:
        abort();
    }
    return;

eot:
    if (s->dma_cmd == IDE_DMA_READ || s->dma_cmd == IDE_DMA_WRITE) {
        block_acct_done(blk_get_stats(s->blk), &s->acct);
    }
    ide_set_inactive(s, stay_active);
}

static void ide_sector_start_dma(IDEState *s, enum ide_dma_cmd dma_cmd)
{
    s->status = READY_STAT | SEEK_STAT | DRQ_STAT;
    s->io_buffer_size = 0;
    s->dma_cmd = dma_cmd;

    switch (dma_cmd) {
    case IDE_DMA_READ:
        block_acct_start(blk_get_stats(s->blk), &s->acct,
                         s->nsector * BDRV_SECTOR_SIZE, BLOCK_ACCT_READ);
        break;
    case IDE_DMA_WRITE:
        block_acct_start(blk_get_stats(s->blk), &s->acct,
                         s->nsector * BDRV_SECTOR_SIZE, BLOCK_ACCT_WRITE);
        break;
    default:
        break;
    }

    ide_start_dma(s, ide_dma_cb);
}

void ide_start_dma(IDEState *s, BlockCompletionFunc *cb)
{
    s->io_buffer_index = 0;
    ide_set_retry(s);
    if (s->bus->dma->ops->start_dma) {
        s->bus->dma->ops->start_dma(s->bus->dma, s, cb);
    }
}

static void ide_sector_write(IDEState *s);

static void ide_sector_write_timer_cb(void *opaque)
{
    IDEState *s = opaque;
    ide_bus_set_irq(s->bus);
}

static void ide_sector_write_cb(void *opaque, int ret)
{
    IDEState *s = opaque;
    int n;

    s->pio_aiocb = NULL;
    s->status &= ~BUSY_STAT;

    if (ret != 0) {
        if (ide_handle_rw_error(s, -ret, IDE_RETRY_PIO)) {
            return;
        }
    }

    block_acct_done(blk_get_stats(s->blk), &s->acct);

    n = s->nsector;
    if (n > s->req_nb_sectors) {
        n = s->req_nb_sectors;
    }
    s->nsector -= n;

    ide_set_sector(s, ide_get_sector(s) + n);
    if (s->nsector == 0) {
        /* no more sectors to write */
        ide_transfer_stop(s);
    } else {
        int n1 = s->nsector;
        if (n1 > s->req_nb_sectors) {
            n1 = s->req_nb_sectors;
        }
        ide_transfer_start(s, s->io_buffer, n1 * BDRV_SECTOR_SIZE,
                           ide_sector_write);
    }

    if (s->win2k_install_hack && ((++s->irq_count % 16) == 0)) {
        /* It seems there is a bug in the Windows 2000 installer HDD
           IDE driver which fills the disk with empty logs when the
           IDE write IRQ comes too early. This hack tries to correct
           that at the expense of slower write performances. Use this
           option _only_ to install Windows 2000. You must disable it
           for normal use. */
        timer_mod(s->sector_write_timer, qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL) +
                  (NANOSECONDS_PER_SECOND / 1000));
    } else {
        ide_bus_set_irq(s->bus);
    }
}

static void ide_sector_write(IDEState *s)
{
    int64_t sector_num;
    int n;

    s->status = READY_STAT | SEEK_STAT | BUSY_STAT;
    sector_num = ide_get_sector(s);

    n = s->nsector;
    if (n > s->req_nb_sectors) {
        n = s->req_nb_sectors;
    }

    trace_ide_sector_write(sector_num, n);

    if (!ide_sect_range_ok(s, sector_num, n)) {
        ide_rw_error(s);
        block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_WRITE);
        return;
    }

    qemu_iovec_init_buf(&s->qiov, s->io_buffer, n * BDRV_SECTOR_SIZE);

    block_acct_start(blk_get_stats(s->blk), &s->acct,
                     n * BDRV_SECTOR_SIZE, BLOCK_ACCT_WRITE);
    s->pio_aiocb = blk_aio_pwritev(s->blk, sector_num << BDRV_SECTOR_BITS,
                                   &s->qiov, 0, ide_sector_write_cb, s);
}

static void ide_flush_cb(void *opaque, int ret)
{
    IDEState *s = opaque;

    s->pio_aiocb = NULL;

    if (ret < 0) {
        /* XXX: What sector number to set here? */
        if (ide_handle_rw_error(s, -ret, IDE_RETRY_FLUSH)) {
            return;
        }
    }

    if (s->blk) {
        block_acct_done(blk_get_stats(s->blk), &s->acct);
    }
    s->status = READY_STAT | SEEK_STAT;
    ide_cmd_done(s);
    ide_bus_set_irq(s->bus);
}

static void ide_flush_cache(IDEState *s)
{
    if (s->blk == NULL) {
        ide_flush_cb(s, 0);
        return;
    }

    s->status |= BUSY_STAT;
    ide_set_retry(s);
    block_acct_start(blk_get_stats(s->blk), &s->acct, 0, BLOCK_ACCT_FLUSH);
    s->pio_aiocb = blk_aio_flush(s->blk, ide_flush_cb, s);
}

static void ide_cfata_metadata_inquiry(IDEState *s)
{
    uint16_t *p;
    uint32_t spd;

    p = (uint16_t *) s->io_buffer;
    memset(p, 0, 0x200);
    spd = ((s->mdata_size - 1) >> 9) + 1;

    ide_put_le16(p + 0, 0x0001);                    /* Data format revision */
    ide_put_le16(p + 1, 0x0000);                    /* Media property: silicon */
    ide_put_le16(p + 2, s->media_changed);          /* Media status */
    ide_put_le16(p + 3, s->mdata_size & 0xffff);    /* Capacity in bytes (low) */
    ide_put_le16(p + 4, s->mdata_size >> 16);       /* Capacity in bytes (high) */
    ide_put_le16(p + 5, spd & 0xffff);              /* Sectors per device (low) */
    ide_put_le16(p + 6, spd >> 16);                 /* Sectors per device (high) */
}

static void ide_cfata_metadata_read(IDEState *s)
{
    uint16_t *p;

    if (((s->hcyl << 16) | s->lcyl) << 9 > s->mdata_size + 2) {
        s->status = ERR_STAT;
        s->error = ABRT_ERR;
        return;
    }

    p = (uint16_t *) s->io_buffer;
    memset(p, 0, 0x200);

    ide_put_le16(p + 0, s->media_changed);          /* Media status */
    memcpy(p + 1, s->mdata_storage + (((s->hcyl << 16) | s->lcyl) << 9),
                    MIN(MIN(s->mdata_size - (((s->hcyl << 16) | s->lcyl) << 9),
                                    s->nsector << 9), 0x200 - 2));
}

static void ide_cfata_metadata_write(IDEState *s)
{
    if (((s->hcyl << 16) | s->lcyl) << 9 > s->mdata_size + 2) {
        s->status = ERR_STAT;
        s->error = ABRT_ERR;
        return;
    }

    s->media_changed = 0;

    memcpy(s->mdata_storage + (((s->hcyl << 16) | s->lcyl) << 9),
                    s->io_buffer + 2,
                    MIN(MIN(s->mdata_size - (((s->hcyl << 16) | s->lcyl) << 9),
                                    s->nsector << 9), 0x200 - 2));
}

static void ide_cmd_lba48_transform(IDEState *s, int lba48)
{
    s->lba48 = lba48;

    /* handle the 'magic' 0 nsector count conversion here. to avoid
     * fiddling with the rest of the read logic, we just store the
     * full sector count in ->nsector and ignore ->hob_nsector from now
     */
    if (!s->lba48) {
        if (!s->nsector)
            s->nsector = 256;
    } else {
        if (!s->nsector && !s->hob_nsector)
            s->nsector = 65536;
        else {
            int lo = s->nsector;
            int hi = s->hob_nsector;

            s->nsector = (hi << 8) | lo;
        }
    }
}

static void ide_reset(IDEState *s)
{
    trace_ide_reset(s);

    if (s->pio_aiocb) {
        blk_aio_cancel(s->pio_aiocb);
        s->pio_aiocb = NULL;
    }

    if (s->reset_reverts) {
        s->reset_reverts = false;
        s->heads         = s->drive_heads;
        s->sectors       = s->drive_sectors;
    }
    if (s->drive_kind == IDE_CFATA)
        s->mult_sectors = 0;
    else
        s->mult_sectors = MAX_MULT_SECTORS;
    /* ide regs */
    s->feature = 0;
    s->error = 0;
    s->nsector = 0;
    s->sector = 0;
    s->lcyl = 0;
    s->hcyl = 0;

    /* lba48 */
    s->hob_feature = 0;
    s->hob_sector = 0;
    s->hob_nsector = 0;
    s->hob_lcyl = 0;
    s->hob_hcyl = 0;

    s->select = (ATA_DEV_ALWAYS_ON);
    s->status = READY_STAT | SEEK_STAT;

    s->lba48 = 0;

    ide_atapi_reset_state(s);
    /* ATA DMA state */
    s->io_buffer_size = 0;
    s->req_nb_sectors = 0;

    ide_set_signature(s);
    /* init the transfer handler so that 0xffff is returned on data
       accesses */
    s->end_transfer_func = ide_dummy_transfer_stop;
    ide_dummy_transfer_stop(s);
    s->media_changed = 0;
}

static bool cmd_nop(IDEState *s, uint8_t cmd)
{
    return true;
}

static bool cmd_data_set_management(IDEState *s, uint8_t cmd)
{
    switch (s->feature) {
    case DSM_TRIM:
        if (s->blk) {
            ide_sector_start_dma(s, IDE_DMA_TRIM);
            return false;
        }
        break;
    }

    ide_abort_command(s);
    return true;
}

static bool cmd_identify(IDEState *s, uint8_t cmd)
{
    if (s->blk && s->drive_kind != IDE_CD) {
        if (s->drive_kind != IDE_CFATA) {
            ide_identify(s);
        } else {
            ide_cfata_identify(s);
        }
        s->status = READY_STAT | SEEK_STAT;
        ide_transfer_start(s, s->io_buffer, 512, ide_transfer_stop);
        ide_bus_set_irq(s->bus);
        return false;
    } else {
        if (s->drive_kind == IDE_CD) {
            ide_set_signature(s);
        }
        ide_abort_command(s);
    }

    return true;
}

static bool cmd_verify(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_VERIFY_EXT);

    /* do sector number check ? */
    ide_cmd_lba48_transform(s, lba48);

    return true;
}

static bool cmd_set_multiple_mode(IDEState *s, uint8_t cmd)
{
    if (s->drive_kind == IDE_CFATA && s->nsector == 0) {
        /* Disable Read and Write Multiple */
        s->mult_sectors = 0;
    } else if ((s->nsector & 0xff) != 0 &&
        ((s->nsector & 0xff) > MAX_MULT_SECTORS ||
         (s->nsector & (s->nsector - 1)) != 0)) {
        ide_abort_command(s);
    } else {
        s->mult_sectors = s->nsector & 0xff;
    }

    return true;
}

static bool cmd_read_multiple(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_MULTREAD_EXT);

    if (!s->blk || !s->mult_sectors) {
        ide_abort_command(s);
        return true;
    }

    ide_cmd_lba48_transform(s, lba48);
    s->req_nb_sectors = s->mult_sectors;
    ide_sector_read(s);
    return false;
}

static bool cmd_write_multiple(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_MULTWRITE_EXT);
    int n;

    if (!s->blk || !s->mult_sectors) {
        ide_abort_command(s);
        return true;
    }

    ide_cmd_lba48_transform(s, lba48);

    s->req_nb_sectors = s->mult_sectors;
    n = MIN(s->nsector, s->req_nb_sectors);

    s->status = SEEK_STAT | READY_STAT;
    ide_transfer_start(s, s->io_buffer, 512 * n, ide_sector_write);

    s->media_changed = 1;

    return false;
}

static bool cmd_read_pio(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_READ_EXT);

    if (s->drive_kind == IDE_CD) {
        ide_set_signature(s); /* odd, but ATA4 8.27.5.2 requires it */
        ide_abort_command(s);
        return true;
    }

    if (!s->blk) {
        ide_abort_command(s);
        return true;
    }

    ide_cmd_lba48_transform(s, lba48);
    s->req_nb_sectors = 1;
    ide_sector_read(s);

    return false;
}

static bool cmd_write_pio(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_WRITE_EXT);

    if (!s->blk) {
        ide_abort_command(s);
        return true;
    }

    ide_cmd_lba48_transform(s, lba48);

    s->req_nb_sectors = 1;
    s->status = SEEK_STAT | READY_STAT;
    ide_transfer_start(s, s->io_buffer, 512, ide_sector_write);

    s->media_changed = 1;

    return false;
}

static bool cmd_read_dma(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_READDMA_EXT);

    if (!s->blk) {
        ide_abort_command(s);
        return true;
    }

    ide_cmd_lba48_transform(s, lba48);
    ide_sector_start_dma(s, IDE_DMA_READ);

    return false;
}

static bool cmd_write_dma(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_WRITEDMA_EXT);

    if (!s->blk) {
        ide_abort_command(s);
        return true;
    }

    ide_cmd_lba48_transform(s, lba48);
    ide_sector_start_dma(s, IDE_DMA_WRITE);

    s->media_changed = 1;

    return false;
}

static bool cmd_flush_cache(IDEState *s, uint8_t cmd)
{
    ide_flush_cache(s);
    return false;
}

static bool cmd_seek(IDEState *s, uint8_t cmd)
{
    /* XXX: Check that seek is within bounds */
    return true;
}

static bool cmd_read_native_max(IDEState *s, uint8_t cmd)
{
    bool lba48 = (cmd == WIN_READ_NATIVE_MAX_EXT);

    /* Refuse if no sectors are addressable (e.g. medium not inserted) */
    if (s->nb_sectors == 0) {
        ide_abort_command(s);
    } else {
        /*
         * Save the active drive parameters, which may have been
         * limited from their native counterparts by, e.g., INITIALIZE
         * DEVICE PARAMETERS or SET MAX ADDRESS.
         */
        const int aheads = s->heads;
        const int asectors = s->sectors;

        s->heads = s->drive_heads;
        s->sectors = s->drive_sectors;

        ide_cmd_lba48_transform(s, lba48);
        ide_set_sector(s, s->nb_sectors - 1);

        s->heads = aheads;
        s->sectors = asectors;
    }

    return true;
}

static bool cmd_check_power_mode(IDEState *s, uint8_t cmd)
{
    s->nsector = 0xff; /* device active or idle */
    return true;
}

/* INITIALIZE DEVICE PARAMETERS */
static bool cmd_specify(IDEState *s, uint8_t cmd)
{
    if (s->blk && s->drive_kind != IDE_CD) {
        s->heads = (s->select & (ATA_DEV_HS)) + 1;
        s->sectors = s->nsector;
        ide_bus_set_irq(s->bus);
    } else {
        ide_abort_command(s);
    }

    return true;
}

static bool cmd_set_features(IDEState *s, uint8_t cmd)
{
    uint16_t *identify_data;

    if (!s->blk) {
        ide_abort_command(s);
        return true;
    }

    /* XXX: valid for CDROM ? */
    switch (s->feature) {
    case 0x01: /* 8-bit I/O enable (CompactFlash) */
    case 0x81: /* 8-bit I/O disable (CompactFlash) */
        if (s->drive_kind != IDE_CFATA) {
            goto abort_cmd;
        }
        s->io8 = !(s->feature & 0x80);
        return true;
    case 0x02: /* write cache enable */
        blk_set_enable_write_cache(s->blk, true);
        identify_data = (uint16_t *)s->identify_data;
        ide_put_le16(identify_data + 85, (1 << 14) | (1 << 5) | 1);
        return true;
    case 0x82: /* write cache disable */
        blk_set_enable_write_cache(s->blk, false);
        identify_data = (uint16_t *)s->identify_data;
        ide_put_le16(identify_data + 85, (1 << 14) | 1);
        ide_flush_cache(s);
        return false;
    case 0xcc: /* reverting to power-on defaults enable */
        s->reset_reverts = true;
        return true;
    case 0x66: /* reverting to power-on defaults disable */
        s->reset_reverts = false;
        return true;
    case 0xaa: /* read look-ahead enable */
    case 0x55: /* read look-ahead disable */
    case 0x05: /* set advanced power management mode */
    case 0x85: /* disable advanced power management mode */
    case 0x69: /* NOP */
    case 0x67: /* NOP */
    case 0x96: /* NOP */
    case 0x9a: /* NOP */
    case 0x42: /* enable Automatic Acoustic Mode */
    case 0xc2: /* disable Automatic Acoustic Mode */
        return true;
    case 0x03: /* set transfer mode */
        {
            uint8_t val = s->nsector & 0x07;
            identify_data = (uint16_t *)s->identify_data;

            switch (s->nsector >> 3) {
            case 0x00: /* pio default */
            case 0x01: /* pio mode */
                ide_put_le16(identify_data + 62, 0x07);
                ide_put_le16(identify_data + 63, 0x07);
                ide_put_le16(identify_data + 88, 0x3f);
                break;
            case 0x02: /* single word dma mode */
                ide_put_le16(identify_data + 62, 0x07 | (1 << (val + 8)));
                ide_put_le16(identify_data + 63, 0x07);
                ide_put_le16(identify_data + 88, 0x3f);
                break;
            case 0x04: /* mdma mode */
                ide_put_le16(identify_data + 62, 0x07);
                ide_put_le16(identify_data + 63, 0x07 | (1 << (val + 8)));
                ide_put_le16(identify_data + 88, 0x3f);
                break;
            case 0x08: /* udma mode */
                ide_put_le16(identify_data + 62, 0x07);
                ide_put_le16(identify_data + 63, 0x07);
                ide_put_le16(identify_data + 88, 0x3f | (1 << (val + 8)));
                break;
            default:
                goto abort_cmd;
            }
            return true;
        }
    }

abort_cmd:
    ide_abort_command(s);
    return true;
}


/* Shared signature and diagnostic status, without command notification. */
static void ide_set_diagnostic_status(IDEState *s)
{
    /*
     * Clear the device register per the ATA (v6) specification,
     * because ide_set_signature does not clear LBA or drive bits.
     */
    s->select = (ATA_DEV_ALWAYS_ON);
    ide_set_signature(s);

    if (s->drive_kind == IDE_CD) {
        s->status = 0; /* ATAPI spec (v6) section 9.10 defines packet
                        * devices to return a clear status register
                        * with READY_STAT *not* set. */
        s->error = 0x01;
    } else {
        s->status = READY_STAT | SEEK_STAT;
        /* The bits of the error register are not as usual for this command!
         * They are part of the regular output (this is why ERR_STAT isn't set)
         * Device 0 passed, Device 1 passed or not present. */
        s->error = 0x01;
    }
}

/* EXECUTE DEVICE DIAGNOSTIC */
static bool cmd_exec_dev_diagnostic(IDEState *s, uint8_t cmd)
{
    ide_set_diagnostic_status(s);
    if (s->drive_kind != IDE_CD) {
        ide_bus_set_irq(s->bus);
    }
    return false;
}

/*** CF-ATA commands ***/

static bool cmd_cfa_req_ext_error_code(IDEState *s, uint8_t cmd)
{
    s->error = 0x09;    /* miscellaneous error */
    s->status = READY_STAT | SEEK_STAT;
    ide_bus_set_irq(s->bus);

    return false;
}

static bool cmd_cfa_erase_sectors(IDEState *s, uint8_t cmd)
{
    /* WIN_SECURITY_FREEZE_LOCK has the same ID as CFA_WEAR_LEVEL and is
     * required for Windows 8 to work with AHCI */

    if (cmd == CFA_WEAR_LEVEL) {
        s->nsector = 0;
    }

    if (cmd == CFA_ERASE_SECTORS) {
        s->media_changed = 1;
    }

    return true;
}

static bool cmd_cfa_translate_sector(IDEState *s, uint8_t cmd)
{
    s->status = READY_STAT | SEEK_STAT;

    memset(s->io_buffer, 0, 0x200);
    s->io_buffer[0x00] = s->hcyl;                   /* Cyl MSB */
    s->io_buffer[0x01] = s->lcyl;                   /* Cyl LSB */
    s->io_buffer[0x02] = s->select;                 /* Head */
    s->io_buffer[0x03] = s->sector;                 /* Sector */
    s->io_buffer[0x04] = ide_get_sector(s) >> 16;   /* LBA MSB */
    s->io_buffer[0x05] = ide_get_sector(s) >> 8;    /* LBA */
    s->io_buffer[0x06] = ide_get_sector(s) >> 0;    /* LBA LSB */
    s->io_buffer[0x13] = 0x00;                      /* Erase flag */
    s->io_buffer[0x18] = 0x00;                      /* Hot count */
    s->io_buffer[0x19] = 0x00;                      /* Hot count */
    s->io_buffer[0x1a] = 0x01;                      /* Hot count */

    ide_transfer_start(s, s->io_buffer, 0x200, ide_transfer_stop);
    ide_bus_set_irq(s->bus);

    return false;
}

static bool cmd_cfa_access_metadata_storage(IDEState *s, uint8_t cmd)
{
    switch (s->feature) {
    case 0x02:  /* Inquiry Metadata Storage */
        ide_cfata_metadata_inquiry(s);
        break;
    case 0x03:  /* Read Metadata Storage */
        ide_cfata_metadata_read(s);
        break;
    case 0x04:  /* Write Metadata Storage */
        ide_cfata_metadata_write(s);
        break;
    default:
        ide_abort_command(s);
        return true;
    }

    ide_transfer_start(s, s->io_buffer, 0x200, ide_transfer_stop);
    s->status = 0x00; /* NOTE: READY is _not_ set */
    ide_bus_set_irq(s->bus);

    return false;
}

static bool cmd_ibm_sense_condition(IDEState *s, uint8_t cmd)
{
    switch (s->feature) {
    case 0x01:  /* sense temperature in device */
        s->nsector = 0x50;      /* +20 C */
        break;
    default:
        ide_abort_command(s);
        return true;
    }

    return true;
}


#define HD_OK (1u << IDE_HD)
#define CD_OK (1u << IDE_CD)
#define CFA_OK (1u << IDE_CFATA)
#define HD_CFA_OK (HD_OK | CFA_OK)
#define ALL_OK (HD_OK | CD_OK | CFA_OK)

/* Set the Disk Seek Completed status bit during completion */
#define SET_DSC (1u << 8)

/* See ACS-2 T13/2015-D Table B.2 Command codes */
static const struct {
    /* Returns true if the completion code should be run */
    bool (*handler)(IDEState *s, uint8_t cmd);
    int flags;
} ide_cmd_table[0x100] = {
    /* NOP not implemented, mandatory for CD */
    [CFA_REQ_EXT_ERROR_CODE]      = { cmd_cfa_req_ext_error_code, CFA_OK },
    [WIN_DSM]                     = { cmd_data_set_management, HD_CFA_OK },
    [WIN_DEVICE_RESET]            = { ide_atapi_cmd_device_reset, CD_OK },
    [WIN_RECAL]                   = { cmd_nop, HD_CFA_OK | SET_DSC},
    [WIN_READ]                    = { cmd_read_pio, ALL_OK },
    [WIN_READ_ONCE]               = { cmd_read_pio, HD_CFA_OK },
    [WIN_READ_EXT]                = { cmd_read_pio, HD_CFA_OK },
    [WIN_READDMA_EXT]             = { cmd_read_dma, HD_CFA_OK },
    [WIN_READ_NATIVE_MAX_EXT]     = { cmd_read_native_max, HD_CFA_OK | SET_DSC },
    [WIN_MULTREAD_EXT]            = { cmd_read_multiple, HD_CFA_OK },
    [WIN_WRITE]                   = { cmd_write_pio, HD_CFA_OK },
    [WIN_WRITE_ONCE]              = { cmd_write_pio, HD_CFA_OK },
    [WIN_WRITE_EXT]               = { cmd_write_pio, HD_CFA_OK },
    [WIN_WRITEDMA_EXT]            = { cmd_write_dma, HD_CFA_OK },
    [CFA_WRITE_SECT_WO_ERASE]     = { cmd_write_pio, CFA_OK },
    [WIN_MULTWRITE_EXT]           = { cmd_write_multiple, HD_CFA_OK },
    [WIN_WRITE_VERIFY]            = { cmd_write_pio, HD_CFA_OK },
    [WIN_VERIFY]                  = { cmd_verify, HD_CFA_OK | SET_DSC },
    [WIN_VERIFY_ONCE]             = { cmd_verify, HD_CFA_OK | SET_DSC },
    [WIN_VERIFY_EXT]              = { cmd_verify, HD_CFA_OK | SET_DSC },
    [WIN_SEEK]                    = { cmd_seek, HD_CFA_OK | SET_DSC },
    [CFA_TRANSLATE_SECTOR]        = { cmd_cfa_translate_sector, CFA_OK },
    [WIN_DIAGNOSE]                = { cmd_exec_dev_diagnostic, ALL_OK },
    [WIN_SPECIFY]                 = { cmd_specify, HD_CFA_OK | SET_DSC },
    [WIN_STANDBYNOW2]             = { cmd_nop, HD_CFA_OK },
    [WIN_IDLEIMMEDIATE2]          = { cmd_nop, HD_CFA_OK },
    [WIN_STANDBY2]                = { cmd_nop, HD_CFA_OK },
    [WIN_SETIDLE2]                = { cmd_nop, HD_CFA_OK },
    [WIN_CHECKPOWERMODE2]         = { cmd_check_power_mode, HD_CFA_OK | SET_DSC },
    [WIN_SLEEPNOW2]               = { cmd_nop, HD_CFA_OK },
    [WIN_PACKETCMD]               = { ide_atapi_cmd_packet, CD_OK },
    [WIN_PIDENTIFY]               = { ide_atapi_cmd_identify_packet, CD_OK },
    [WIN_SMART]                   = { ide_ata_cmd_smart, HD_CFA_OK | SET_DSC },
    [CFA_ACCESS_METADATA_STORAGE] = { cmd_cfa_access_metadata_storage, CFA_OK },
    [CFA_ERASE_SECTORS]           = { cmd_cfa_erase_sectors, CFA_OK | SET_DSC },
    [WIN_MULTREAD]                = { cmd_read_multiple, HD_CFA_OK },
    [WIN_MULTWRITE]               = { cmd_write_multiple, HD_CFA_OK },
    [WIN_SETMULT]                 = { cmd_set_multiple_mode, HD_CFA_OK | SET_DSC },
    [WIN_READDMA]                 = { cmd_read_dma, HD_CFA_OK },
    [WIN_READDMA_ONCE]            = { cmd_read_dma, HD_CFA_OK },
    [WIN_WRITEDMA]                = { cmd_write_dma, HD_CFA_OK },
    [WIN_WRITEDMA_ONCE]           = { cmd_write_dma, HD_CFA_OK },
    [CFA_WRITE_MULTI_WO_ERASE]    = { cmd_write_multiple, CFA_OK },
    [WIN_STANDBYNOW1]             = { cmd_nop, HD_CFA_OK },
    [WIN_IDLEIMMEDIATE]           = { cmd_nop, HD_CFA_OK },
    [WIN_STANDBY]                 = { cmd_nop, HD_CFA_OK },
    [WIN_SETIDLE1]                = { cmd_nop, HD_CFA_OK },
    [WIN_CHECKPOWERMODE1]         = { cmd_check_power_mode, HD_CFA_OK | SET_DSC },
    [WIN_SLEEPNOW1]               = { cmd_nop, HD_CFA_OK },
    [WIN_FLUSH_CACHE]             = { cmd_flush_cache, ALL_OK },
    [WIN_FLUSH_CACHE_EXT]         = { cmd_flush_cache, HD_CFA_OK },
    [WIN_IDENTIFY]                = { cmd_identify, ALL_OK },
    [WIN_SETFEATURES]             = { cmd_set_features, ALL_OK | SET_DSC },
    [IBM_SENSE_CONDITION]         = { cmd_ibm_sense_condition, CFA_OK | SET_DSC },
    [CFA_WEAR_LEVEL]              = { cmd_cfa_erase_sectors, HD_CFA_OK | SET_DSC },
    [WIN_READ_NATIVE_MAX]         = { cmd_read_native_max, HD_CFA_OK | SET_DSC },
};

static bool ide_cmd_permitted(IDEState *s, uint32_t cmd)
{
    return cmd < ARRAY_SIZE(ide_cmd_table)
        && (ide_cmd_table[cmd].flags & (1u << s->drive_kind));
}

void ide_bus_exec_cmd(IDEBus *bus, uint32_t val)
{
    IDEState *s;
    bool complete;

    s = ide_bus_active_if(bus);
    trace_ide_bus_exec_cmd(bus, s, val);

    /* ignore commands to non existent slave */
    if (s != bus->ifs && !s->blk) {
        return;
    }

    /* Only RESET is allowed while BSY and/or DRQ are set,
     * and only to ATAPI devices. */
    if (s->status & (BUSY_STAT|DRQ_STAT)) {
        if (val != WIN_DEVICE_RESET || s->drive_kind != IDE_CD) {
            return;
        }
    }

    if (!ide_cmd_permitted(s, val)) {
        ide_abort_command(s);
        ide_bus_set_irq(s->bus);
        return;
    }

    s->status = READY_STAT | BUSY_STAT;
    s->error = 0;
    s->io_buffer_offset = 0;

    complete = ide_cmd_table[val].handler(s, val);
    if (complete) {
        s->status &= ~BUSY_STAT;
        assert(!!s->error == !!(s->status & ERR_STAT));

        if ((ide_cmd_table[val].flags & SET_DSC) && !s->error) {
            s->status |= SEEK_STAT;
        }

        ide_cmd_done(s);
        ide_bus_set_irq(s->bus);
    }
}

/*
 * Shared reset ordering: cancel transfers before resetting registers.
 * Callers own the protocol-specific status and diagnostic response.
 */
void ide_reset_transfers(IDEState *s)
{
    /* Halt PIO (Via register state); PIO BH remains scheduled. */
    ide_transfer_halt(s);

    /* Cancel DMA -- may drain block device and invoke callbacks */
    ide_cancel_dma_sync(s);

    /* Cancel PIO callback, reset registers/signature, etc */
    ide_reset(s);
}

static void ide_perform_srst(IDEState *s)
{
    s->status |= BUSY_STAT;
    ide_reset_transfers(s);

    /* SRST sets the diagnostic signature without a command-completion IRQ. */
    ide_set_diagnostic_status(s);
}

static void ide_bus_perform_srst(void *opaque)
{
    IDEBus *bus = opaque;
    IDEState *s;
    int i;

    /* Cancellation can run completion callbacks; keep INTRQ inactive. */
    bus->cmd |= IDE_CTRL_RESET;
    for (i = 0; i < 2; i++) {
        s = &bus->ifs[i];
        ide_perform_srst(s);
    }
    qemu_irq_lower(bus->irq);

    bus->cmd &= ~IDE_CTRL_RESET;
}

void ide_ctrl_write(void *opaque, uint32_t addr, uint32_t val)
{
    IDEBus *bus = opaque;
    IDEState *s;
    int i;

    trace_ide_ctrl_write(addr, val, bus);

    /* Device0 and Device1 each have their own control register,
     * but QEMU models it as just one register in the controller. */
    if (!(bus->cmd & IDE_CTRL_RESET) && (val & IDE_CTRL_RESET)) {
        qemu_irq_lower(bus->irq);
        for (i = 0; i < 2; i++) {
            s = &bus->ifs[i];
            s->status |= BUSY_STAT;
        }
        replay_bh_schedule_oneshot_event(qemu_get_aio_context(),
                                         ide_bus_perform_srst, bus);
    }

    bus->cmd = val;
}

static void ide_dummy_transfer_stop(IDEState *s)
{
    s->data_ptr = s->io_buffer;
    s->data_end = s->io_buffer;
    s->io_buffer[0] = 0xff;
    s->io_buffer[1] = 0xff;
    s->io_buffer[2] = 0xff;
    s->io_buffer[3] = 0xff;
}

void ide_bus_reset(IDEBus *bus)
{
    /* pending async DMA - needs the IDEState before it is reset */
    if (bus->dma->aiocb) {
        trace_ide_bus_reset_aio();
        blk_aio_cancel(bus->dma->aiocb);
        bus->dma->aiocb = NULL;
    }

    bus->unit = 0;
    bus->cmd = 0;
    ide_reset(&bus->ifs[0]);
    ide_reset(&bus->ifs[1]);
    /* Reset also clears the high-order-byte selector and interrupt output. */
    bus->cmd &= ~IDE_CTRL_HOB;
    qemu_irq_lower(bus->irq);

    /* reset dma provider too */
    if (bus->dma->ops->reset) {
        bus->dma->ops->reset(bus->dma);
    }
}

int ide_init_drive(IDEState *s, IDEDevice *dev, IDEDriveKind kind, Error **errp)
{
    uint64_t nb_sectors;

    s->blk = dev->conf.blk;
    s->drive_kind = kind;

    blk_get_geometry(s->blk, &nb_sectors);
    s->win2k_install_hack = dev->win2k_install_hack;
    s->cylinders = dev->conf.cyls;
    s->heads = s->drive_heads = dev->conf.heads;
    s->sectors = s->drive_sectors = dev->conf.secs;
    s->chs_trans = dev->chs_trans;
    s->nb_sectors = nb_sectors;
    s->wwn = dev->wwn;
    /* The SMART values should be preserved across power cycles
       but they aren't.  */
    s->smart_enabled = 1;
    s->smart_autosave = 1;
    s->smart_errors = 0;
    s->smart_selftest_count = 0;
    if (kind == IDE_CD) {
        blk_set_dev_ops(s->blk, &ide_cd_block_ops, s);
    } else {
        if (!blk_is_inserted(s->blk)) {
            error_setg(errp, "Device needs media, but drive is empty");
            return -1;
        }
        if (!blk_is_writable(s->blk)) {
            error_setg(errp, "Can't use a read-only drive");
            return -1;
        }
        blk_set_dev_ops(s->blk, &ide_hd_block_ops, s);
    }
    if (dev->serial) {
        pstrcpy(s->drive_serial_str, sizeof(s->drive_serial_str), dev->serial);
    } else {
        snprintf(s->drive_serial_str, sizeof(s->drive_serial_str),
                 "QM%05d", s->drive_serial);
    }
    if (dev->model) {
        pstrcpy(s->drive_model_str, sizeof(s->drive_model_str), dev->model);
    } else {
        switch (kind) {
        case IDE_CD:
            strcpy(s->drive_model_str, "QEMU DVD-ROM");
            break;
        case IDE_CFATA:
            strcpy(s->drive_model_str, "QEMU MICRODRIVE");
            break;
        default:
            strcpy(s->drive_model_str, "QEMU HARDDISK");
            break;
        }
    }

    if (dev->version) {
        pstrcpy(s->version, sizeof(s->version), dev->version);
    } else {
        pstrcpy(s->version, sizeof(s->version), QEMU_HW_VERSION);
    }

    ide_reset(s);
    blk_iostatus_enable(s->blk);
    return 0;
}

static void ide_init1(IDEBus *bus, int unit)
{
    static int drive_serial = 1;
    IDEState *s = &bus->ifs[unit];

    s->bus = bus;
    s->unit = unit;
    s->drive_serial = drive_serial++;
    /* we need at least 2k alignment for accessing CDROMs using O_DIRECT */
    s->io_buffer_total_len = IDE_DMA_BUF_SECTORS*512 + 4;
    s->io_buffer = qemu_memalign(2048, s->io_buffer_total_len);
    memset(s->io_buffer, 0, s->io_buffer_total_len);

    s->smart_selftest_data = blk_blockalign(s->blk, 512);
    memset(s->smart_selftest_data, 0, 512);

    s->sector_write_timer = timer_new_ns(QEMU_CLOCK_VIRTUAL,
                                           ide_sector_write_timer_cb, s);
}

static int ide_nop_int(const IDEDMA *dma, bool is_write)
{
    return 0;
}

static void ide_nop(const IDEDMA *dma)
{
}

static int32_t ide_nop_int32(const IDEDMA *dma, int32_t l)
{
    return 0;
}

static const IDEDMAOps ide_dma_nop_ops = {
    .prepare_buf    = ide_nop_int32,
    .restart_dma    = ide_nop,
    .rw_buf         = ide_nop_int,
};

static void ide_restart_dma(IDEState *s, enum ide_dma_cmd dma_cmd)
{
    s->unit = s->bus->retry_unit;
    ide_set_sector(s, s->bus->retry_sector_num);
    s->nsector = s->bus->retry_nsector;
    s->bus->dma->ops->restart_dma(s->bus->dma);
    s->io_buffer_size = 0;
    s->dma_cmd = dma_cmd;
    ide_start_dma(s, ide_dma_cb);
}

static void ide_restart_bh(void *opaque)
{
    IDEBus *bus = opaque;
    IDEState *s;
    bool is_read;
    int error_status;

    qemu_bh_delete(bus->bh);
    bus->bh = NULL;

    error_status = bus->error_status;
    if (bus->error_status == 0) {
        return;
    }

    s = ide_bus_active_if(bus);
    is_read = (bus->error_status & IDE_RETRY_READ) != 0;

    /* The error status must be cleared before resubmitting the request: The
     * request may fail again, and this case can only be distinguished if the
     * called function can set a new error status. */
    bus->error_status = 0;

    /* The HBA has generically asked to be kicked on retry */
    if (error_status & IDE_RETRY_HBA) {
        if (s->bus->dma->ops->restart) {
            s->bus->dma->ops->restart(s->bus->dma);
        }
    } else if (IS_IDE_RETRY_DMA(error_status)) {
        if (error_status & IDE_RETRY_TRIM) {
            ide_restart_dma(s, IDE_DMA_TRIM);
        } else {
            ide_restart_dma(s, is_read ? IDE_DMA_READ : IDE_DMA_WRITE);
        }
    } else if (IS_IDE_RETRY_PIO(error_status)) {
        if (is_read) {
            ide_sector_read(s);
        } else {
            ide_sector_write(s);
        }
    } else if (error_status & IDE_RETRY_FLUSH) {
        ide_flush_cache(s);
    } else if (IS_IDE_RETRY_ATAPI(error_status)) {
        assert(s->end_transfer_func == ide_atapi_cmd);
        ide_atapi_dma_restart(s);
    } else {
        abort();
    }
}

static void ide_restart_cb(void *opaque, bool running, RunState state)
{
    IDEBus *bus = opaque;

    if (!running)
        return;

    if (!bus->bh) {
        bus->bh = qemu_bh_new(ide_restart_bh, bus);
        qemu_bh_schedule(bus->bh);
    }
}

void ide_bus_register_restart_cb(IDEBus *bus)
{
    if (bus->dma->ops->restart_dma) {
        bus->vmstate = qemu_add_vm_change_state_handler(ide_restart_cb, bus);
    }
}

static IDEDMA ide_dma_nop = {
    .ops = &ide_dma_nop_ops,
    .aiocb = NULL,
};

void ide_bus_init_output_irq(IDEBus *bus, qemu_irq irq_out)
{
    int i;

    for(i = 0; i < 2; i++) {
        ide_init1(bus, i);
        ide_reset(&bus->ifs[i]);
    }
    bus->irq = irq_out;
    bus->dma = &ide_dma_nop;
}

void ide_bus_set_irq(IDEBus *bus)
{
    if (!(bus->cmd & (IDE_CTRL_DISABLE_IRQ | IDE_CTRL_RESET))) {
        qemu_irq_raise(bus->irq);
    }
}

void ide_exit(IDEState *s)
{
    timer_free(s->sector_write_timer);
    qemu_vfree(s->smart_selftest_data);
    qemu_vfree(s->io_buffer);
}

static bool is_identify_set(void *opaque, int version_id)
{
    IDEState *s = opaque;

    return s->identify_set != 0;
}

static EndTransferFunc *transfer_end_table[] = {
    [IDE_TRANSFER_END_SECTOR_READ] = ide_sector_read,
    [IDE_TRANSFER_END_SECTOR_WRITE] = ide_sector_write,
    [IDE_TRANSFER_END_STOP] = ide_transfer_stop,
    [IDE_TRANSFER_END_ATAPI_REPLY] = ide_atapi_cmd_reply_end,
    [IDE_TRANSFER_END_ATAPI_CMD] = ide_atapi_cmd,
    [IDE_TRANSFER_END_DUMMY_STOP] = ide_dummy_transfer_stop,
};

static int transfer_end_table_idx(EndTransferFunc *fn)
{
    int i;

    for (i = 0; i < ARRAY_SIZE(transfer_end_table); i++)
        if (transfer_end_table[i] == fn)
            return i;

    return -1;
}

static int ide_drive_post_load(void *opaque, int version_id)
{
    IDEState *s = opaque;

    if (s->blk && s->identify_set) {
        blk_set_enable_write_cache(s->blk, !!(s->identify_data[85] & (1 << 5)));
    }
    return 0;
}

static int ide_drive_pio_post_load(void *opaque, int version_id)
{
    IDEState *s = opaque;

    if (s->end_transfer_fn_idx >= ARRAY_SIZE(transfer_end_table)) {
        return -EINVAL;
    }
    s->end_transfer_func = transfer_end_table[s->end_transfer_fn_idx];
    s->data_ptr = s->io_buffer + s->cur_io_buffer_offset;
    s->data_end = s->data_ptr + s->cur_io_buffer_len;
    s->atapi_dma = s->feature & 1; /* as per ide_atapi_cmd_packet */

    return 0;
}

static int ide_drive_pio_pre_save(void *opaque)
{
    IDEState *s = opaque;
    int idx;

    s->cur_io_buffer_offset = s->data_ptr - s->io_buffer;
    s->cur_io_buffer_len = s->data_end - s->data_ptr;

    idx = transfer_end_table_idx(s->end_transfer_func);
    if (idx == -1) {
        fprintf(stderr, "%s: invalid end_transfer_func for DRQ_STAT\n",
                        __func__);
        s->end_transfer_fn_idx = 2;
    } else {
        s->end_transfer_fn_idx = idx;
    }

    return 0;
}

static bool ide_drive_pio_state_needed(void *opaque)
{
    IDEState *s = opaque;

    return ((s->status & DRQ_STAT) != 0)
        || (s->bus->error_status & IDE_RETRY_PIO);
}

static bool ide_error_needed(void *opaque)
{
    IDEBus *bus = opaque;

    return (bus->error_status != 0);
}

static const VMStateDescription vmstate_ide_drive_pio_state = {
    .name = "ide_drive/pio_state",
    .version_id = 1,
    .minimum_version_id = 1,
    .pre_save = ide_drive_pio_pre_save,
    .post_load = ide_drive_pio_post_load,
    .needed = ide_drive_pio_state_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_INT32(req_nb_sectors, IDEState),
        VMSTATE_VARRAY_INT32(io_buffer, IDEState, io_buffer_total_len, 1,
                             vmstate_info_uint8, uint8_t),
        VMSTATE_INT32(cur_io_buffer_offset, IDEState),
        VMSTATE_INT32(cur_io_buffer_len, IDEState),
        VMSTATE_UINT8(end_transfer_fn_idx, IDEState),
        VMSTATE_INT32(elementary_transfer_size, IDEState),
        VMSTATE_INT32(packet_transfer_size, IDEState),
        VMSTATE_END_OF_LIST()
    }
};

const VMStateDescription vmstate_ide_drive = {
    .name = "ide_drive",
    .version_id = 3,
    .minimum_version_id = 0,
    .post_load = ide_drive_post_load,
    .fields = (const VMStateField[]) {
        VMSTATE_INT32(mult_sectors, IDEState),
        VMSTATE_INT32(identify_set, IDEState),
        VMSTATE_BUFFER_TEST(identify_data, IDEState, is_identify_set),
        VMSTATE_UINT8(feature, IDEState),
        VMSTATE_UINT8(error, IDEState),
        VMSTATE_UINT32(nsector, IDEState),
        VMSTATE_UINT8(sector, IDEState),
        VMSTATE_UINT8(lcyl, IDEState),
        VMSTATE_UINT8(hcyl, IDEState),
        VMSTATE_UINT8(hob_feature, IDEState),
        VMSTATE_UINT8(hob_sector, IDEState),
        VMSTATE_UINT8(hob_nsector, IDEState),
        VMSTATE_UINT8(hob_lcyl, IDEState),
        VMSTATE_UINT8(hob_hcyl, IDEState),
        VMSTATE_UINT8(select, IDEState),
        VMSTATE_UINT8(status, IDEState),
        VMSTATE_UINT8(lba48, IDEState),
        VMSTATE_UINT8(sense_key, IDEState),
        VMSTATE_UINT8(asc, IDEState),
        VMSTATE_UINT8_V(cdrom_changed, IDEState, 3),
        VMSTATE_END_OF_LIST()
    },
    .subsections = (const VMStateDescription * const []) {
        &vmstate_ide_drive_pio_state,
        &vmstate_ide_tray_state,
        &vmstate_ide_atapi_gesn_state,
        NULL
    }
};

static const VMStateDescription vmstate_ide_error_status = {
    .name ="ide_bus/error",
    .version_id = 2,
    .minimum_version_id = 1,
    .needed = ide_error_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_INT32(error_status, IDEBus),
        VMSTATE_INT64_V(retry_sector_num, IDEBus, 2),
        VMSTATE_UINT32_V(retry_nsector, IDEBus, 2),
        VMSTATE_UINT8_V(retry_unit, IDEBus, 2),
        VMSTATE_END_OF_LIST()
    }
};

const VMStateDescription vmstate_ide_bus = {
    .name = "ide_bus",
    .version_id = 1,
    .minimum_version_id = 1,
    .fields = (const VMStateField[]) {
        VMSTATE_UINT8(cmd, IDEBus),
        VMSTATE_UINT8(unit, IDEBus),
        VMSTATE_END_OF_LIST()
    },
    .subsections = (const VMStateDescription * const []) {
        &vmstate_ide_error_status,
        NULL
    }
};

void ide_drive_get(DriveInfo **hd, int n)
{
    int i;

    for (i = 0; i < n; i++) {
        hd[i] = drive_get_by_index(IF_IDE, i);
    }
}
