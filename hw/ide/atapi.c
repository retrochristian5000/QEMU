/*
 * QEMU ATAPI Emulation
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
#include "qemu/cutils.h"
#include "hw/scsi/scsi.h"
#include "hw/block/dvdrom.h"
#include "hw/block/mmc-rom.h"
#include "hw/block/cdrom-sector.h"
#include "system/block-backend.h"
#include "migration/vmstate.h"
#include "scsi/constants.h"
#include "ide-internal.h"
#include "trace.h"

/* Packet-device state is reset even in unused IDE slots for compatibility. */
void ide_atapi_reset_state(IDEState *s)
{
    s->sense_key = 0;
    s->asc = 0;
    s->cdrom_changed = 0;
    s->packet_transfer_size = 0;
    s->elementary_transfer_size = 0;
    s->io_buffer_index = 0;
    s->cd_sector_size = 0;
    s->atapi_dma = 0;
    s->tray_locked = 0;
    s->tray_open = 0;
}

bool ide_atapi_cmd_device_reset(IDEState *s, uint8_t cmd)
{
    ide_reset_transfers(s);

    /* RESET: ATA8-ACS3 7.10.4 "Normal Outputs";
     * ATA8-ACS3 Table 184 "Device Signatures for Normal Output" */
    s->status = 0x00;

    /* Do not overwrite status register */
    return false;
}

/* Packet-device identification and removable-media notifications. */
static void ide_atapi_identify(IDEState *s)
{
    uint16_t *p;

    p = (uint16_t *)s->identify_data;
    if (s->identify_set) {
        goto fill_buffer;
    }
    memset(p, 0, sizeof(s->identify_data));

    /* Removable CDROM, 50us response, 12 byte packets */
    ide_put_le16(p + 0, (2 << 14) | (5 << 8) | (1 << 7) | (2 << 5) | (0 << 0));
    ide_padstr((char *)(p + 10), s->drive_serial_str, 20); /* serial number */
    ide_put_le16(p + 20, 3); /* buffer type */
    ide_put_le16(p + 21, 512); /* cache size in sectors */
    ide_put_le16(p + 22, 4); /* ecc bytes */
    ide_padstr((char *)(p + 23), s->version, 8); /* firmware version */
    ide_padstr((char *)(p + 27), s->drive_model_str, 40); /* model */
    if (s->atapi_unswapped_model) {
        /* Early NEC CDR-260 firmware returns the model in wire order. */
        for (int i = 27; i < 47; i++) {
            p[i] = bswap16(p[i]);
        }
    }
    ide_put_le16(p + 48, 1); /* dword I/O (XXX: should not be set on CDROM) */
#ifdef USE_DMA_CDROM
    ide_put_le16(p + 49, 1 << 9 | 1 << 8); /* DMA and LBA supported */
    ide_put_le16(p + 53, 7); /* words 64-70, 54-58, 88 valid */
    ide_put_le16(p + 62, 7);  /* single word dma0-2 supported */
    ide_put_le16(p + 63, 7);  /* mdma0-2 supported */
#else
    ide_put_le16(p + 49, 1 << 9); /* LBA supported, no DMA */
    ide_put_le16(p + 53, 3); /* words 64-70, 54-58 valid */
    ide_put_le16(p + 63, 0x103); /* DMA modes XXX: may be incorrect */
#endif
    ide_put_le16(p + 64, 3); /* pio3-4 supported */
    ide_put_le16(p + 65, 0xb4); /* minimum DMA multiword tx cycle time */
    ide_put_le16(p + 66, 0xb4); /* recommended DMA multiword tx cycle time */
    ide_put_le16(p + 67, 0x12c); /* minimum PIO cycle time without flow control */
    ide_put_le16(p + 68, 0xb4); /* minimum PIO cycle time with IORDY flow control */

    ide_put_le16(p + 71, 30); /* in ns */
    ide_put_le16(p + 72, 30); /* in ns */

    if (s->ncq_queues) {
        ide_put_le16(p + 75, s->ncq_queues - 1);
        /* NCQ supported */
        ide_put_le16(p + 76, (1 << 8));
    }

    ide_put_le16(p + 80, 0x1e); /* support up to ATA/ATAPI-4 */
    if (s->wwn) {
        ide_put_le16(p + 84, (1 << 8)); /* supports WWN for words 108-111 */
        ide_put_le16(p + 87, (1 << 8)); /* WWN enabled */
    }

#ifdef USE_DMA_CDROM
    ide_put_le16(p + 88, 0x3f | (1 << 13)); /* udma5 set and supported */
#endif

    if (s->wwn) {
        /* LE 16-bit words 111-108 contain 64-bit World Wide Name */
        ide_put_le16(p + 108, s->wwn >> 48);
        ide_put_le16(p + 109, s->wwn >> 32);
        ide_put_le16(p + 110, s->wwn >> 16);
        ide_put_le16(p + 111, s->wwn);
    }

    s->identify_set = 1;

fill_buffer:
    memcpy(s->io_buffer, p, sizeof(s->identify_data));
}

bool ide_atapi_cmd_identify_packet(IDEState *s, uint8_t cmd)
{
    ide_atapi_identify(s);
    s->status = READY_STAT | SEEK_STAT;
    ide_transfer_start(s, s->io_buffer, 512, ide_transfer_stop);
    ide_bus_set_irq(s->bus);
    return false;
}

bool ide_atapi_cmd_packet(IDEState *s, uint8_t cmd)
{
    /* overlapping commands not supported */
    if (s->feature & 0x02) {
        ide_abort_command(s);
        return true;
    }

    s->status = READY_STAT | SEEK_STAT;
    s->atapi_dma = s->feature & 1;
    if (s->atapi_dma) {
        s->dma_cmd = IDE_DMA_ATAPI;
    }
    s->nsector = 1;
    ide_transfer_start(s, s->io_buffer, ATAPI_PACKET_SIZE,
                       ide_atapi_cmd);
    return false;
}

/* called when the inserted state of the media has changed */
static void ide_cd_change_cb(void *opaque, bool load, Error **errp)
{
    IDEState *s = opaque;
    uint64_t nb_sectors;

    s->tray_open = !load;
    blk_get_geometry(s->blk, &nb_sectors);
    s->nb_sectors = nb_sectors;

    /*
     * First indicate to the guest that a CD has been removed.  That's
     * done on the next command the guest sends us.
     *
     * Then we set UNIT_ATTENTION, by which the guest will
     * detect a new CD in the drive.  See ide_atapi_cmd() for details.
     */
    s->cdrom_changed = 1;
    s->events.new_media = true;
    s->events.eject_request = false;
    ide_bus_set_irq(s->bus);
}

static void ide_cd_eject_request_cb(void *opaque, bool force)
{
    IDEState *s = opaque;

    s->events.eject_request = true;
    if (force) {
        s->tray_locked = false;
    }
    ide_bus_set_irq(s->bus);
}

static bool ide_cd_is_tray_open(void *opaque)
{
    return ((IDEState *)opaque)->tray_open;
}

static bool ide_cd_is_medium_locked(void *opaque)
{
    return ((IDEState *)opaque)->tray_locked;
}

const BlockDevOps ide_cd_block_ops = {
    .change_media_cb = ide_cd_change_cb,
    .eject_request_cb = ide_cd_eject_request_cb,
    .is_tray_open = ide_cd_is_tray_open,
    .is_medium_locked = ide_cd_is_medium_locked,
};

#define ATAPI_SECTOR_BITS (2 + BDRV_SECTOR_BITS)
#define ATAPI_SECTOR_SIZE (1 << ATAPI_SECTOR_BITS)

static void ide_atapi_cmd_read_dma_cb(void *opaque, int ret);

static void padstr8(uint8_t *buf, int buf_size, const char *src)
{
    int i;
    for(i = 0; i < buf_size; i++) {
        if (*src)
            buf[i] = *src++;
        else
            buf[i] = ' ';
    }
}

static inline int media_present(IDEState *s)
{
    return !s->tray_open && s->nb_sectors > 0;
}

/* XXX: DVDs that could fit on a CD will be reported as a CD */
static inline int media_is_dvd(IDEState *s)
{
    return (media_present(s) && s->nb_sectors > CD_MAX_SECTORS);
}

static inline int media_is_cd(IDEState *s)
{
    return (media_present(s) && s->nb_sectors <= CD_MAX_SECTORS);
}

/* Expand packed Mode 1 payloads without overwriting unread sectors. */
static void cd_expand_raw_sectors(IDEState *s, int nsec)
{
    for (int i = nsec - 1; i >= 0; i--) {
        memmove(s->io_buffer + i * 2352 + 16,
                s->io_buffer + i * ATAPI_SECTOR_SIZE, ATAPI_SECTOR_SIZE);
        cdrom_synthesize_mode1_sector(s->io_buffer + i * 2352, s->lba + i);
    }
}

static void cd_read_sector_cb(void *opaque, int ret)
{
    IDEState *s = opaque;
    int et = s->elementary_transfer_size;
    int skip = s->io_buffer_index;
    int nsec = DIV_ROUND_UP(skip + et, s->cd_sector_size);
    uint8_t *buf;

    trace_cd_read_sector_cb(s->lba, ret);

    if (ret < 0) {
        block_acct_failed(blk_get_stats(s->blk), &s->acct);
        ide_atapi_io_error(s, ret);
        return;
    }

    block_acct_done(blk_get_stats(s->blk), &s->acct);

    if (s->cd_sector_size == 2352) {
        cd_expand_raw_sectors(s, nsec);
    }

    s->status &= ~BUSY_STAT;

    s->nsector = (s->nsector & ~7) | ATAPI_INT_REASON_IO;
    s->lcyl = et & 0xff;
    s->hcyl = (et >> 8) & 0xff;
    ide_bus_set_irq(s->bus);

    /* a boundary sector shared with the next burst is re-read there */
    buf = s->io_buffer + skip;
    s->packet_transfer_size -= et;
    s->lba += (skip + et) / s->cd_sector_size;
    s->io_buffer_index = (skip + et) % s->cd_sector_size;
    s->elementary_transfer_size = 0;

    if (ide_transfer_start_norecurse(s, buf, et, ide_atapi_cmd_reply_end)) {
        ide_atapi_cmd_reply_end(s);
    }
}

/*
 * Read the whole elementary transfer (one DRQ burst) in a single async
 * request. No read is issued mid-burst, so unlike the old synchronous
 * rebuffer it cannot deadlock against a concurrent drain.
 */
static int cd_read_sector(IDEState *s)
{
    int et = s->elementary_transfer_size;
    int skip = s->io_buffer_index;
    int nsec = DIV_ROUND_UP(skip + et, s->cd_sector_size);

    if (s->cd_sector_size != 2048 && s->cd_sector_size != 2352) {
        block_acct_invalid(blk_get_stats(s->blk), BLOCK_ACCT_READ);
        return -EINVAL;
    }

    /* a burst is bounded by the byte count limit, so it fits io_buffer */
    assert(nsec * s->cd_sector_size <= s->io_buffer_total_len);

    /*
     * Read the payload packed at the front of io_buffer; the 2352 raw case is
     * unpacked into place on completion.
     */
    qemu_iovec_init_buf(&s->qiov, s->io_buffer, nsec * ATAPI_SECTOR_SIZE);

    trace_cd_read_sector(s->lba);

    block_acct_start(blk_get_stats(s->blk), &s->acct,
                     nsec * ATAPI_SECTOR_SIZE, BLOCK_ACCT_READ);

    ide_buffered_readv(s, (int64_t)s->lba << 2, &s->qiov, nsec * 4,
                       cd_read_sector_cb, s);

    s->status |= BUSY_STAT;
    return 0;
}

void ide_atapi_cmd_ok(IDEState *s)
{
    s->error = 0;
    s->status = READY_STAT | SEEK_STAT;
    s->nsector = (s->nsector & ~7) | ATAPI_INT_REASON_IO | ATAPI_INT_REASON_CD;
    ide_transfer_stop(s);
    ide_bus_set_irq(s->bus);
}

void ide_atapi_cmd_error(IDEState *s, int sense_key, int asc)
{
    trace_ide_atapi_cmd_error(s, sense_key, asc);
    s->error = sense_key << 4;
    s->status = READY_STAT | ERR_STAT;
    s->nsector = (s->nsector & ~7) | ATAPI_INT_REASON_IO | ATAPI_INT_REASON_CD;
    s->sense_key = sense_key;
    s->asc = asc;
    ide_transfer_stop(s);
    ide_bus_set_irq(s->bus);
}

void ide_atapi_io_error(IDEState *s, int ret)
{
    /* XXX: handle more errors */
    if (ret == -ENOMEDIUM) {
        ide_atapi_cmd_error(s, NOT_READY,
                            ASC_MEDIUM_NOT_PRESENT);
    } else {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_LOGICAL_BLOCK_OOR);
    }
}

static uint16_t atapi_byte_count_limit(IDEState *s)
{
    uint16_t bcl;

    bcl = s->lcyl | (s->hcyl << 8);
    if (bcl == 0xffff) {
        return 0xfffe;
    }
    return bcl;
}

/* Complete a packet-level ATA abort, including the completion interrupt. */
static void atapi_abort_bcl(IDEState *s)
{
    s->nsector = (s->nsector & ~7) | ATAPI_INT_REASON_IO | ATAPI_INT_REASON_CD;
    ide_abort_command(s);
    ide_bus_set_irq(s->bus);
}

/* A non-final PIO phase must contain a positive, even number of bytes. */
static int atapi_pio_phase_size(IDEState *s)
{
    int limit = atapi_byte_count_limit(s);

    trace_ide_atapi_cmd_reply_end_bcl(s, limit);
    if (s->packet_transfer_size > limit) {
        return limit & ~1;
    }
    return s->packet_transfer_size;
}

/* The whole ATAPI transfer logic is handled in this function */
void ide_atapi_cmd_reply_end(IDEState *s)
{
    int size, ret;

    trace_ide_atapi_cmd_reply_end(s, s->packet_transfer_size,
                                  s->elementary_transfer_size,
                                  s->io_buffer_index);

    if (s->lba != -1 && s->packet_transfer_size > 0) {
        size = atapi_pio_phase_size(s);
        if (!size) {
            atapi_abort_bcl(s);
            return;
        }
        s->elementary_transfer_size = size;
        ret = cd_read_sector(s);
        if (ret < 0) {
            ide_atapi_io_error(s, ret);
        }
        return;
    }

    while (s->packet_transfer_size > 0) {
        size = atapi_pio_phase_size(s);
        if (!size) {
            atapi_abort_bcl(s);
            return;
        }
        /* a new transfer is needed */
        s->nsector = (s->nsector & ~7) | ATAPI_INT_REASON_IO;
        s->lcyl = size & 0xff;
        s->hcyl = size >> 8;
        s->elementary_transfer_size = size;
        trace_ide_atapi_cmd_reply_end_new(s, s->status);
        ide_bus_set_irq(s->bus);

        s->packet_transfer_size -= size;
        s->elementary_transfer_size -= size;
        s->io_buffer_index += size;
        assert(size <= s->io_buffer_total_len);
        assert(s->io_buffer_index <= s->io_buffer_total_len);

        /* Some adapters process PIO data right away.  In that case, we need
         * to avoid mutual recursion between ide_transfer_start
         * and ide_atapi_cmd_reply_end.
         */
        if (!ide_transfer_start_norecurse(s,
                                          s->io_buffer + s->io_buffer_index - size,
                                          size, ide_atapi_cmd_reply_end)) {
            return;
        }
    }

    /* end of transfer */
    trace_ide_atapi_cmd_reply_end_eot(s, s->status);
    ide_atapi_cmd_ok(s);
    ide_bus_set_irq(s->bus);
}

/* send a reply of 'size' bytes in s->io_buffer to an ATAPI command */
static void ide_atapi_cmd_reply(IDEState *s, int size, int max_size)
{
    if (size > max_size)
        size = max_size;
    s->lba = -1; /* no sector read */
    s->packet_transfer_size = size;
    s->io_buffer_size = size;    /* dma: send the reply data as one chunk */
    s->elementary_transfer_size = 0;

    if (s->atapi_dma) {
        block_acct_start(blk_get_stats(s->blk), &s->acct, size,
                         BLOCK_ACCT_READ);
        s->status = READY_STAT | SEEK_STAT | DRQ_STAT;
        ide_start_dma(s, ide_atapi_cmd_read_dma_cb);
    } else {
        s->status = READY_STAT | SEEK_STAT;
        s->io_buffer_index = 0;
        ide_atapi_cmd_reply_end(s);
    }
}

/* start a CD-ROM read command */
static void ide_atapi_cmd_read_pio(IDEState *s, int lba, int nb_sectors,
                                   int sector_size)
{
    assert(0 <= lba && lba < (s->nb_sectors >> 2));

    s->lba = lba;
    s->packet_transfer_size = nb_sectors * sector_size;
    s->elementary_transfer_size = 0;
    s->io_buffer_index = 0;
    s->cd_sector_size = sector_size;

    ide_atapi_cmd_reply_end(s);
}

static void ide_atapi_cmd_check_status(IDEState *s)
{
    trace_ide_atapi_cmd_check_status(s);
    s->error = MC_ERR | (UNIT_ATTENTION << 4);
    s->status = ERR_STAT;
    s->nsector = 0;
    ide_bus_set_irq(s->bus);
}
/* ATAPI DMA support */

static void ide_atapi_cmd_read_dma_cb(void *opaque, int ret)
{
    IDEState *s = opaque;
    int n, dma_result;

    if (ret < 0) {
        if (ide_handle_rw_error(s, -ret, ide_dma_cmd_to_retry(s->dma_cmd))) {
            if (s->bus->error_status) {
                s->bus->dma->aiocb = NULL;
                return;
            }
            goto eot;
        }
    }

    if (s->io_buffer_size > 0) {
        /*
         * For a cdrom read sector command (s->lba != -1),
         * adjust the lba for the next s->io_buffer_size chunk
         * and dma the current chunk.
         * For a command != read (s->lba == -1), just transfer
         * the reply data.
         */
        if (s->lba != -1) {
            n = s->io_buffer_size / s->cd_sector_size;
            if (s->cd_sector_size == 2352) {
                cd_expand_raw_sectors(s, n);
            }
            s->lba += n;
        }
        s->packet_transfer_size -= s->io_buffer_size;
        dma_result = s->bus->dma->ops->rw_buf(s->bus->dma, true);

        if (dma_result <= 0) {
            if (dma_result < 0) {
                /* The guest DMA memory access failed; do not report the
                 * ATAPI transfer as successfully completed. */
                ret = -EIO;
                ide_atapi_io_error(s, ret);
            }
            goto eot;
        }
    }

    if (s->packet_transfer_size <= 0) {
        s->status = READY_STAT | SEEK_STAT;
        s->nsector = (s->nsector & ~7) | ATAPI_INT_REASON_IO | ATAPI_INT_REASON_CD;
        ide_bus_set_irq(s->bus);
        goto eot;
    }

    s->io_buffer_index = 0;
    /*
     * Both cooked and raw reads use the same bounded DMA staging buffer.
     * Raw sectors are expanded in place only after the packed read ends.
     */
    n = MIN(s->packet_transfer_size / s->cd_sector_size,
            IDE_DMA_BUF_SECTORS * BDRV_SECTOR_SIZE / s->cd_sector_size);
    s->io_buffer_size = n * s->cd_sector_size;
    trace_ide_atapi_cmd_read_dma_cb_aio(s, s->lba, n);
    qemu_iovec_init_buf(&s->bus->dma->qiov, s->io_buffer,
                       n * ATAPI_SECTOR_SIZE);

    s->bus->dma->aiocb = ide_buffered_readv(s, (int64_t)s->lba << 2,
                                            &s->bus->dma->qiov, n * 4,
                                            ide_atapi_cmd_read_dma_cb, s);
    return;

eot:
    if (ret < 0) {
        block_acct_failed(blk_get_stats(s->blk), &s->acct);
    } else {
        block_acct_done(blk_get_stats(s->blk), &s->acct);
    }
    ide_set_inactive(s, false);
}

/* start a CD-ROM read command with DMA */
/* XXX: test if DMA is available */
static void ide_atapi_cmd_read_dma(IDEState *s, int lba, int nb_sectors,
                                   int sector_size)
{
    assert(0 <= lba && lba < (s->nb_sectors >> 2));

    s->lba = lba;
    s->packet_transfer_size = nb_sectors * sector_size;
    s->io_buffer_size = 0;
    s->cd_sector_size = sector_size;

    block_acct_start(blk_get_stats(s->blk), &s->acct, s->packet_transfer_size,
                     BLOCK_ACCT_READ);

    /* XXX: check if BUSY_STAT should be set */
    s->status = READY_STAT | SEEK_STAT | DRQ_STAT | BUSY_STAT;
    ide_start_dma(s, ide_atapi_cmd_read_dma_cb);
}

static void ide_atapi_cmd_read(IDEState *s, int lba, int nb_sectors,
                               int sector_size)
{
    trace_ide_atapi_cmd_read(s, s->atapi_dma ? "dma" : "pio",
                             lba, nb_sectors);
    if (s->atapi_dma) {
        ide_atapi_cmd_read_dma(s, lba, nb_sectors, sector_size);
    } else {
        ide_atapi_cmd_read_pio(s, lba, nb_sectors, sector_size);
    }
}

void ide_atapi_dma_restart(IDEState *s)
{
    /*
     * At this point we can just re-evaluate the packet command and start over.
     * The presence of ->dma_cb callback in the pre_save ensures that the packet
     * command has been completely sent and we can safely restart command.
     */
    s->unit = s->bus->retry_unit;
    s->bus->dma->ops->restart_dma(s->bus->dma);
    ide_atapi_cmd(s);
}

static unsigned int event_status_media(IDEState *s,
                                       uint8_t *buf)
{
    uint8_t event_code, media_status;

    media_status = 0;
    if (s->tray_open) {
        media_status = MS_TRAY_OPEN;
    } else if (blk_is_inserted(s->blk)) {
        media_status = MS_MEDIA_PRESENT;
    }

    /* Event notification descriptor */
    event_code = MEC_NO_CHANGE;
    if (media_status != MS_TRAY_OPEN) {
        if (s->events.new_media) {
            event_code = MEC_NEW_MEDIA;
            s->events.new_media = false;
        } else if (s->events.eject_request) {
            event_code = MEC_EJECT_REQUESTED;
            s->events.eject_request = false;
        }
    }

    buf[4] = event_code;
    buf[5] = media_status;

    /* These fields are reserved, just clear them. */
    buf[6] = 0;
    buf[7] = 0;

    return 8; /* We wrote to 4 extra bytes from the header */
}

/*
 * Before transferring data or otherwise signalling acceptance of a command
 * marked CONDDATA, we must check the validity of the byte_count_limit.
 */
static bool validate_bcl(IDEState *s)
{
    /* TODO: Check IDENTIFY data word 125 for defacult BCL (currently 0) */
    if (s->atapi_dma || atapi_byte_count_limit(s)) {
        return true;
    }

    atapi_abort_bcl(s);
    return false;
}

static void cmd_get_event_status_notification(IDEState *s,
                                              uint8_t *buf)
{
    const uint8_t *packet = buf;

    struct {
        uint8_t opcode;
        uint8_t polled;        /* lsb bit is polled; others are reserved */
        uint8_t reserved2[2];
        uint8_t class;
        uint8_t reserved3[2];
        uint16_t len;
        uint8_t control;
    } QEMU_PACKED *gesn_cdb;

    struct {
        uint16_t len;
        uint8_t notification_class;
        uint8_t supported_events;
    } QEMU_PACKED *gesn_event_header;
    unsigned int max_len, used_len;

    gesn_cdb = (void *)packet;
    gesn_event_header = (void *)buf;

    max_len = be16_to_cpu(gesn_cdb->len);

    /* It is fine by the MMC spec to not support async mode operations */
    if (!(gesn_cdb->polled & 0x01)) { /* asynchronous mode */
        /* Only polling is supported, asynchronous mode is not. */
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_INV_FIELD_IN_CMD_PACKET);
        return;
    }

    /* polling mode operation */

    /*
     * These are the supported events.
     *
     * We currently only support requests of the 'media' type.
     * Notification class requests and supported event classes are bitmasks,
     * but they are build from the same values as the "notification class"
     * field.
     */
    gesn_event_header->supported_events = 1 << GESN_MEDIA;

    /*
     * We use |= below to set the class field; other bits in this byte
     * are reserved now but this is useful to do if we have to use the
     * reserved fields later.
     */
    gesn_event_header->notification_class = 0;

    /*
     * Responses to requests are to be based on request priority.  The
     * notification_class_request_type enum above specifies the
     * priority: upper elements are higher prio than lower ones.
     */
    if (gesn_cdb->class & (1 << GESN_MEDIA)) {
        gesn_event_header->notification_class |= GESN_MEDIA;
        used_len = event_status_media(s, buf);
    } else {
        gesn_event_header->notification_class = 0x80; /* No event available */
        used_len = sizeof(*gesn_event_header);
    }
    gesn_event_header->len = cpu_to_be16(used_len
                                         - sizeof(*gesn_event_header));
    ide_atapi_cmd_reply(s, used_len, max_len);
}

static void cmd_request_sense(IDEState *s, uint8_t *buf)
{
    int max_len = buf[4];

    memset(buf, 0, 18);
    buf[0] = 0x70 | (1 << 7);
    buf[2] = s->sense_key;
    buf[7] = 10;
    buf[12] = s->asc;

    if (s->sense_key == UNIT_ATTENTION) {
        s->sense_key = NO_SENSE;
    }

    ide_atapi_cmd_reply(s, 18, max_len);
}

static void cmd_inquiry(IDEState *s, uint8_t *buf)
{
    uint8_t page_code = buf[2];
    int max_len = buf[4];

    unsigned idx = 0;
    unsigned size_idx;
    unsigned preamble_len;

    /* If the EVPD (Enable Vital Product Data) bit is set in byte 1,
     * we are being asked for a specific page of info indicated by byte 2. */
    if (buf[1] & 0x01) {
        preamble_len = 4;
        size_idx = 3;

        buf[idx++] = 0x05;      /* CD-ROM */
        buf[idx++] = page_code; /* Page Code */
        buf[idx++] = 0x00;      /* reserved */
        idx++;                  /* length (set later) */

        switch (page_code) {
        case 0x00:
            /* Supported Pages: List of supported VPD responses. */
            buf[idx++] = 0x00; /* 0x00: Supported Pages, and: */
            buf[idx++] = 0x83; /* 0x83: Device Identification. */
            break;

        case 0x83:
            /* Device Identification. Each entry is optional, but the entries
             * included here are modeled after libata's VPD responses.
             * If the response is given, at least one entry must be present. */

            /* Entry 1: Serial */
            if (idx + 24 > max_len) {
                /* Not enough room for even the first entry: */
                /* 4 byte header + 20 byte string */
                ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                                    ASC_DATA_PHASE_ERROR);
                return;
            }
            buf[idx++] = 0x02; /* Ascii */
            buf[idx++] = 0x00; /* Vendor Specific */
            buf[idx++] = 0x00;
            buf[idx++] = 20;   /* Remaining length */
            padstr8(buf + idx, 20, s->drive_serial_str);
            idx += 20;

            /* Entry 2: Drive Model and Serial */
            if (idx + 72 > max_len) {
                /* 4 (header) + 8 (vendor) + 60 (model & serial) */
                goto out;
            }
            buf[idx++] = 0x02; /* Ascii */
            buf[idx++] = 0x01; /* T10 Vendor */
            buf[idx++] = 0x00;
            buf[idx++] = 68;
            padstr8(buf + idx, 8, "ATA"); /* Generic T10 vendor */
            idx += 8;
            padstr8(buf + idx, 40, s->drive_model_str);
            idx += 40;
            padstr8(buf + idx, 20, s->drive_serial_str);
            idx += 20;

            /* Entry 3: WWN */
            if (s->wwn && (idx + 12 <= max_len)) {
                /* 4 byte header + 8 byte wwn */
                buf[idx++] = 0x01; /* Binary */
                buf[idx++] = 0x03; /* NAA */
                buf[idx++] = 0x00;
                buf[idx++] = 0x08;
                stq_be_p(&buf[idx], s->wwn);
                idx += 8;
            }
            break;

        default:
            /* SPC-3, revision 23 sec. 6.4 */
            ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                                ASC_INV_FIELD_IN_CMD_PACKET);
            return;
        }
    } else {
        preamble_len = 5;
        size_idx = 4;

        buf[0] = 0x05; /* CD-ROM */
        buf[1] = 0x80; /* removable */
        buf[2] = 0x00; /* ISO */
        buf[3] = 0x21; /* ATAPI-2 (XXX: put ATAPI-4 ?) */
        /* buf[size_idx] set below. */
        buf[5] = 0;    /* reserved */
        buf[6] = 0;    /* reserved */
        buf[7] = 0;    /* reserved */
        padstr8(buf + 8, 8, "QEMU");
        padstr8(buf + 16, 16, s->atapi_inquiry_product ?:
                "QEMU DVD-ROM");
        padstr8(buf + 32, 4, s->version);
        idx = 36;
    }

 out:
    buf[size_idx] = idx - preamble_len;
    ide_atapi_cmd_reply(s, idx, max_len);
}

static void cmd_get_configuration(IDEState *s, uint8_t *buf)
{
    uint16_t current = MMC_PROFILE_NONE;
    int max_len;

    /* only feature 0 is supported */
    if (buf[2] != 0 || buf[3] != 0) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_INV_FIELD_IN_CMD_PACKET);
        return;
    }

    /* XXX: could result in alignment problems in some architectures */
    max_len = lduw_be_p(buf + 7);

    /*
     * XXX: avoid overflow for io_buffer if max_len is bigger than
     *      the size of that buffer (dimensioned to max number of
     *      sectors to transfer at once)
     *
     *      Only a problem if the feature/profiles grow.
     */
    if (max_len > BDRV_SECTOR_SIZE) {
        /* XXX: assume 1 sector */
        max_len = BDRV_SECTOR_SIZE;
    }

    /* A cooked image does not identify a recordable or erasable medium. */
    if (media_is_dvd(s) && !s->atapi_cd_only) {
        current = MMC_PROFILE_DVD_ROM;
    } else if (media_is_cd(s)) {
        current = MMC_PROFILE_CD_ROM;
    }

    mmc_rom_profile_list(buf, current);
    if (s->atapi_cd_only) {
        /* Keep only the CD-ROM profile descriptor. */
        memmove(buf + 12, buf + 16, 4);
        buf[3] = MMC_ROM_PROFILE_LIST_SIZE - 8;
        buf[11] = 4;
        ide_atapi_cmd_reply(s, MMC_ROM_PROFILE_LIST_SIZE - 4, max_len);
    } else {
        ide_atapi_cmd_reply(s, MMC_ROM_PROFILE_LIST_SIZE, max_len);
    }
}

static void cmd_mode_sense(IDEState *s, uint8_t *buf)
{
    int action, code;
    int max_len;

    max_len = lduw_be_p(buf + 7);
    action = buf[2] >> 6;
    code = buf[2] & 0x3f;

    switch(action) {
    case 0: /* current values */
        switch(code) {
        case MODE_PAGE_R_W_ERROR: /* error recovery */
            stw_be_p(&buf[0], 16 - 2);
            buf[2] = 0x70;
            buf[3] = 0;
            buf[4] = 0;
            buf[5] = 0;
            buf[6] = 0;
            buf[7] = 0;

            buf[8] = MODE_PAGE_R_W_ERROR;
            buf[9] = 16 - 10;
            buf[10] = 0x00;
            buf[11] = 0x05;
            buf[12] = 0x00;
            buf[13] = 0x00;
            buf[14] = 0x00;
            buf[15] = 0x00;
            ide_atapi_cmd_reply(s, 16, max_len);
            break;
        case MODE_PAGE_AUDIO_CTL:
            /* Do not return stale command bytes or previous reply data. */
            memset(buf, 0, 24);
            stw_be_p(&buf[0], 24 - 2);
            buf[2] = 0x70;
            buf[3] = 0;
            buf[4] = 0;
            buf[5] = 0;
            buf[6] = 0;
            buf[7] = 0;

            buf[8] = MODE_PAGE_AUDIO_CTL;
            buf[9] = 24 - 10;
            /* Fill with CDROM audio volume */
            buf[17] = 0;
            buf[19] = 0;
            buf[21] = 0;
            buf[23] = 0;

            ide_atapi_cmd_reply(s, 24, max_len);
            break;
        case MODE_PAGE_CAPABILITIES:
            stw_be_p(&buf[0], 30 - 2);
            buf[2] = 0x70;
            buf[3] = 0;
            buf[4] = 0;
            buf[5] = 0;
            buf[6] = 0;
            buf[7] = 0;

            buf[8] = MODE_PAGE_CAPABILITIES;
            buf[9] = 30 - 10;
            /* Do not claim DVD or unverified recordable-media support. */
            buf[10] = s->atapi_cd_only ? 0 : 0x3b;
            buf[11] = 0x00; /* No recording capabilities */

            /* Claim PLAY_AUDIO capability (0x01) since some Linux
               code checks for this to automount media. */
            buf[12] = 0x71;
            buf[13] = 3 << 5;
            buf[14] = (1 << 0) | (1 << 3) | (1 << 5);
            if (s->tray_locked) {
                buf[14] |= 1 << 1;
            }
            buf[15] = 0x00; /* No volume & mute control, no changer */
            stw_be_p(&buf[16], 704); /* 4x read speed */
            buf[18] = 0; /* Two volume levels */
            buf[19] = 2;
            stw_be_p(&buf[20], 512); /* 512k buffer */
            stw_be_p(&buf[22], 704); /* 4x read speed current */
            buf[24] = 0;
            buf[25] = 0;
            buf[26] = 0;
            buf[27] = 0;
            buf[28] = 0;
            buf[29] = 0;
            ide_atapi_cmd_reply(s, 30, max_len);
            break;
        default:
            goto error_cmd;
        }
        break;
    case 1: /* changeable values */
        goto error_cmd;
    case 2: /* default values */
        goto error_cmd;
    default:
    case 3: /* saved values */
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_SAVING_PARAMETERS_NOT_SUPPORTED);
        break;
    }
    return;

error_cmd:
    ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_INV_FIELD_IN_CMD_PACKET);
}

static void cmd_test_unit_ready(IDEState *s, uint8_t *buf)
{
    /* Not Ready Conditions are already handled in ide_atapi_cmd(), so if we
     * come here, we know that it's ready. */
    ide_atapi_cmd_ok(s);
}

static void cmd_prevent_allow_medium_removal(IDEState *s, uint8_t* buf)
{
    s->tray_locked = buf[4] & 1;
    blk_lock_medium(s->blk, buf[4] & 1);
    ide_atapi_cmd_ok(s);
}

static void cmd_read(IDEState *s, uint8_t* buf)
{
    unsigned int nb_sectors, lba;

    /* Total logical sectors of ATAPI_SECTOR_SIZE(=2048) bytes */
    uint64_t total_sectors = s->nb_sectors >> 2;

    if (buf[0] == GPCMD_READ_10) {
        nb_sectors = lduw_be_p(buf + 7);
    } else {
        nb_sectors = ldl_be_p(buf + 6);
    }
    if (nb_sectors == 0) {
        ide_atapi_cmd_ok(s);
        return;
    }

    lba = ldl_be_p(buf + 2);
    if (lba >= total_sectors || lba + nb_sectors - 1 >= total_sectors) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_LOGICAL_BLOCK_OOR);
        return;
    }

    ide_atapi_cmd_read(s, lba, nb_sectors, 2048);
}

static void cmd_read_cd(IDEState *s, uint8_t* buf)
{
    unsigned int nb_sectors, lba, transfer_request;

    /* Total logical sectors of ATAPI_SECTOR_SIZE(=2048) bytes */
    uint64_t total_sectors = s->nb_sectors >> 2;

    nb_sectors = (buf[6] << 16) | (buf[7] << 8) | buf[8];
    if (nb_sectors == 0) {
        ide_atapi_cmd_ok(s);
        return;
    }

    lba = ldl_be_p(buf + 2);
    if (lba >= total_sectors || nb_sectors > total_sectors - lba) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_LOGICAL_BLOCK_OOR);
        return;
    }

    transfer_request = buf[9] & 0xf8;
    if (transfer_request == 0x00) {
        /* nothing */
        ide_atapi_cmd_ok(s);
        return;
    }

    /*
     * The backing image exposes cooked Mode 1 blocks, not CD-DA or
     * XA sectors. Do not return synthetic Mode 1 for a different type.
     */
    switch (cdrom_mode1_expected_type(buf[1])) {
    case CDROM_SECTOR_MATCH:
        break;
    case CDROM_SECTOR_MISMATCH:
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_ILLEGAL_MODE_FOR_TRACK);
        return;
    case CDROM_SECTOR_RESERVED:
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_INV_FIELD_IN_CMD_PACKET);
        return;
    }

    /* Check validity of BCL before transferring data */
    if (!validate_bcl(s)) {
        return;
    }

    switch (transfer_request) {
    case 0x10:
        /* normal read */
        ide_atapi_cmd_read(s, lba, nb_sectors, 2048);
        break;
    case 0xf8:
        /* read all data */
        ide_atapi_cmd_read(s, lba, nb_sectors, 2352);
        break;
    default:
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_INV_FIELD_IN_CMD_PACKET);
        break;
    }
}

static void cmd_seek(IDEState *s, uint8_t* buf)
{
    unsigned int lba;
    uint64_t total_sectors = s->nb_sectors >> 2;

    lba = ldl_be_p(buf + 2);
    if (lba >= total_sectors) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_LOGICAL_BLOCK_OOR);
        return;
    }

    ide_atapi_cmd_ok(s);
}

static void cmd_start_stop_unit(IDEState *s, uint8_t* buf)
{
    int sense;
    bool start = buf[4] & 1;
    bool loej = buf[4] & 2;     /* load on start, eject on !start */
    int pwrcnd = buf[4] & 0xf0;

    if (pwrcnd) {
        /* eject/load only happens for power condition == 0 */
        ide_atapi_cmd_ok(s);
        return;
    }

    if (loej) {
        if (!start && !s->tray_open && s->tray_locked) {
            sense = blk_is_inserted(s->blk)
                ? NOT_READY : ILLEGAL_REQUEST;
            ide_atapi_cmd_error(s, sense, ASC_MEDIA_REMOVAL_PREVENTED);
            return;
        }

        if (s->tray_open != !start) {
            blk_eject(s->blk, !start);
            s->tray_open = !start;
        }
    }

    ide_atapi_cmd_ok(s);
}

static void cmd_mechanism_status(IDEState *s, uint8_t* buf)
{
    int max_len = lduw_be_p(buf + 8);

    stw_be_p(buf, 0);
    /* no current LBA */
    buf[2] = 0;
    buf[3] = 0;
    buf[4] = 0;
    buf[5] = 1;
    stw_be_p(buf + 6, 0);
    ide_atapi_cmd_reply(s, 8, max_len);
}

/* READ SUB-CHANNEL audio status header (SFF-8020, SUBQ clear). */
static void cmd_read_subchannel(IDEState *s, uint8_t *buf)
{
    int max_len = lduw_be_p(buf + 7);

    /* The raw image backend has no current sub-Q position or audio state. */
    if (buf[2] & 0x40) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_INV_FIELD_IN_CMD_PACKET);
        return;
    }
    if (!max_len) {
        ide_atapi_cmd_ok(s);
        return;
    }
    if (!validate_bcl(s)) {
        return;
    }
    memset(buf, 0, 4);
    buf[1] = 0x00; /* Audio status not supported. */
    ide_atapi_cmd_reply(s, 4, max_len);
}

static void cmd_read_toc_pma_atip(IDEState *s, uint8_t* buf)
{
    int format, msf, start_track, len;
    int max_len;
    uint64_t total_sectors = s->nb_sectors >> 2;

    max_len = lduw_be_p(buf + 7);
    format = buf[9] >> 6;
    msf = (buf[1] >> 1) & 1;
    start_track = buf[6];

    switch(format) {
    case 0:
        len = cdrom_read_toc(total_sectors, buf, msf, start_track);
        if (len < 0)
            goto error_cmd;
        ide_atapi_cmd_reply(s, len, max_len);
        break;
    case 1:
        /* multi session : only a single session defined */
        memset(buf, 0, 12);
        buf[1] = 0x0a;
        buf[2] = 0x01;
        buf[3] = 0x01;
        ide_atapi_cmd_reply(s, 12, max_len);
        break;
    case 2:
        len = cdrom_read_toc_raw(total_sectors, buf, msf, start_track);
        if (len < 0)
            goto error_cmd;
        ide_atapi_cmd_reply(s, len, max_len);
        break;
    default:
    error_cmd:
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_INV_FIELD_IN_CMD_PACKET);
    }
}

static void cmd_read_cdvd_capacity(IDEState *s, uint8_t* buf)
{
    uint64_t total_sectors = s->nb_sectors >> 2;

    /* NOTE: it is really the number of sectors minus 1 */
    stl_be_p(buf, total_sectors - 1);
    stl_be_p(buf + 4, 2048);
    ide_atapi_cmd_reply(s, 8, 8);
}

static void cmd_read_disc_information(IDEState *s, uint8_t* buf)
{
    uint8_t type = buf[1] & 7;
    uint32_t max_len = lduw_be_p(buf + 7);

    /* Types 1/2 are only defined for Blu-Ray.  */
    if (type != 0) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                            ASC_INV_FIELD_IN_CMD_PACKET);
        return;
    }

    mmc_rom_disc_information(buf);

    ide_atapi_cmd_reply(s, MMC_ROM_DISC_INFO_SIZE, max_len);
}

static void cmd_read_dvd_structure(IDEState *s, uint8_t* buf)
{
    int max_len;
    int media = buf[1];
    uint8_t layer = buf[6];
    int format = buf[7];
    int ret;

    max_len = lduw_be_p(buf + 8);

    if (format < 0xff) {
        if (media_is_cd(s)) {
            ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                                ASC_INCOMPATIBLE_FORMAT);
            return;
        } else if (!media_present(s)) {
            ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                                ASC_INV_FIELD_IN_CMD_PACKET);
            return;
        }
    }

    switch (format) {
        case 0x00 ... 0x7f:
        case 0xff:
            if (media == 0) {
                ret = dvdrom_read_structure(s->nb_sectors >> 2, layer,
                                            format, buf,
                                            s->io_buffer_total_len);

                if (ret < 0) {
                    ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                        ret == -ENOMEDIUM ? ASC_MEDIUM_NOT_PRESENT :
                                           ASC_INV_FIELD_IN_CMD_PACKET);
                } else {
                    ide_atapi_cmd_reply(s, ret, max_len);
                }

                break;
            }
            /* TODO: BD support, fall through for now */

        /* Generic disk structures */
        case 0x80: /* TODO: AACS volume identifier */
        case 0x81: /* TODO: AACS media serial number */
        case 0x82: /* TODO: AACS media identifier */
        case 0x83: /* TODO: AACS media key block */
        case 0x90: /* TODO: List of recognized format layers */
        case 0xc0: /* TODO: Write protection status */
        default:
            ide_atapi_cmd_error(s, ILLEGAL_REQUEST,
                                ASC_INV_FIELD_IN_CMD_PACKET);
            break;
    }
}

static void cmd_set_speed(IDEState *s, uint8_t* buf)
{
    ide_atapi_cmd_ok(s);
}

enum {
    /*
     * Only commands flagged as ALLOW_UA are allowed to run under a
     * unit attention condition. (See MMC-5, section 4.1.6.1)
     */
    ALLOW_UA = 0x01,

    /*
     * Commands flagged with CHECK_READY can only execute if a medium is present.
     * Otherwise they report the Not Ready Condition. (See MMC-5, section
     * 4.1.8)
     */
    CHECK_READY = 0x02,

    /*
     * Commands flagged with NONDATA do not in any circumstances return
     * any data via ide_atapi_cmd_reply. These commands are exempt from
     * the normal byte_count_limit constraints.
     * See ATA8-ACS3 "7.21.5 Byte Count Limit"
     */
    NONDATA = 0x04,

    /*
     * CONDDATA implies a command that transfers data only conditionally based
     * on the presence of suboptions. It should be exempt from the BCL check at
     * command validation time, but it needs to be checked at the command
     * handler level instead.
     */
    CONDDATA = 0x08,
};

static const struct AtapiCmd {
    void (*handler)(IDEState *s, uint8_t *buf);
    int flags;
} atapi_cmd_table[0x100] = {
    [ 0x00 ] = { cmd_test_unit_ready,               CHECK_READY | NONDATA },
    [ 0x03 ] = { cmd_request_sense,                 ALLOW_UA },
    [ 0x12 ] = { cmd_inquiry,                       ALLOW_UA },
    [ 0x1b ] = { cmd_start_stop_unit,               NONDATA }, /* [1] */
    [ 0x1e ] = { cmd_prevent_allow_medium_removal,  NONDATA },
    [ 0x25 ] = { cmd_read_cdvd_capacity,            CHECK_READY },
    [ 0x28 ] = { cmd_read, /* (10) */               CHECK_READY },
    [ 0x2b ] = { cmd_seek,                          CHECK_READY | NONDATA },
    [ 0x42 ] = { cmd_read_subchannel,               CHECK_READY | CONDDATA },
    [ 0x43 ] = { cmd_read_toc_pma_atip,             CHECK_READY },
    [ 0x46 ] = { cmd_get_configuration,             ALLOW_UA },
    [ 0x4a ] = { cmd_get_event_status_notification, ALLOW_UA },
    [ 0x51 ] = { cmd_read_disc_information,         CHECK_READY },
    [ 0x5a ] = { cmd_mode_sense, /* (10) */         0 },
    [ 0xa8 ] = { cmd_read, /* (12) */               CHECK_READY },
    [ 0xad ] = { cmd_read_dvd_structure,            CHECK_READY },
    [ 0xbb ] = { cmd_set_speed,                     NONDATA },
    [ 0xbd ] = { cmd_mechanism_status,              0 },
    [ 0xbe ] = { cmd_read_cd,                       CHECK_READY | CONDDATA },
    /* [1] handler detects and reports not ready condition itself */
};

void ide_atapi_cmd(IDEState *s)
{
    uint8_t *buf = s->io_buffer;
    const struct AtapiCmd *cmd = &atapi_cmd_table[s->io_buffer[0]];

    trace_ide_atapi_cmd(s, s->io_buffer[0]);

    if (trace_event_get_state_backends(TRACE_IDE_ATAPI_CMD_PACKET)) {
        g_autoptr(GString) str =
            qemu_hexdump_line(NULL, buf, ATAPI_PACKET_SIZE, 1, 0);
        trace_ide_atapi_cmd_packet(s, s->lcyl | (s->hcyl << 8), str->str);
    }

    /*
     * If there's a UNIT_ATTENTION condition pending, only command flagged with
     * ALLOW_UA are allowed to complete. with other commands getting a CHECK
     * condition response unless a higher priority status, defined by the drive
     * here, is pending.
     */
    if (s->sense_key == UNIT_ATTENTION && !(cmd->flags & ALLOW_UA)) {
        ide_atapi_cmd_check_status(s);
        return;
    }
    /*
     * When a CD gets changed, we have to report an ejected state and
     * then a loaded state to guests so that they detect tray
     * open/close and media change events.  Guests that do not use
     * GET_EVENT_STATUS_NOTIFICATION to detect such tray open/close
     * states rely on this behavior.
     */
    if (!(cmd->flags & ALLOW_UA) &&
        !s->tray_open && blk_is_inserted(s->blk) && s->cdrom_changed) {

        if (s->cdrom_changed == 1) {
            ide_atapi_cmd_error(s, NOT_READY, ASC_MEDIUM_NOT_PRESENT);
            s->cdrom_changed = 2;
        } else {
            ide_atapi_cmd_error(s, UNIT_ATTENTION, ASC_MEDIUM_MAY_HAVE_CHANGED);
            s->cdrom_changed = 0;
        }

        return;
    }

    /* CD-only profiles cannot execute DVD-specific commands. */
    if (s->atapi_cd_only && buf[0] == 0xad) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_ILLEGAL_OPCODE);
        return;
    }

    /* Cooked images lack a physical media type; use the existing size test. */
    if (s->atapi_cd_only && (cmd->flags & CHECK_READY) && media_is_dvd(s)) {
        ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_INCOMPATIBLE_FORMAT);
        return;
    }

    /* Report a Not Ready condition if appropriate for the command */
    if ((cmd->flags & CHECK_READY) &&
        (!media_present(s) || !blk_is_inserted(s->blk)))
    {
        ide_atapi_cmd_error(s, NOT_READY, ASC_MEDIUM_NOT_PRESENT);
        return;
    }

    /* Commands that don't transfer DATA permit the byte_count_limit to be 0.
     * If this is a data-transferring PIO command and BCL is 0,
     * we abort at the /ATA/ level, not the ATAPI level.
     * See ATA8 ACS3 section 7.17.6.49 and 7.21.5 */
    if (cmd->handler && !(cmd->flags & (NONDATA | CONDDATA))) {
        if (!validate_bcl(s)) {
            return;
        }
    }

    /* Execute the command */
    if (cmd->handler) {
        cmd->handler(s, buf);
        return;
    }

    ide_atapi_cmd_error(s, ILLEGAL_REQUEST, ASC_ILLEGAL_OPCODE);
}

/* Existing removable-media migration subsections; wire format unchanged. */
static bool ide_tray_state_needed(void *opaque)
{
    IDEState *s = opaque;

    return s->tray_open || s->tray_locked;
}

static bool ide_atapi_gesn_needed(void *opaque)
{
    IDEState *s = opaque;

    return s->events.new_media || s->events.eject_request;
}

/* Fields for GET_EVENT_STATUS_NOTIFICATION ATAPI command */
const VMStateDescription vmstate_ide_atapi_gesn_state = {
    .name ="ide_drive/atapi/gesn_state",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = ide_atapi_gesn_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(events.new_media, IDEState),
        VMSTATE_BOOL(events.eject_request, IDEState),
        VMSTATE_END_OF_LIST()
    }
};

const VMStateDescription vmstate_ide_tray_state = {
    .name = "ide_drive/tray_state",
    .version_id = 1,
    .minimum_version_id = 1,
    .needed = ide_tray_state_needed,
    .fields = (const VMStateField[]) {
        VMSTATE_BOOL(tray_open, IDEState),
        VMSTATE_BOOL(tray_locked, IDEState),
        VMSTATE_END_OF_LIST()
    }
};
